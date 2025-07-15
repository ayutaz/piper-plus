"""
PyTorch Lightning module for multilingual VITS training.
Extends the original VitsModel to support language embeddings.
"""

import logging
from pathlib import Path

import pytorch_lightning as pl
import torch
from torch import autocast
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .commons import slice_segments
from .dataset_multilingual import (
    MultilingualBatch,
    MultilingualCollate,
    MultilingualDataset,
)
from .losses import discriminator_loss, feature_loss, generator_loss, kl_loss
from .mel_processing import mel_spectrogram_torch
from .models import MultiPeriodDiscriminator
from .models_multilingual import MultilingualSynthesizerTrn

_LOGGER = logging.getLogger("vits.lightning_multilingual")


class MultilingualVitsModel(pl.LightningModule):
    """PyTorch Lightning module for multilingual VITS training."""

    def __init__(
        self,
        num_symbols: int,
        num_speakers: int,
        num_languages: int = 8,
        lang_embedding_dim: int = 64,
        # audio
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=(
            (1, 2),
            (2, 6),
            (3, 12),
        ),
        upsample_rates=(8, 8, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16, 8),
        # mel
        filter_length: int = 1024,
        hop_length: int = 256,
        win_length: int = 1024,
        mel_channels: int = 80,
        sample_rate: int = 22050,
        sample_bytes: int = 2,
        channels: int = 1,
        mel_fmin: float = 0.0,
        mel_fmax: float | None = None,
        # model
        inter_channels: int = 192,
        hidden_channels: int = 192,
        filter_channels: int = 768,
        n_heads: int = 2,
        n_layers: int = 6,
        kernel_size: int = 3,
        p_dropout: float = 0.1,
        n_layers_q: int = 3,
        use_spectral_norm: bool = False,
        gin_channels: int = 0,
        use_sdp: bool = True,
        segment_size: int = 8192,
        # training
        dataset: list[str | Path] | None = None,
        learning_rate: float = 2e-4,
        betas: tuple[float, float] = (0.8, 0.99),
        eps: float = 1e-9,
        batch_size: int = 1,
        lr_decay: float = 0.999875,
        init_lr_ratio: float = 1.0,
        warmup_epochs: int = 0,
        c_mel: int = 45,
        c_kl: float = 1.0,
        grad_clip: float | None = None,
        num_workers: int = 1,
        seed: int = 1234,
        num_test_examples: int = 5,
        validation_split: float = 0.1,
        max_phoneme_ids: int | None = None,
        language_map: dict[str, int] | None = None,
        **kwargs,
    ):
        super().__init__()
        self.save_hyperparameters()

        if (self.hparams.num_speakers > 1) and (self.hparams.gin_channels <= 0):
            # Default gin_channels for multi-speaker model
            self.hparams.gin_channels = 512

        # Default language map
        if language_map is None:
            self.hparams.language_map = {
                "ja": 0,
                "en": 1,
                "zh": 2,
                "es": 3,
                "fr": 4,
                "de": 5,
                "ko": 6,
                "mixed": 7,  # For mixed language utterances
            }

        # Set up multilingual model
        self.model_g = MultilingualSynthesizerTrn(
            n_vocab=self.hparams.num_symbols,
            spec_channels=self.hparams.filter_length // 2 + 1,
            segment_size=self.hparams.segment_size // self.hparams.hop_length,
            inter_channels=self.hparams.inter_channels,
            hidden_channels=self.hparams.hidden_channels,
            filter_channels=self.hparams.filter_channels,
            n_heads=self.hparams.n_heads,
            n_layers=self.hparams.n_layers,
            kernel_size=self.hparams.kernel_size,
            p_dropout=self.hparams.p_dropout,
            resblock=self.hparams.resblock,
            resblock_kernel_sizes=self.hparams.resblock_kernel_sizes,
            resblock_dilation_sizes=self.hparams.resblock_dilation_sizes,
            upsample_rates=self.hparams.upsample_rates,
            upsample_initial_channel=self.hparams.upsample_initial_channel,
            upsample_kernel_sizes=self.hparams.upsample_kernel_sizes,
            n_speakers=self.hparams.num_speakers,
            gin_channels=self.hparams.gin_channels,
            use_sdp=self.hparams.use_sdp,
            n_languages=self.hparams.num_languages,
            lang_embedding_dim=self.hparams.lang_embedding_dim,
        )

        self.model_d = MultiPeriodDiscriminator(
            use_spectral_norm=self.hparams.use_spectral_norm
        )

        # Dataset splits
        self._train_dataset: Dataset | None = None
        self._val_dataset: Dataset | None = None
        self._test_dataset: Dataset | None = None
        self._load_datasets(validation_split, num_test_examples, max_phoneme_ids)

        # State kept between training optimizers
        self._y = None
        self._y_hat = None

    def _load_datasets(
        self,
        validation_split: float,
        num_test_examples: int,
        max_phoneme_ids: int | None = None,
    ):
        if self.hparams.dataset is None:
            _LOGGER.debug("No dataset to load")
            return

        full_dataset = MultilingualDataset(
            self.hparams.dataset,
            max_phoneme_ids=max_phoneme_ids,
            language_map=self.hparams.language_map,
        )
        valid_set_size = int(len(full_dataset) * validation_split)
        train_set_size = len(full_dataset) - valid_set_size - num_test_examples

        self._train_dataset, self._test_dataset, self._val_dataset = random_split(
            full_dataset, [train_set_size, num_test_examples, valid_set_size]
        )

    def forward(self, text, text_lengths, scales, sid=None, lang_ids=None):
        noise_scale = scales[0]
        length_scale = scales[1]
        noise_scale_w = scales[2]
        audio, *_ = self.model_g.infer(
            text,
            text_lengths,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
            sid=sid,
            lang_ids=lang_ids,
        )

        return audio

    def training_step(self, batch: MultilingualBatch, batch_idx: int):
        # Optimizers
        optim_g, optim_d = self.optimizers()

        # Generator step
        (
            y_hat,
            l_length,
            attn,
            ids_slice,
            x_mask,
            y_mask,
            (z, z_p, m_p, logs_p, m_q, logs_q),
        ) = self.model_g(
            batch.phoneme_ids,
            batch.phoneme_lengths,
            batch.spectrogram,
            batch.spectrogram_lengths,
            sid=batch.speaker_ids,
            lang_ids=batch.language_ids,
        )

        # mel = slice_segments(
        #     batch.spectrogram,
        #     ids_slice,
        #     self.hparams.segment_size // self.hparams.hop_length,
        # )
        y_mel = slice_segments(
            batch.audio, ids_slice * self.hparams.hop_length, self.hparams.segment_size
        )
        y_hat_mel = mel_spectrogram_torch(
            y_hat.squeeze(1),
            self.hparams.filter_length,
            self.hparams.mel_channels,
            self.hparams.sample_rate,
            self.hparams.hop_length,
            self.hparams.win_length,
            self.hparams.mel_fmin,
            self.hparams.mel_fmax,
        )

        self._y = slice_segments(
            batch.audio, ids_slice * self.hparams.hop_length, self.hparams.segment_size
        )

        self._y_hat = y_hat

        # Generator losses
        with autocast(enabled=False):
            # Only run discriminator on generator output
            y_d_hat_r, y_d_hat_g, _, _ = self.model_d(self._y, self._y_hat.detach())

            loss_disc, losses_disc_r, losses_disc_g = discriminator_loss(
                y_d_hat_r, y_d_hat_g
            )
            loss_disc_all = loss_disc

        # Log discriminator loss
        self.log("loss_disc_all", loss_disc_all)

        # Update discriminator
        self.manual_backward(loss_disc_all)
        if self.hparams.grad_clip:
            self.clip_gradients(
                optim_d, gradient_clip_val=self.hparams.grad_clip, gradient_clip_algorithm="norm"
            )
        optim_d.step()
        optim_d.zero_grad()

        with autocast(enabled=False):
            # Generator
            y_d_hat_r, y_d_hat_g, fmap_r, fmap_g = self.model_d(self._y, self._y_hat)
            loss_fm = feature_loss(fmap_r, fmap_g)
            loss_mel = F.l1_loss(y_mel, y_hat_mel) * self.hparams.c_mel
            loss_kl = kl_loss(z_p, logs_q, m_p, logs_p, z_mask=y_mask) * self.hparams.c_kl
            loss_gen, losses_gen = generator_loss(y_d_hat_g)
            loss_gen_all = loss_gen + loss_fm + loss_mel + loss_kl

        # Log generator losses
        self.log("loss_gen", loss_gen)
        self.log("loss_fm", loss_fm)
        self.log("loss_mel", loss_mel)
        self.log("loss_kl", loss_kl)
        self.log("loss_gen_all", loss_gen_all)

        # Update generator
        self.manual_backward(loss_gen_all)
        if self.hparams.grad_clip:
            self.clip_gradients(
                optim_g, gradient_clip_val=self.hparams.grad_clip, gradient_clip_algorithm="norm"
            )
        optim_g.step()
        optim_g.zero_grad()

        # Learning rate scheduling
        schedulers = self.lr_schedulers()
        if isinstance(schedulers, list):
            for scheduler in schedulers:
                scheduler.step()
        else:
            schedulers.step()

    def validation_step(self, batch: MultilingualBatch, batch_idx: int):
        # Similar to training step but without optimization
        (
            y_hat,
            l_length,
            attn,
            ids_slice,
            x_mask,
            y_mask,
            (z, z_p, m_p, logs_p, m_q, logs_q),
        ) = self.model_g(
            batch.phoneme_ids,
            batch.phoneme_lengths,
            batch.spectrogram,
            batch.spectrogram_lengths,
            sid=batch.speaker_ids,
            lang_ids=batch.language_ids,
        )

        # mel = slice_segments(
        #     batch.spectrogram,
        #     ids_slice,
        #     self.hparams.segment_size // self.hparams.hop_length,
        # )
        y_mel = slice_segments(
            batch.audio, ids_slice * self.hparams.hop_length, self.hparams.segment_size
        )
        y_hat_mel = mel_spectrogram_torch(
            y_hat.squeeze(1),
            self.hparams.filter_length,
            self.hparams.mel_channels,
            self.hparams.sample_rate,
            self.hparams.hop_length,
            self.hparams.win_length,
            self.hparams.mel_fmin,
            self.hparams.mel_fmax,
        )

        # y = slice_segments(
        #     batch.audio, ids_slice * self.hparams.hop_length, self.hparams.segment_size
        # )

        # Calculate validation losses
        loss_mel = F.l1_loss(y_mel, y_hat_mel) * self.hparams.c_mel
        loss_kl = kl_loss(z_p, logs_q, m_p, logs_p, z_mask=y_mask) * self.hparams.c_kl

        self.log("val_loss_mel", loss_mel)
        self.log("val_loss_kl", loss_kl)
        self.log("val_loss", loss_mel + loss_kl)

    def configure_optimizers(self):
        # Configure optimizers and learning rate schedulers
        optim_g = torch.optim.AdamW(
            self.model_g.parameters(),
            lr=self.hparams.learning_rate,
            betas=self.hparams.betas,
            eps=self.hparams.eps,
        )
        optim_d = torch.optim.AdamW(
            self.model_d.parameters(),
            lr=self.hparams.learning_rate,
            betas=self.hparams.betas,
            eps=self.hparams.eps,
        )

        scheduler_g = torch.optim.lr_scheduler.ExponentialLR(
            optim_g, gamma=self.hparams.lr_decay
        )
        scheduler_d = torch.optim.lr_scheduler.ExponentialLR(
            optim_d, gamma=self.hparams.lr_decay
        )

        return [optim_g, optim_d], [scheduler_g, scheduler_d]

    def train_dataloader(self):
        if self._train_dataset is None:
            return None

        return DataLoader(
            self._train_dataset,
            batch_size=self.hparams.batch_size,
            shuffle=True,
            num_workers=self.hparams.num_workers,
            collate_fn=MultilingualCollate(),
            pin_memory=True,
        )

    def val_dataloader(self):
        if self._val_dataset is None:
            return None

        return DataLoader(
            self._val_dataset,
            batch_size=self.hparams.batch_size,
            num_workers=self.hparams.num_workers,
            collate_fn=MultilingualCollate(),
            pin_memory=True,
        )

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = parent_parser.add_argument_group("MultilingualVitsModel")
        parser.add_argument("--batch-size", type=int, default=16)
        parser.add_argument("--validation-split", type=float, default=0.1)
        parser.add_argument("--num-test-examples", type=int, default=5)
        parser.add_argument("--max-phoneme-ids", type=int)
        parser.add_argument("--hidden-channels", type=int, default=192)
        parser.add_argument("--inter-channels", type=int, default=192)
        parser.add_argument("--filter-channels", type=int, default=768)
        parser.add_argument("--n-layers", type=int, default=6)
        parser.add_argument("--n-heads", type=int, default=2)
        parser.add_argument("--num-languages", type=int, default=8)
        parser.add_argument("--lang-embedding-dim", type=int, default=64)

        return parent_parser
