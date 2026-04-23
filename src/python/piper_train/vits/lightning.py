import logging
import types
from pathlib import Path

import numpy as np
import pytorch_lightning as pl
import torch
import torchaudio.functional as AF
from torch import autocast
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .commons import slice_segments
from .dataset import Batch, PiperDataset, SpeakerBalancedBatchSampler, UtteranceCollate
from .losses import discriminator_loss, feature_loss, generator_loss, kl_loss
from .mel_processing import mel_spectrogram_torch, spec_to_mel_torch
from .models import (
    MultiPeriodDiscriminator,
    SynthesizerTrn,
    WavLMDiscriminator,
)


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
        style_vector_dim: int = 0,
        style_condition_dropout: float = 0.0,
        style_condition_mode: str = "global",
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
        # PE-A emotion perceptual loss (Phase 4 / PR-F)
        # All weights default to 0.0 so the loss is disabled unless the user
        # opts in via ``--pea-emotion-*`` flags in ``__main__.py``.
        pea_emotion_loss_weight: float = 0.0,
        pea_emotion_centroid_weight: float = 0.0,
        pea_emotion_margin_weight: float = 0.0,
        pea_emotion_style_bank: str | Path | None = None,
        pea_emotion_model_name: str = "facebook/pe-av-small",
        pea_emotion_sample_rate: int = 16000,
        pea_emotion_loss_every_n_steps: int = 1,
        pea_emotion_warmup_steps: int = 0,
        pea_emotion_margin: float = 0.1,
        **kwargs,
    ):
        super().__init__()
        self.automatic_optimization = (
            False  # Multiple optimizers require manual optimization
        )
        if style_condition_mode not in {"global", "text"}:
            raise ValueError(
                "style_condition_mode must be either 'global' or 'text', "
                f"got {style_condition_mode!r}"
            )

        # Fix gin_channels BEFORE save_hyperparameters() so the correct value is saved
        # This fixes the bug where gin_channels=0 was saved for multi-speaker models
        if (num_speakers > 1 or num_languages > 1) and (gin_channels <= 0):
            gin_channels = 512
        if (style_vector_dim > 0) and (gin_channels <= 0):
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
            style_vector_dim=self.hparams.style_vector_dim,
            style_condition_dropout=self.hparams.style_condition_dropout,
            style_condition_mode=self.hparams.style_condition_mode,
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

        # PE-A emotion perceptual loss state (Phase 4 / PR-F).
        # ``_pea_emotion_model`` is lazily loaded the first time
        # ``_compute_pea_emotion_loss`` is invoked (see P4-T02).
        # Must be assigned AFTER save_hyperparameters() so the hparams
        # snapshot of the 9 pea_emotion_* kwargs is already captured.
        self._pea_emotion_model = None
        self._pea_emotion_to_idx: dict[str, int] = {}
        self._init_pea_emotion_loss()

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

    # ------------------------------------------------------------------
    # PE-A emotion perceptual loss (Phase 4 / PR-F)
    # ------------------------------------------------------------------

    def _pea_emotion_loss_enabled(self) -> bool:
        """Return True when any PE-A emotion loss weight is positive.

        Fork-compatible auto-enable: the three loss weights act as implicit
        enable flags so we do not need a separate ``--pea-emotion-enabled``
        CLI option. All weights defaulting to 0.0 keeps the feature off for
        existing training runs.
        """
        return (
            self.hparams.pea_emotion_loss_weight > 0
            or self.hparams.pea_emotion_centroid_weight > 0
            or self.hparams.pea_emotion_margin_weight > 0
        )

    def _init_pea_emotion_loss(self) -> None:
        """Load the style bank and register emotion centroids as buffers.

        Called once from ``__init__`` after ``save_hyperparameters()``. When
        the loss is disabled (all weights == 0) this is a no-op so existing
        training runs see zero overhead.

        Raises
        ------
        ValueError
            If the loss is enabled but ``--pea-emotion-style-bank`` was not
            supplied.
        """
        if not self._pea_emotion_loss_enabled():
            return

        style_bank = self.hparams.pea_emotion_style_bank
        if not style_bank:
            raise ValueError(
                "--pea-emotion-style-bank is required when PE-A emotion loss is enabled"
            )

        # Use the shared loader so the .npz schema stays in lock-step with
        # piper_train.tools.build_pea_style_bank / validate_style_bank.
        from piper_train.perception.pea_loader import load_style_bank

        emotion_names, emotion_centroids, global_centroid = load_style_bank(
            Path(style_bank)
        )

        self._pea_emotion_to_idx = {
            name: idx for idx, name in enumerate(emotion_names)
        }
        # L2-normalise both centroid arrays before registering so downstream
        # cosine similarity / direction maths consume unit-norm vectors.
        self.register_buffer(
            "pea_emotion_global_centroid",
            F.normalize(global_centroid, dim=-1),
            persistent=False,
        )
        self.register_buffer(
            "pea_emotion_centroids",
            F.normalize(emotion_centroids, dim=-1),
            persistent=False,
        )
        _LOGGER.info(
            "PE-A emotion loss enabled: style_bank=%s, emotions=%s",
            style_bank,
            ",".join(emotion_names),
        )

    def _ensure_pea_emotion_model(self):
        """Lazily load the PE-A audio model.

        The model is loaded on the first call and cached on the instance.
        Call sites should invoke this from
        ``_compute_pea_emotion_loss`` so that when the loss is disabled no
        PE-A weights are ever downloaded or held in GPU memory.

        The loaded model is moved to ``self.device`` and its audio embedder
        is monkey-patched to use :func:`grad_enabled_embedder_forward` so
        gradients flow back to ``y_hat`` while PE-A weights stay frozen.
        """
        if self._pea_emotion_model is not None:
            return self._pea_emotion_model

        from piper_train.perception.pea_loader import (
            grad_enabled_embedder_forward,
            load_pea_emotion_model,
        )

        model = load_pea_emotion_model(
            self.hparams.pea_emotion_model_name,
            device=self.device,
        )

        # Rebind the DAC embedder to the grad-enabled forward (fork 314b3355
        # approach). The attribute path mirrors Transformers PE-A.
        try:
            embedder = model.audio_model.audio_encoder.embedder
        except AttributeError as err:
            raise AttributeError(
                "Unexpected PE-A model layout: expected "
                "model.audio_model.audio_encoder.embedder. "
                f"Underlying error: {err}"
            ) from err
        embedder.forward = types.MethodType(
            grad_enabled_embedder_forward, embedder
        )

        self._pea_emotion_model = model
        return self._pea_emotion_model

    def _compute_pea_emotion_loss(
        self,
        y_hat: torch.Tensor,
        batch: Batch,
    ) -> torch.Tensor | None:
        """Compute the 3-term PE-A emotion perceptual loss.

        Composition (fork 314b3355 ``lightning.py:298-382`` faithful port)::

            loss = w_dir      * (1 - cos(e_dir,     t_dir))
                 + w_centroid * (1 - cos(embeddings, target_centroids))
                 + w_margin   * ReLU(margin + max_other_sim - target_sim)

        where ``e_dir = normalize(embeddings - global_centroid)`` and
        ``t_dir = normalize(target_centroids - global_centroid)``.

        Ticket design: this method contains the numerical calculation only.
        Warmup / ``every_n_steps`` gating lives in ``training_step_g`` (see
        P4-T03) so the loss computation stays pure and unit-testable.

        Returns
        -------
        torch.Tensor | None
            Scalar tensor when loss is produced. ``None`` when the loss is
            disabled (all weights ≤ 0), the batch carries no ``emotions``
            field, no sample's emotion is in the style bank, or the loss
            value contains ``NaN``/``Inf`` (guard with warning log).
        """

        # --- Guard 1: fully disabled → zero overhead bail-out ---
        if not self._pea_emotion_loss_enabled():
            return None

        emotions = getattr(batch, "emotions", None)
        # --- Guard 2: no emotion labels in this batch ---
        if not emotions:
            return None

        # Filter batch samples that have a label present in the style bank.
        valid_indices = [
            idx
            for idx, emotion in enumerate(emotions)
            if emotion in self._pea_emotion_to_idx
        ]
        if not valid_indices:
            return None

        sample_indices = torch.as_tensor(valid_indices, device=y_hat.device)
        emotion_indices = torch.as_tensor(
            [self._pea_emotion_to_idx[emotions[idx]] for idx in valid_indices],
            device=y_hat.device,
            dtype=torch.long,
        )

        # --- Resample audio to PE-A's expected rate (16 kHz default) ---
        # y_hat is typically [B, 1, T] from the generator; index_select on
        # dim 0 keeps the channel axis intact which torchaudio handles fine.
        audio = y_hat.index_select(0, sample_indices).float()
        if self.hparams.sample_rate != self.hparams.pea_emotion_sample_rate:
            audio = AF.resample(
                audio,
                orig_freq=int(self.hparams.sample_rate),
                new_freq=int(self.hparams.pea_emotion_sample_rate),
            )

        # --- Extract L2-normalised embeddings (DAC gradient-control inside
        # the embedder's monkey-patched forward) ---
        pea_model = self._ensure_pea_emotion_model()
        embeddings = pea_model.get_audio_embeds(audio)
        # ModelOutput fallback: some wrapper variants return an object with
        # an ``audio_embeds`` attribute instead of a raw tensor.
        if hasattr(embeddings, "audio_embeds"):
            embeddings = embeddings.audio_embeds
        embeddings = F.normalize(embeddings.float(), dim=-1)

        # --- Gather target centroids ---
        centroids = self.pea_emotion_centroids.to(
            device=embeddings.device, dtype=embeddings.dtype
        )
        global_centroid = self.pea_emotion_global_centroid.to(
            device=embeddings.device, dtype=embeddings.dtype
        )
        target_centroids = centroids.index_select(0, emotion_indices)

        # --- 3-term composition ---
        loss = embeddings.new_zeros(())

        # Direction loss (always computed to give us a scalar for logging,
        # but only added to the total when w_direction > 0).
        target_dirs = F.normalize(
            target_centroids - global_centroid.unsqueeze(0), dim=-1
        )
        embedding_dirs = F.normalize(
            embeddings - global_centroid.unsqueeze(0), dim=-1
        )
        loss_dir = (
            1.0 - F.cosine_similarity(embedding_dirs, target_dirs, dim=-1).mean()
        )
        if self.hparams.pea_emotion_loss_weight > 0:
            loss = loss + loss_dir * self.hparams.pea_emotion_loss_weight
            self._log_with_batch_info("loss_pea_emotion_dir", loss_dir, batch)

        # Centroid loss: 1 - cos(embedding, target) — fork implementation
        # uses angular distance, NOT L2 (norm-invariant, more stable under
        # SimCLR/CLIP-style conventions). See P4-T02 §6.1 for rationale.
        if self.hparams.pea_emotion_centroid_weight > 0:
            loss_centroid = 1.0 - F.cosine_similarity(
                embeddings, target_centroids, dim=-1
            ).mean()
            loss = loss + loss_centroid * self.hparams.pea_emotion_centroid_weight
            self._log_with_batch_info(
                "loss_pea_emotion_centroid", loss_centroid, batch
            )

        # Margin hinge: push ``target_similarity`` at least ``margin``
        # ahead of the best non-target centroid. ``masked_fill`` avoids
        # touching the ``similarities`` tensor in-place so autograd stays
        # happy (fork 314b3355 uses the same pattern).
        if self.hparams.pea_emotion_margin_weight > 0:
            similarities = embeddings @ centroids.transpose(0, 1)
            target_similarity = similarities.gather(
                1, emotion_indices[:, None]
            )
            other_similarities = similarities.masked_fill(
                F.one_hot(
                    emotion_indices, num_classes=centroids.size(0)
                ).bool(),
                -1.0,
            )
            max_other_similarity = other_similarities.max(
                dim=1, keepdim=True
            ).values
            loss_margin = F.relu(
                self.hparams.pea_emotion_margin
                + max_other_similarity
                - target_similarity
            ).mean()
            loss = loss + loss_margin * self.hparams.pea_emotion_margin_weight
            self._log_with_batch_info("loss_pea_emotion_margin", loss_margin, batch)

        # --- NaN/Inf guard: skip this step if the loss degenerated ---
        if not torch.isfinite(loss).all():
            _LOGGER.warning(
                "PE-A emotion loss produced non-finite value at step=%d; "
                "skipping loss contribution for this step.",
                int(self.global_step),
            )
            return None

        self._log_with_batch_info("loss_pea_emotion", loss, batch)
        return loss

    def forward(
        self,
        text,
        text_lengths,
        scales,
        sid=None,
        lid=None,
        prosody_features=None,
        style_vector=None,
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
            style_vector=style_vector,
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
            style_vectors,
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
            batch.style_vectors if batch.style_vectors is not None else None,
        )
        (
            y_hat,
            l_length,
            _attn,
            ids_slice,
            _x_mask,
            z_mask,
            (_z, z_p, m_p, logs_p, _m_q, logs_q),
        ) = self.model_g(
            x,
            x_lengths,
            spec,
            spec_lengths,
            speaker_ids,
            lid=language_ids,
            prosody_features=prosody_features,
            style_vector=style_vectors,
        )
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

            # PE-A emotion perceptual loss (Phase 4 / PR-F).
            # Warmup + every_n_steps gating live HERE (not inside
            # _compute_pea_emotion_loss) per P4-T03 design: the loss method
            # stays a pure numerical function, training_step_g owns the
            # scheduling. When the loss is fully disabled the
            # _pea_emotion_loss_enabled() check short-circuits so there is
            # zero overhead for existing training runs.
            loss_pea_emotion = None
            if self._pea_emotion_loss_enabled():
                warmup_steps = int(self.hparams.pea_emotion_warmup_steps)
                every_n_steps = max(
                    1, int(self.hparams.pea_emotion_loss_every_n_steps)
                )
                if (
                    self.global_step >= warmup_steps
                    and self.global_step % every_n_steps == 0
                ):
                    loss_pea_emotion = self._compute_pea_emotion_loss(
                        y_hat, batch
                    )

            if loss_pea_emotion is not None:
                # Scale up by every_n_steps so the effective gradient
                # magnitude stays consistent regardless of skip-step cadence
                # (fork 314b3355 uses the same multiplier pattern for WavLM
                # above and for PE-A in its own implementation).
                loss_pea_emotion_scaled = loss_pea_emotion * max(
                    1, int(self.hparams.pea_emotion_loss_every_n_steps)
                )
                loss_gen_all = loss_gen_all + loss_pea_emotion_scaled

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

    def on_after_backward(self) -> None:
        """Zero gradients when non-finite values are detected.

        PE-A emotion perceptual loss goes through a frozen external model
        (PE-A / DAC) which, in rare cases, produces NaN/Inf gradients during
        early training. Without this hook a single poisoned step could
        propagate NaNs throughout the optimizer state and permanently break
        training.

        The hook only runs when PE-A loss is enabled (so existing training
        flows see no behaviour change) and iterates model parameters until
        it finds a non-finite gradient. When found it zeros ALL gradients
        for this step via ``zero_grad(set_to_none=True)`` — equivalent to a
        skip-step — and emits a WARNING log.
        """
        if not self._pea_emotion_loss_enabled():
            return

        for name, param in self.named_parameters():
            grad = param.grad
            if grad is None:
                continue
            if not torch.isfinite(grad).all():
                _LOGGER.warning(
                    "PE-A emotion loss produced non-finite gradient at "
                    "step=%d (param=%s); zeroing all gradients for this step.",
                    int(self.global_step),
                    name,
                )
                self.zero_grad(set_to_none=True)
                return

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
            "--style-vector-dim",
            type=int,
            default=0,
            help="Dimension of optional utterance-level style vectors. Default: 0 (disabled, backwards-compatible).",
        )
        parser.add_argument(
            "--style-condition-dropout",
            type=float,
            default=0.0,
            help="Dropout probability for style-vector conditioning during training. Default: 0.0.",
        )
        parser.add_argument(
            "--style-condition-mode",
            choices=("text", "global"),
            default="global",
            help=(
                "Where to inject utterance-level style vectors. "
                "'global' adds projected style to VITS global conditioning g; "
                "'text' adds projected style to the scaled text encoder input."
            ),
        )
        # PE-A emotion perceptual loss (Phase 4 / PR-F) — all disabled by
        # default. Loss is implicitly enabled when ANY of the three weights
        # is > 0. ``--pea-emotion-style-bank`` becomes required in that
        # case (enforced by VitsModel._init_pea_emotion_loss()).
        parser.add_argument(
            "--pea-emotion-loss-weight",
            type=float,
            default=0.0,
            help=(
                "Weight for PE-A generated-audio direction loss toward the "
                "target emotion. Default: 0.0 (disabled)."
            ),
        )
        parser.add_argument(
            "--pea-emotion-centroid-weight",
            type=float,
            default=0.0,
            help=(
                "Weight for PE-A generated-audio attraction to the target "
                "emotion centroid (1 - cosine). Default: 0.0 (disabled)."
            ),
        )
        parser.add_argument(
            "--pea-emotion-margin-weight",
            type=float,
            default=0.0,
            help=(
                "Weight for PE-A target-vs-other emotion centroid hinge "
                "margin loss. Default: 0.0 (disabled)."
            ),
        )
        parser.add_argument(
            "--pea-emotion-style-bank",
            default=None,
            help=(
                "Path to a PE-A style bank .npz (schema: emotion_names, "
                "emotion_centroids, global_centroid). Required when any "
                "pea-emotion weight > 0."
            ),
        )
        parser.add_argument(
            "--pea-emotion-model-name",
            default="facebook/pe-av-small",
            help="HuggingFace model name for PE-A (default: facebook/pe-av-small).",
        )
        parser.add_argument(
            "--pea-emotion-sample-rate",
            type=int,
            default=16000,
            help="Sample rate used by the PE-A emotion model (default: 16000).",
        )
        parser.add_argument(
            "--pea-emotion-loss-every-n-steps",
            type=int,
            default=1,
            help=(
                "Compute PE-A emotion loss every N generator steps "
                "(default: 1; recommended 4 for speed)."
            ),
        )
        parser.add_argument(
            "--pea-emotion-warmup-steps",
            type=int,
            default=0,
            help=(
                "Delay PE-A emotion loss until this many global steps have "
                "elapsed (default: 0; recommended 2000)."
            ),
        )
        parser.add_argument(
            "--pea-emotion-margin",
            type=float,
            default=0.1,
            help="Cosine margin for PE-A target-vs-other margin loss (default: 0.1).",
        )
        parser.add_argument(
            "--num-workers",
            type=int,
            default=2,
            help="Number of workers for DataLoader (default: 2 for parallel data loading). "
            "Set to 0 for single-threaded loading if shared memory is limited.",
        )
        return parent_parser
