import logging
from pathlib import Path

import pytorch_lightning as pl
import torch
from torch import autocast
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .commons import slice_segments
from .dataset import Batch, PiperDataset, SpeakerBalancedBatchSampler, UtteranceCollate
from .losses import discriminator_loss, feature_loss, generator_loss, kl_loss
from .mb_istft import PQMF
from .mel_processing import mel_spectrogram_torch, spec_to_mel_torch
from .models import (
    MultiPeriodDiscriminator,
    SynthesizerTrn,
    WavLMDiscriminator,
)
from .stft_loss import MultiResolutionSTFTLoss


# Optional wandb import with graceful fallback
try:
    import wandb

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

_LOGGER = logging.getLogger("vits.lightning")

# Memory cleanup frequency (iterations)
MEMORY_CLEANUP_FREQUENCY = 500


def normalize_id_tensor(
    raw_value: int | torch.Tensor | None,
    device: torch.device | None = None,
) -> torch.Tensor | None:
    """Normalize a speaker_id or language_id to a 1-D LongTensor of shape [1].

    Handles four input patterns produced by the dataset layer:
    - ``int``         -> ``torch.LongTensor([value])``
    - 0-D ``Tensor``  -> ``value.unsqueeze(0)``  (scalar from ``random_split`` Subset)
    - 1-D ``Tensor``  -> pass-through            (already shape [1])
    - ``None``        -> ``None``

    Optionally moves the result to *device*.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, torch.Tensor):
        t = raw_value.unsqueeze(0) if raw_value.dim() == 0 else raw_value
    else:
        t = torch.LongTensor([raw_value])
    if device is not None:
        t = t.to(device)
    return t


class VitsModel(pl.LightningModule):
    def __init__(
        self,
        num_symbols: int,
        num_speakers: int,
        num_languages: int = 1,
        audio_log_epochs: int = 1,  # Log audio samples to WandB every N epochs
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
        prosody_dim: int = 16,
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
        num_workers: int = 2,
        seed: int = 1234,
        num_test_examples: int = 2,
        validation_split: float = 0.1,
        max_phoneme_ids: int | None = None,
        validate_cache: bool = False,
        # WavLM Discriminator (enabled by default for improved audio quality)
        use_wavlm_discriminator: bool = True,
        wavlm_model_name: str = "microsoft/wavlm-base-plus",
        c_wavlm: float = 0.5,
        wavlm_every_n_steps: int = 1,
        # MB-iSTFT options
        c_sub_stft: float = 1.0,
        sub_stft_fft_sizes: tuple[int, ...] = (171, 384, 683),
        sub_stft_hop_sizes: tuple[int, ...] = (10, 30, 60),
        sub_stft_win_sizes: tuple[int, ...] = (60, 150, 300),
        **kwargs,
    ):
        super().__init__()
        self.automatic_optimization = (
            False  # Multiple optimizers require manual optimization
        )

        # Fix gin_channels BEFORE save_hyperparameters() so the correct value is saved
        # This fixes the bug where gin_channels=0 was saved for multi-speaker models
        if (num_speakers > 1 or num_languages > 1) and (gin_channels <= 0):
            gin_channels = 512

        self.save_hyperparameters()

        # Set up models
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
            n_languages=self.hparams.num_languages,
            gin_channels=self.hparams.gin_channels,
            use_sdp=self.hparams.use_sdp,
            prosody_dim=self.hparams.prosody_dim,
        )
        self.model_d = MultiPeriodDiscriminator(
            use_spectral_norm=self.hparams.use_spectral_norm
        )

        # WavLM Discriminator (optional)
        self.model_d_wavlm = None
        if self.hparams.use_wavlm_discriminator:
            _LOGGER.info(
                f"Initializing WavLM Discriminator with model: {self.hparams.wavlm_model_name}"
            )
            self.model_d_wavlm = WavLMDiscriminator(
                model_name=self.hparams.wavlm_model_name,
                source_sample_rate=self.hparams.sample_rate,
            )

        # MB-iSTFT: PQMF for GT analysis + sub-band STFT loss
        self.pqmf = PQMF(subbands=4)
        # Share PQMF instance with the decoder to avoid duplicate buffers
        self.model_g.dec.pqmf = self.pqmf
        self.sub_stft_loss = MultiResolutionSTFTLoss(
            fft_sizes=self.hparams.sub_stft_fft_sizes,
            hop_sizes=self.hparams.sub_stft_hop_sizes,
            win_sizes=self.hparams.sub_stft_win_sizes,
        )

        # Dataset splits
        self._train_dataset: Dataset | None = None
        self._val_dataset: Dataset | None = None
        self._test_dataset: Dataset | None = None
        self._load_datasets(validation_split, num_test_examples, max_phoneme_ids)

        # State kept between training optimizers
        self._y = None
        self._y_hat = None

    def _load_test_dataset(self, test_utterances_path: Path):
        """Load fixed test dataset for WandB audio logging.

        Ensures Japanese, English, and mixed sentences are all covered.
        Mixed sentences (language_id == -1) are automatically phonemized with ja-en.
        """
        import json

        from .dataset import Utterance

        utterances = []

        with open(test_utterances_path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line.strip())

                # Mixed sentences (language_id == -1) need phonemization
                if data.get("language_id", 0) == -1:
                    from piper_plus_g2p import get_phonemizer

                    phonemizer = get_phonemizer("ja-en")
                    phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(
                        data["text"]
                    )

                    # Load phoneme_id_map from config.json
                    config_path = self.hparams.dataset_dir / "config.json"
                    with open(config_path, encoding="utf-8") as cfg:
                        config = json.load(cfg)
                        pid_map = config["phoneme_id_map"]

                    # Convert phonemes to IDs
                    phoneme_ids = []
                    prosody_features = []
                    for phoneme, prosody_info in zip(
                        phonemes, prosody_info_list, strict=True
                    ):
                        if phoneme in pid_map:
                            ids = pid_map[phoneme]
                            phoneme_ids.extend(ids)
                            for _ in ids:
                                if prosody_info is not None:
                                    prosody_features.append(
                                        {
                                            "a1": prosody_info.a1,
                                            "a2": prosody_info.a2,
                                            "a3": prosody_info.a3,
                                        }
                                    )
                                else:
                                    prosody_features.append(None)

                    # Apply post-processing (BOS/EOS/padding)
                    phoneme_ids, prosody_features = phonemizer.post_process_ids(
                        phoneme_ids, prosody_features, pid_map
                    )

                    data["phoneme_ids"] = phoneme_ids
                    data["prosody_features"] = prosody_features
                    # Set language_id to ja (0) for mixed sentences (or detect from text)
                    data["language_id"] = config.get("language_id_map", {}).get("ja", 0)

                # Create Utterance object
                utt = Utterance(
                    phoneme_ids=torch.LongTensor(data["phoneme_ids"]),
                    audio_norm_path=None,  # Not needed for test set
                    audio_spec_path=None,
                    speaker_id=data.get("speaker_id", 0),
                    language_id=data.get("language_id", 0),
                    prosody_features=data.get("prosody_features"),
                    text=data["text"],  # Store original text for logging
                )
                utterances.append(utt)

        _LOGGER.info(
            f"Loaded {len(utterances)} fixed test utterances from {test_utterances_path}"
        )
        return utterances

    def _load_datasets(
        self,
        validation_split: float,
        num_test_examples: int,
        max_phoneme_ids: int | None = None,
    ):
        if self.hparams.dataset is None:
            _LOGGER.debug("No dataset to load")
            return

        validate_cache = self.hparams.get("validate_cache", False)

        # Try to load fixed test dataset first
        test_utterances_path = self.hparams.dataset_dir / "test_utterances.jsonl"
        if test_utterances_path.exists():
            self._test_dataset = self._load_test_dataset(test_utterances_path)
            # Load train/val datasets without test examples
            full_dataset = PiperDataset(
                self.hparams.dataset,
                max_phoneme_ids=max_phoneme_ids,
                validate_cache=validate_cache,
            )
            valid_set_size = int(len(full_dataset) * validation_split)
            train_set_size = len(full_dataset) - valid_set_size
            split_generator = torch.Generator().manual_seed(self.hparams.seed)
            self._train_dataset, self._val_dataset = random_split(
                full_dataset,
                [train_set_size, valid_set_size],
                generator=split_generator,
            )
        else:
            # Fallback: use random split (old behavior)
            _LOGGER.warning(
                f"Fixed test dataset not found at {test_utterances_path}, using random split"
            )
            full_dataset = PiperDataset(
                self.hparams.dataset,
                max_phoneme_ids=max_phoneme_ids,
                validate_cache=validate_cache,
            )
            valid_set_size = int(len(full_dataset) * validation_split)
            train_set_size = len(full_dataset) - valid_set_size - num_test_examples

            split_generator = torch.Generator().manual_seed(self.hparams.seed)
            self._train_dataset, self._test_dataset, self._val_dataset = random_split(
                full_dataset,
                [train_set_size, num_test_examples, valid_set_size],
                generator=split_generator,
            )

    def forward(
        self, text, text_lengths, scales, sid=None, lid=None, prosody_features=None
    ):
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
            lid=lid,
            prosody_features=prosody_features,
        )

        return audio

    def on_train_epoch_end(self):
        """Step LR schedulers at the end of each epoch.

        With automatic_optimization=False, Lightning does not step schedulers
        automatically. We must do it manually.
        """
        for sch in self.lr_schedulers():
            sch.step()

    def on_train_epoch_start(self):
        """エポック開始時にSpeakerBalancedBatchSamplerのepochを更新"""
        if (
            hasattr(self, "_train_batch_sampler")
            and self._train_batch_sampler is not None
        ):
            self._train_batch_sampler.set_epoch(self.current_epoch)
            _LOGGER.debug(
                "Set SpeakerBalancedBatchSampler epoch to %d", self.current_epoch
            )

    def train_dataloader(self):
        # Check if pin_memory should be disabled (for memory-constrained multi-GPU setups)
        pin_memory = not getattr(self.hparams, "no_pin_memory", False)

        collate_fn = UtteranceCollate(
            is_multispeaker=self.hparams.num_speakers > 1,
            segment_size=self.hparams.segment_size,
            is_multilanguage=self.hparams.num_languages > 1,
        )

        # マルチスピーカーでsamples_per_speakerが設定されている場合は
        # SpeakerBalancedBatchSamplerを使用
        samples_per_speaker = getattr(self.hparams, "samples_per_speaker", 0)
        if self.hparams.num_speakers > 1 and samples_per_speaker > 0:
            language_group_balance = getattr(
                self.hparams, "language_balanced_sampling", None
            )
            # CLI default is False (store_true); convert to None for auto-detection
            if language_group_balance is False:
                language_group_balance = None
            self._train_batch_sampler = SpeakerBalancedBatchSampler(
                self._train_dataset,
                batch_size=self.hparams.batch_size,
                samples_per_speaker=samples_per_speaker,
                drop_last=True,
                language_group_balance=language_group_balance,
            )
            _LOGGER.info(
                "Using SpeakerBalancedBatchSampler: batch_size=%d, samples_per_speaker=%d, "
                "speakers_per_batch=%d",
                self.hparams.batch_size,
                samples_per_speaker,
                self.hparams.batch_size // samples_per_speaker,
            )
            return DataLoader(
                self._train_dataset,
                collate_fn=collate_fn,
                batch_sampler=self._train_batch_sampler,
                num_workers=self.hparams.num_workers,
                pin_memory=pin_memory,
                persistent_workers=(self.hparams.num_workers > 0),
                prefetch_factor=(2 if self.hparams.num_workers > 0 else None),
            )
        else:
            # 従来の動作（ランダムサンプリング）
            self._train_batch_sampler = None
            return DataLoader(
                self._train_dataset,
                collate_fn=collate_fn,
                num_workers=self.hparams.num_workers,
                batch_size=self.hparams.batch_size,
                shuffle=True,
                pin_memory=pin_memory,
                persistent_workers=(self.hparams.num_workers > 0),
                prefetch_factor=(2 if self.hparams.num_workers > 0 else None),
            )

    def val_dataloader(self):
        # Check if pin_memory should be disabled (for memory-constrained multi-GPU setups)
        pin_memory = not getattr(self.hparams, "no_pin_memory", False)
        return DataLoader(
            self._val_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
                is_multilanguage=self.hparams.num_languages > 1,
            ),
            num_workers=self.hparams.num_workers,
            batch_size=self.hparams.batch_size,
            pin_memory=pin_memory,
            persistent_workers=(self.hparams.num_workers > 0),
            prefetch_factor=(2 if self.hparams.num_workers > 0 else None),
        )

    def test_dataloader(self):
        return DataLoader(
            self._test_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
                is_multilanguage=self.hparams.num_languages > 1,
            ),
            num_workers=self.hparams.num_workers,
            batch_size=self.hparams.batch_size,
        )

    def training_step(self, batch: Batch, batch_idx: int):
        # Manual optimization for multiple optimizers
        opt_g, opt_d = self.optimizers()

        # Train generator
        opt_g.zero_grad()
        loss_g = self.training_step_g(batch)
        self.manual_backward(loss_g)
        opt_g.step()

        # Train discriminator
        opt_d.zero_grad()
        loss_d = self.training_step_d(batch)
        self.manual_backward(loss_d)
        opt_d.step()

        # Clear instance variables to release references
        self._y = None
        self._y_hat = None

        # Periodic memory cleanup to prevent fragmentation
        if batch_idx % MEMORY_CLEANUP_FREQUENCY == 0:
            if torch.cuda.is_available():
                torch.cuda.synchronize()  # Wait for GPU operations to complete
                torch.cuda.empty_cache()
                # Use info level only for first cleanup, then debug
                if batch_idx == 0:
                    _LOGGER.info(
                        f"Memory cache clearing enabled every {MEMORY_CLEANUP_FREQUENCY} iterations"
                    )
                else:
                    _LOGGER.debug(f"Memory cache cleared at iteration {batch_idx}")

    def _log_with_batch_info(
        self, key: str, value, batch: Batch = None, batch_size: int = None
    ):
        """Helper method to log with proper batch_size and sync_dist settings."""
        if batch_size is None:
            if batch is not None:
                batch_size = batch.phoneme_ids.size(0)
            else:
                batch_size = self._y.size(0) if hasattr(self, "_y") else None

        sync_dist = self.trainer.world_size > 1
        self.log(key, value, batch_size=batch_size, sync_dist=sync_dist)

    def _get_wandb_logger(self):
        """Get WandB logger from trainer's logger list, if available.

        Returns:
            WandbLogger instance or None if not found/unavailable
        """
        if not WANDB_AVAILABLE:
            return None

        # PyTorch Lightning 2.x uses trainer.loggers (plural) for multiple loggers
        if hasattr(self.trainer, "loggers") and self.trainer.loggers:
            loggers = self.trainer.loggers
        else:
            # Fallback to trainer.logger (singular)
            trainer_logger = self.trainer.logger
            loggers = (
                trainer_logger if isinstance(trainer_logger, list) else [trainer_logger]
            )

        for logger in loggers:
            # Check by class name to avoid import dependency
            if logger.__class__.__name__ == "WandbLogger":
                return logger

        return None

    def training_step_g(self, batch: Batch):
        (
            x,
            x_lengths,
            y,
            _,
            spec,
            spec_lengths,
            speaker_ids,
            language_ids,
            prosody_features,
        ) = (
            batch.phoneme_ids,
            batch.phoneme_lengths,
            batch.audios,
            batch.audio_lengths,
            batch.spectrograms,
            batch.spectrogram_lengths,
            batch.speaker_ids if batch.speaker_ids is not None else None,
            batch.language_ids if batch.language_ids is not None else None,
            batch.prosody_features if batch.prosody_features is not None else None,
        )
        g_output = self.model_g(
            x,
            x_lengths,
            spec,
            spec_lengths,
            speaker_ids,
            lid=language_ids,
            prosody_features=prosody_features,
        )
        y_hat = g_output.waveform
        l_length = g_output.duration_loss
        ids_slice = g_output.ids_slice
        z_mask = g_output.y_mask
        z_p = g_output.latents[1]
        m_p = g_output.latents[2]
        logs_p = g_output.latents[3]
        logs_q = g_output.latents[5]
        o_mb = g_output.decoder_subbands
        self._y_hat = y_hat.contiguous()

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

        # Ensure contiguous memory layout to prevent fragmentation
        y = y.contiguous()
        y_hat = y_hat.contiguous()

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

            loss_gen_all = loss_gen + loss_fm + loss_mel + loss_dur + loss_kl

            # MB-iSTFT: sub-band STFT loss
            if o_mb is not None:
                y_mb = self.pqmf.analysis(y)  # GT subbands [B, 4, T//4]
                loss_sub_stft = self.sub_stft_loss(o_mb, y_mb) * self.hparams.c_sub_stft
                loss_gen_all = loss_gen_all + loss_sub_stft
                self._log_with_batch_info("loss_sub_stft", loss_sub_stft, batch)

            # WavLM Discriminator loss (optional, computed every N steps)
            if self.model_d_wavlm is not None and (
                self.global_step % self.hparams.wavlm_every_n_steps == 0
            ):
                _y_d_hat_r_wlm, y_d_hat_g_wlm, fmap_r_wlm, fmap_g_wlm = (
                    self.model_d_wavlm(y, y_hat)
                )
                loss_fm_wavlm = feature_loss(fmap_r_wlm, fmap_g_wlm)
                loss_gen_wavlm, _ = generator_loss(y_d_hat_g_wlm)
                # Scale up loss to compensate for reduced frequency
                loss_wavlm = (
                    (loss_gen_wavlm + loss_fm_wavlm)
                    * self.hparams.c_wavlm
                    * self.hparams.wavlm_every_n_steps
                )
                loss_gen_all = loss_gen_all + loss_wavlm

                # Log WavLM losses
                self._log_with_batch_info("loss_gen_wavlm", loss_gen_wavlm, batch)
                self._log_with_batch_info("loss_fm_wavlm", loss_fm_wavlm, batch)

            self._log_with_batch_info("loss_gen_all", loss_gen_all, batch)

            return loss_gen_all

    def training_step_d(self, batch: Batch):
        # From training_step_g
        y = self._y
        y_hat = self._y_hat
        # Ensure detached tensors are contiguous
        y_hat_detached = y_hat.detach().contiguous()
        y_d_hat_r, y_d_hat_g, _, _ = self.model_d(y, y_hat_detached)

        with autocast(self.device.type, enabled=False):
            # Discriminator
            loss_disc, _losses_disc_r, _losses_disc_g = discriminator_loss(
                y_d_hat_r, y_d_hat_g
            )
            loss_disc_all = loss_disc

            # WavLM Discriminator loss (optional, computed every N steps)
            if self.model_d_wavlm is not None and (
                self.global_step % self.hparams.wavlm_every_n_steps == 0
            ):
                y_d_hat_r_wlm, y_d_hat_g_wlm, _, _ = self.model_d_wavlm(
                    y, y_hat_detached
                )
                loss_disc_wavlm, _, _ = discriminator_loss(y_d_hat_r_wlm, y_d_hat_g_wlm)
                loss_disc_all = (
                    loss_disc_all
                    + loss_disc_wavlm
                    * self.hparams.c_wavlm
                    * self.hparams.wavlm_every_n_steps
                )

                # Log WavLM discriminator loss
                self._log_with_batch_info("loss_disc_wavlm", loss_disc_wavlm, batch)

            self._log_with_batch_info("loss_disc_all", loss_disc_all, batch)

            return loss_disc_all

    def validation_step(self, batch: Batch, batch_idx: int):
        # Temporarily suppress self.log to prevent training_step_g/d from
        # logging training-named metrics (loss_gen_all, loss_disc_all, etc.)
        # during validation.  We restore self.log immediately after.
        _orig_log = self.log
        self.log = lambda *_args, **_kwargs: None  # no-op
        try:
            loss_g = self.training_step_g(batch)
            loss_d = self.training_step_d(batch)
        finally:
            self.log = _orig_log

        val_loss = loss_g + loss_d
        self._log_with_batch_info("val_loss", val_loss, batch)
        return val_loss

    def on_validation_epoch_end(self):
        """Log audio samples to WandB at the end of validation epoch.

        This is called after all validation batches are processed,
        avoiding blocking the validation loop with audio generation.

        DDP safety: rank 0 performs audio generation and WandB upload inside
        the is_global_zero block, then ALL ranks sync at a barrier. Without
        the barrier, Lightning may advance ranks 1-3 to the next training step
        while rank 0 is still uploading to WandB, causing NCCL ALLREDUCE timeout.
        """
        # Only rank 0 does audio generation and WandB logging.
        # Wrapped in a block (not early return) so the barrier below runs on all ranks.
        if self.trainer.is_global_zero:
            should_log = (
                self.hparams.audio_log_epochs > 0
                and self.current_epoch % self.hparams.audio_log_epochs == 0
            )
            wandb_logger = self._get_wandb_logger() if should_log else None

            if should_log and wandb_logger is not None and WANDB_AVAILABLE:
                import json

                try:
                    wandb_audio_data = []

                    # Build language map from config once (outside loop)
                    language_map = {}
                    try:
                        config_path = self.hparams.dataset_dir / "config.json"
                        with open(config_path, encoding="utf-8") as cfg:
                            cfg_data = json.load(cfg)
                        lid_map = cfg_data.get("language_id_map", {})
                        for lang_name, lang_id in lid_map.items():
                            language_map[lang_id] = lang_name
                    except Exception:
                        pass
                    if not language_map:
                        language_map = {
                            i: f"lang_{i}"
                            for i in range(getattr(self.hparams, "num_languages", 1))
                        }

                    with torch.no_grad():  # Disable gradient computation
                        for utt_idx, test_utt in enumerate(self._test_dataset):
                            # Generate audio
                            text = test_utt.phoneme_ids.unsqueeze(0).to(self.device)
                            text_lengths = torch.LongTensor(
                                [len(test_utt.phoneme_ids)]
                            ).to(self.device)
                            scales = [0.667, 1.0, 0.8]
                            sid = normalize_id_tensor(test_utt.speaker_id, self.device)
                            lid = normalize_id_tensor(test_utt.language_id, self.device)

                            test_audio = self(
                                text, text_lengths, scales, sid=sid, lid=lid
                            ).detach()
                            test_audio = test_audio * (
                                1.0 / max(0.01, abs(test_audio.max()))
                            )

                            # Convert to numpy (CPU)
                            audio_np = test_audio.squeeze().cpu().numpy()

                            # Build metadata
                            text_str = (
                                test_utt.text if test_utt.text else f"sample_{utt_idx}"
                            )
                            speaker_str = (
                                f"spk={sid.item()}" if sid is not None else "single"
                            )
                            lang_str = language_map.get(
                                lid.item() if lid is not None else 0, "unknown"
                            )
                            noise_scale, length_scale, noise_scale_w = scales

                            # Create WandB audio
                            caption = f"{text_str} | {speaker_str} | {lang_str} | noise={noise_scale:.3f},len={length_scale:.2f},noisew={noise_scale_w:.2f}"
                            wandb_audio = wandb.Audio(
                                audio_np,
                                sample_rate=self.hparams.sample_rate,
                                caption=caption,
                            )

                            wandb_audio_data.append(
                                [
                                    text_str,
                                    speaker_str,
                                    lang_str,
                                    self.current_epoch,
                                    self.global_step,
                                    wandb_audio,
                                ]
                            )

                            # Aggressive per-sample GPU memory cleanup
                            del test_audio, text, text_lengths, sid, lid
                            if torch.cuda.is_available():
                                torch.cuda.synchronize()
                                torch.cuda.empty_cache()

                    # Log all samples as table
                    if wandb_audio_data:
                        columns = [
                            "text",
                            "speaker",
                            "language",
                            "epoch",
                            "step",
                            "audio",
                        ]
                        table = wandb.Table(columns=columns, data=wandb_audio_data)
                        wandb_logger.experiment.log(
                            {
                                f"validation_audio_samples/epoch_{self.current_epoch}": table
                            },
                            step=self.global_step,
                        )
                        _LOGGER.info(
                            f"Logged {len(wandb_audio_data)} audio samples to WandB at epoch {self.current_epoch}"
                        )

                    # Final cleanup
                    del wandb_audio_data
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                        torch.cuda.empty_cache()

                except Exception as e:
                    _LOGGER.warning(f"Failed to log audio to WandB: {e}")

        # DDP barrier: all ranks wait here so rank 0's WandB I/O completes before
        # any rank advances to the next training step.
        if self.trainer.world_size > 1:
            torch.distributed.barrier()

    def configure_optimizers(self):
        # Freeze Duration Predictor if requested
        freeze_dp = getattr(self.hparams, "freeze_dp", False)
        if freeze_dp:
            dp_frozen_count = 0
            for name, param in self.model_g.named_parameters():
                if name.startswith("dp."):
                    param.requires_grad = False
                    dp_frozen_count += 1
            _LOGGER.info(
                "Frozen %d Duration Predictor parameters (--freeze-dp)",
                dp_frozen_count,
            )

        # Generator optimizer: only trainable parameters
        gen_params = [p for p in self.model_g.parameters() if p.requires_grad]

        # Collect discriminator parameters (including WavLM if enabled)
        d_params = list(self.model_d.parameters())
        if self.model_d_wavlm is not None:
            d_params = d_params + list(self.model_d_wavlm.parameters())

        optimizers = [
            torch.optim.AdamW(
                gen_params,
                lr=self.hparams.learning_rate,
                betas=self.hparams.betas,
                eps=self.hparams.eps,
                fused=torch.cuda.is_available(),
            ),
            torch.optim.AdamW(
                d_params,
                lr=self.hparams.learning_rate,
                betas=self.hparams.betas,
                eps=self.hparams.eps,
                fused=torch.cuda.is_available(),
            ),
        ]
        schedulers = [
            torch.optim.lr_scheduler.ExponentialLR(
                optimizers[0], gamma=self.hparams.lr_decay
            ),
            torch.optim.lr_scheduler.ExponentialLR(
                optimizers[1], gamma=self.hparams.lr_decay
            ),
        ]

        return optimizers, schedulers

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = parent_parser.add_argument_group("VitsModel")
        parser.add_argument("--batch-size", type=int, required=True)
        parser.add_argument("--validation-split", type=float, default=0.1)
        parser.add_argument("--num-test-examples", type=int, default=2)
        parser.add_argument(
            "--audio-log-epochs",
            type=int,
            default=1,
            help="Log audio samples to WandB every N epochs (default: 1, 0=disable)",
        )
        parser.add_argument(
            "--max-phoneme-ids",
            type=int,
            help="Exclude utterances with phoneme id lists longer than this",
        )
        parser.add_argument(
            "--validate-cache",
            action="store_true",
            default=False,
            help="At startup, load-test every cached .pt file and skip corrupted ones "
            "(slow for large datasets; use once after suspected corruption).",
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
            "--prosody-dim",
            type=int,
            default=16,
            help="Dimension for prosody feature projection (A1/A2/A3). Default: 16 (enabled)",
        )
        parser.add_argument(
            "--num-workers",
            type=int,
            default=2,
            help="Number of workers for DataLoader (default: 2 for parallel data loading). "
            "Set to 0 for single-threaded loading if shared memory is limited.",
        )
        return parent_parser
