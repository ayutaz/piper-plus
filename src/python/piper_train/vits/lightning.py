import logging
import os
from pathlib import Path

import pytorch_lightning as pl
import torch
from torch import autocast
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .commons import slice_segments
from .dataset import Batch, PiperDataset, UtteranceCollate
from .f0_predictor import F0Loss
from .losses import (
    discriminator_loss,
    duration_consistency_loss,
    feature_loss,
    generator_loss,
    kl_loss,
)
from .mel_processing import mel_spectrogram_torch, spec_to_mel_torch
from .models import MultiPeriodDiscriminator, SynthesizerTrn
from .stft_discriminator import CombinedMultiDiscriminator
from .stft_loss import MultiResolutionSTFTLoss

_LOGGER = logging.getLogger("vits.lightning")


class VitsModel(pl.LightningModule):
    def __init__(
        self,
        num_symbols: int,
        num_speakers: int,
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
        c_stft: float = 1.0,
        c_dur_consistency: float = 0.01,
        use_stft_discriminator: bool = True,  # Default: ON - Better quality
        use_duration_regularization: bool = True,  # Default: ON - Stability
        use_wavlm_discriminator: bool = False,
        wavlm_model: str = "microsoft/wavlm-base",
        c_wavlm: float = 1.0,
        wavlm_weight: float = 0.5,
        use_bert_encoder: bool = False,  # Default: OFF - Japanese only, high memory
        bert_model_name: str = "cl-tohoku/bert-base-japanese-v3",
        bert_weight: float = 0.3,
        use_flow_matching: bool = True,  # Default: ON - Better quality & stability
        c_flow_matching: float = 1.0,
        grad_clip: float | None = None,
        num_workers: int = 1,
        seed: int = 1234,
        num_test_examples: int = 5,
        validation_split: float = 0.1,
        max_phoneme_ids: int | None = None,
        **kwargs,
    ):
        super().__init__()
        self.save_hyperparameters()

        if (self.hparams.num_speakers > 1) and (self.hparams.gin_channels <= 0):
            # Default gin_channels for multi-speaker model
            self.hparams.gin_channels = 512

        # Set up models
        self.use_bert = self.hparams.use_bert_encoder
        self.model_g = SynthesizerTrn(
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
            use_bert_encoder=self.hparams.use_bert_encoder,
            bert_model_name=self.hparams.bert_model_name,
            bert_weight=self.hparams.bert_weight,
            use_flow_matching=self.hparams.use_flow_matching,
        )
        if self.hparams.use_wavlm_discriminator:
            from .wavlm_discriminator import WavLMMultiPeriodDiscriminator
            self.model_d = WavLMMultiPeriodDiscriminator(
                use_spectral_norm=self.hparams.use_spectral_norm,
                wavlm_model=self.hparams.wavlm_model,
                wavlm_weight=self.hparams.wavlm_weight,
            )
        elif self.hparams.use_stft_discriminator:
            self.model_d = CombinedMultiDiscriminator(
                use_spectral_norm=self.hparams.use_spectral_norm,
            )
        else:
            self.model_d = MultiPeriodDiscriminator(
                use_spectral_norm=self.hparams.use_spectral_norm,
            )

        # F0 loss
        self.f0_loss = F0Loss()

        # Multi-resolution STFT loss
        self.stft_loss = MultiResolutionSTFTLoss()

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

        full_dataset = PiperDataset(
            self.hparams.dataset,
            max_phoneme_ids=max_phoneme_ids,
        )
        valid_set_size = int(len(full_dataset) * validation_split)
        train_set_size = len(full_dataset) - valid_set_size - num_test_examples

        self._train_dataset, self._test_dataset, self._val_dataset = random_split(
            full_dataset,
            [train_set_size, num_test_examples, valid_set_size],
        )

    def forward(self, text, text_lengths, scales, sid=None, prosody_ids=None):
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
            prosody_ids=prosody_ids,
        )

        return audio

    def train_dataloader(self):
        return DataLoader(
            self._train_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
                use_augmentation=True,
                spec_augment_params={
                    "freq_mask_param": 27,
                    "time_mask_param": 100,
                    "freq_mask_num": 2,
                    "time_mask_num": 2,
                },
                audio_augment_params={
                    "speed_perturb_range": (0.9, 1.1),
                    "pitch_shift_range": (-2, 2),
                    "enable_speed_perturb": True,
                    "enable_pitch_shift": True,
                },
            ),
            num_workers=self.hparams.num_workers,
            batch_size=self.hparams.batch_size,
            pin_memory=True,
            shuffle=True,
        )

    def val_dataloader(self):
        return DataLoader(
            self._val_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
            ),
            num_workers=self.hparams.num_workers,
            batch_size=self.hparams.batch_size,
            pin_memory=True,
        )

    def test_dataloader(self):
        return DataLoader(
            self._test_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
            ),
            num_workers=self.hparams.num_workers,
            batch_size=self.hparams.batch_size,
        )

    def training_step(self, batch: Batch, batch_idx: int, optimizer_idx: int):
        if optimizer_idx == 0:
            return self.training_step_g(batch)

        if optimizer_idx == 1:
            return self.training_step_d(batch)

    def training_step_g(self, batch: Batch):
        x, x_lengths, y, _, spec, spec_lengths, speaker_ids, prosody_ids, f0_values, texts = (
            batch.phoneme_ids,
            batch.phoneme_lengths,
            batch.audios,
            batch.audio_lengths,
            batch.spectrograms,
            batch.spectrogram_lengths,
            batch.speaker_ids if batch.speaker_ids is not None else None,
            batch.prosody_ids if batch.prosody_ids is not None else None,
            batch.f0_values if batch.f0_values is not None else None,
            batch.texts if batch.texts is not None else None,
        )
        (
            y_hat,
            l_length,
            _attn,
            ids_slice,
            _x_mask,
            z_mask,
            (_z, z_p, m_p, logs_p, _m_q, logs_q),
            (f0_pred, f0_variance),
            pred_durations,
        ) = self.model_g(x, x_lengths, spec, spec_lengths, speaker_ids, prosody_ids, texts)
        self._y_hat = y_hat

        # Store z for flow matching loss
        self._z = _z
        self._z_mask = z_mask

        mel = spec_to_mel_torch(
            spec,
            self.hparams.filter_length,
            self.hparams.mel_channels,
            self.hparams.sample_rate,
            self.hparams.mel_fmin,
            self.hparams.mel_fmax,
        )
        y_mel = slice_segments(
            mel,
            ids_slice,
            self.hparams.segment_size // self.hparams.hop_length,
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
        y = slice_segments(
            y,
            ids_slice * self.hparams.hop_length,
            self.hparams.segment_size,
        )  # slice

        # Save for training_step_d
        self._y = y

        _y_d_hat_r, y_d_hat_g, fmap_r, fmap_g = self.model_d(y, y_hat)

        with autocast(self.device.type, enabled=False):
            # Generator loss
            loss_dur = torch.sum(l_length.float())
            loss_mel = F.l1_loss(y_mel, y_hat_mel) * self.hparams.c_mel
            loss_kl = kl_loss(z_p, logs_q, m_p, logs_p, z_mask) * self.hparams.c_kl

            loss_fm = feature_loss(fmap_r, fmap_g)
            loss_gen, _losses_gen = generator_loss(y_d_hat_g)

            # F0 loss
            loss_f0 = torch.tensor(0.0, device=self.device)
            if f0_pred is not None and f0_values is not None:
                # Create mask for valid F0 frames
                f0_mask = z_mask[:, :, : f0_values.shape[-1]]

                # Apply F0 loss
                loss_f0, f0_metrics = self.f0_loss(
                    None,  # f0_pred_bins not used in this version
                    f0_pred[:, :, : f0_values.shape[-1]],  # Match dimensions
                    f0_variance[:, :, : f0_values.shape[-1]],
                    f0_values.unsqueeze(1),  # Add channel dimension
                    f0_mask,
                )

                # Log F0 metrics
                for metric_name, metric_value in f0_metrics.items():
                    self.log(f"train/{metric_name}", metric_value)

            # Multi-resolution STFT loss
            loss_stft = torch.tensor(0.0, device=self.device)
            if self.hparams.use_stft_discriminator and not self.hparams.use_wavlm_discriminator:
                loss_stft, stft_metrics = self.stft_loss(y_hat, y)
                loss_stft = loss_stft * self.hparams.c_stft

                # Log STFT metrics
                for metric_name, metric_value in stft_metrics.items():
                    self.log(f"train/{metric_name}", metric_value)

            # WavLM discriminator already includes multi-scale losses
            # so we don't need separate STFT loss when using WavLM

            # Duration consistency loss
            loss_dur_consistency = torch.tensor(0.0, device=self.device)
            if self.hparams.use_duration_regularization and pred_durations is not None:
                loss_dur_consistency, dur_metrics = duration_consistency_loss(
                    pred_durations,
                    x_lengths,
                    phoneme_ids=x,  # Pass phoneme IDs for phoneme-specific penalties
                )
                loss_dur_consistency = (
                    loss_dur_consistency * self.hparams.c_dur_consistency
                )

                # Log duration metrics
                for metric_name, metric_value in dur_metrics.items():
                    self.log(f"train/{metric_name}", metric_value)

            # Adjust feature matching loss weight when using WavLM
            if self.hparams.use_wavlm_discriminator:
                loss_fm = loss_fm * self.hparams.c_wavlm

            # Flow matching loss
            loss_flow_matching = 0.0
            if self.hparams.use_flow_matching:
                # Get global conditioning if multi-speaker
                g = None
                if speaker_ids is not None:
                    g = self.model_g.emb_g(speaker_ids).unsqueeze(-1)

                loss_flow_matching = self.model_g.compute_flow_matching_loss(
                    self._z, self._z_mask, g
                ) * self.hparams.c_flow_matching
                self.log("loss_flow_matching", loss_flow_matching)

            loss_gen_all = (
                loss_gen
                + loss_fm
                + loss_mel
                + loss_dur
                + loss_kl
                + loss_f0
                + loss_stft
                + loss_dur_consistency
                + loss_flow_matching
            )

            self.log("loss_gen_all", loss_gen_all)
            self.log("loss_fm", loss_fm)
            self.log("loss_gen", loss_gen)

            return loss_gen_all

    def training_step_d(self, batch: Batch):
        # From training_step_g
        y = self._y
        y_hat = self._y_hat
        y_d_hat_r, y_d_hat_g, _, _ = self.model_d(y, y_hat.detach())

        with autocast(self.device.type, enabled=False):
            # Discriminator
            loss_disc, _losses_disc_r, _losses_disc_g = discriminator_loss(
                y_d_hat_r,
                y_d_hat_g,
            )
            loss_disc_all = loss_disc

            self.log("loss_disc_all", loss_disc_all)

            return loss_disc_all

    def validation_step(self, batch: Batch, batch_idx: int):
        val_loss = self.training_step_g(batch) + self.training_step_d(batch)
        self.log("val_loss", val_loss)

        # Generate audio examples
        for utt_idx, test_utt in enumerate(self._test_dataset):
            text = test_utt.phoneme_ids.unsqueeze(0).to(self.device)
            text_lengths = torch.LongTensor([len(test_utt.phoneme_ids)]).to(self.device)
            scales = [0.667, 1.0, 0.8]
            sid = (
                test_utt.speaker_id.to(self.device)
                if test_utt.speaker_id is not None
                else None
            )
            test_audio = self(text, text_lengths, scales, sid=sid).detach()

            # Scale to make louder in [-1, 1]
            test_audio = test_audio * (1.0 / max(0.01, abs(test_audio.max())))

            tag = test_utt.text or str(utt_idx)
            self.logger.experiment.add_audio(
                tag,
                test_audio,
                sample_rate=self.hparams.sample_rate,
            )

        return val_loss

    def configure_optimizers(self):
        optimizers = [
            torch.optim.AdamW(
                self.model_g.parameters(),
                lr=self.hparams.learning_rate,
                betas=self.hparams.betas,
                eps=self.hparams.eps,
            ),
            torch.optim.AdamW(
                self.model_d.parameters(),
                lr=self.hparams.learning_rate,
                betas=self.hparams.betas,
                eps=self.hparams.eps,
            ),
        ]
        schedulers = [
            torch.optim.lr_scheduler.ExponentialLR(
                optimizers[0],
                gamma=self.hparams.lr_decay,
            ),
            torch.optim.lr_scheduler.ExponentialLR(
                optimizers[1],
                gamma=self.hparams.lr_decay,
            ),
        ]

        return optimizers, schedulers

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = parent_parser.add_argument_group("VitsModel")
        parser.add_argument("--batch-size", type=int, required=True)
        parser.add_argument("--validation-split", type=float, default=0.1)
        parser.add_argument("--num-test-examples", type=int, default=5)
        parser.add_argument(
            "--max-phoneme-ids",
            type=int,
            help="Exclude utterances with phoneme id lists longer than this",
        )
        parser.add_argument("--hidden-channels", type=int, default=192)
        parser.add_argument("--inter-channels", type=int, default=192)
        parser.add_argument("--filter-channels", type=int, default=768)
        parser.add_argument("--n-layers", type=int, default=6)
        parser.add_argument("--n-heads", type=int, default=2)
        parser.add_argument(
            "--gin-channels",
            type=int,
            default=0,
            help="Speaker embedding size for multi-speaker models (default: 0 for single, 768 for multi)",
        )
        parser.add_argument(
            "--num-workers",
            type=int,
            default=min(16, os.cpu_count()),
            help="Number of workers for DataLoader",
        )
        parser.add_argument(
            "--use-duration-regularization",
            action="store_true",
            default=True,
            help="Use duration consistency regularization",
        )
        parser.add_argument(
            "--c-dur-consistency",
            type=float,
            default=0.01,
            help="Weight for duration consistency loss",
        )
        parser.add_argument(
            "--use-wavlm-discriminator",
            action="store_true",
            help="Use WavLM-based discriminator for enhanced perceptual quality",
        )
        parser.add_argument(
            "--wavlm-model",
            type=str,
            default="microsoft/wavlm-base",
            help="Pretrained WavLM model to use",
        )
        parser.add_argument(
            "--c-wavlm",
            type=float,
            default=1.0,
            help="Weight for WavLM discriminator loss",
        )
        parser.add_argument(
            "--wavlm-weight",
            type=float,
            default=0.5,
            help="Balance between WavLM and traditional discriminators",
        )
        parser.add_argument(
            "--use-bert-encoder",
            action="store_true",
            help="Use Japanese BERT encoder for contextual text understanding",
        )
        parser.add_argument(
            "--bert-model-name",
            type=str,
            default="cl-tohoku/bert-base-japanese-v3",
            help="Pretrained Japanese BERT model to use",
        )
        parser.add_argument(
            "--bert-weight",
            type=float,
            default=0.3,
            help="Weight for combining BERT features with phoneme embeddings",
        )
        parser.add_argument(
            "--use-flow-matching",
            action="store_true",
            help="Use Conditional Flow Matching instead of traditional normalizing flow",
        )
        parser.add_argument(
            "--c-flow-matching",
            type=float,
            default=1.0,
            help="Weight for flow matching loss",
        )
        return parent_parser
