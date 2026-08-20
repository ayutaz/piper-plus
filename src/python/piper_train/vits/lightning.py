import contextlib
import copy
import logging
import os
from pathlib import Path

import numpy as np
import pytorch_lightning as pl
import torch
from torch import autocast
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .commons import (
    migrate_prefilm_decoder_cond,
    migrate_prefilm_optimizer_states,
    normalize_checkpoint_state_dict,
    optimizer_states_need_migration,
    slice_segments,
)
from .dataset import Batch, PiperDataset, SpeakerBalancedBatchSampler, UtteranceCollate
from .losses import (
    adv_speaker_classifier_loss_d,
    adv_speaker_classifier_loss_g,
    adv_speaker_classifier_stats,
    build_latent_filling_embeddings,
    build_same_language_permutation,
    dino_loss,
    discriminator_loss,
    f0_prediction_loss,
    f0_teacher_forcing_prob,
    feature_loss,
    gather_speaker_loss_inputs,
    generator_loss,
    jcu_split,
    kl_loss,
    mel_speaker_consistency_loss,
    should_run_latent_filling_step,
    speaker_consistency_loss,
    speaker_infonce_loss,
    swap_spk_ramp_weight,
)
from .mb_istft import PQMF, carrier_source_regularization
from .mel_processing import mel_spectrogram_torch, spec_to_mel_torch
from .models import (
    MRD_HIRES_RESOLUTIONS,
    AdversarialSpeakerClassifier,
    MultiPeriodDiscriminator,
    MultiResolutionSpectrogramDiscriminator,
    SynthesizerTrn,
    WavLMDiscriminator,
)
from .stft_loss import HighBandSTFTLoss, MultiResolutionSTFTLoss


# Optional wandb import with graceful fallback
try:
    import wandb

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

_LOGGER = logging.getLogger("vits.lightning")
# パッケージ名前空間の logger。本モジュールの _LOGGER は歴史的経緯で
# "vits.lightning" 名のため、ユーザ向け警告 (F8 DINO 退化警告等) は
# piper_train.* 名前空間で出す (logging config / テストの補足対象)。
_PKG_LOGGER = logging.getLogger("piper_train.vits.lightning")

# Memory cleanup frequency (iterations)
MEMORY_CLEANUP_FREQUENCY = 500

# Raw KL safety cap (see training_step_g). Shared with the KL-cap sticking
# guard so the clamp value and the detector can never drift apart.
_KL_CAP = 1e4
# Abort after this many *consecutive* steps with raw KL pinned at the cap.
# The cap is expected to be active only in the first ~100 batches of scratch
# training; hundreds of consecutive capped steps mean the KL term carries no
# gradient signal and the run is unrecoverable (2026-08 v8 incident: corrupt
# MAS alignments kept raw KL at the cap from step ~30 to the end of an
# 80-epoch run while non_finite_skip=0% looked healthy).
_KL_CAP_ABORT_DEFAULT = 300


def _kl_cap_abort_steps_from_env() -> int:
    """Parse PIPER_PLUS_KL_CAP_ABORT_STEPS (default 300, 0 disables abort)."""
    raw = os.environ.get("PIPER_PLUS_KL_CAP_ABORT_STEPS", "")
    if not raw:
        return _KL_CAP_ABORT_DEFAULT
    try:
        return int(raw)
    except ValueError:
        _LOGGER.warning(
            "Invalid PIPER_PLUS_KL_CAP_ABORT_STEPS=%r — using default %d",
            raw,
            _KL_CAP_ABORT_DEFAULT,
        )
        return _KL_CAP_ABORT_DEFAULT


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


def _select_ort_providers() -> list:
    """ONNX Runtime providers を学習時 SCL 推論用に選択する。

    SCL は毎 training step で per-utterance に CAM++ ONNX を呼ぶため、
    CPU 固定だとボトルネックになる (V100×4 環境で 14 sec/step を観測)。
    GPU が利用可能なら CUDA を優先し、速度を 5-10× 改善する。

    環境変数 ``PIPER_PLUS_FORCE_CPU_ORT=1`` で CPU 固定 (デバッグ・低 VRAM 環境用)。
    """
    import os

    if os.environ.get("PIPER_PLUS_FORCE_CPU_ORT", "0") == "1":
        return ["CPUExecutionProvider"]

    import onnxruntime as ort

    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class CamPPSpeakerEncoder:
    """ONNX wrapper for CAM++ speaker embedding extraction (Speaker Consistency Loss).

    NOT an nn.Module — excluded from state_dict/checkpoints automatically.
    Provider 選択は ``_select_ort_providers`` に委譲 (デフォルトで GPU 優先)。
    """

    def __init__(self, onnx_path: str, source_sr: int = 22050, target_sr: int = 16000):
        import onnxruntime as ort

        providers = _select_ort_providers()
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.source_sr = source_sr
        self.target_sr = target_sr
        actual = self.session.get_providers()
        _LOGGER.info("CamPPSpeakerEncoder loaded: %s (providers=%s)", onnx_path, actual)

    @torch.no_grad()
    def __call__(self, audio: torch.Tensor) -> torch.Tensor:
        """Extract speaker embeddings from audio waveforms.

        Args:
            audio: [B, T] float32 waveform at source_sr

        Returns:
            [B, 192] L2-normalized speaker embeddings (on same device as input)
        """
        import torchaudio

        device = audio.device
        embeddings = []
        for i in range(audio.size(0)):
            wav = audio[i].unsqueeze(0).cpu().float()
            # Resample to 16kHz
            if self.source_sr != self.target_sr:
                wav = torchaudio.functional.resample(
                    wav, self.source_sr, self.target_sr
                )
            # Compute 80-dim Fbank
            fbank = torchaudio.compliance.kaldi.fbank(
                wav,
                num_mel_bins=80,
                sample_frequency=self.target_sr,
                dither=0.0,
            )
            # Mean subtraction (CMVN)
            fbank = fbank - fbank.mean(dim=0, keepdim=True)
            # ONNX inference: [1, T, 80] -> [1, 192]
            fbank_np = fbank.unsqueeze(0).numpy()
            emb = self.session.run(None, {"input": fbank_np})[0]
            embeddings.append(emb[0])

        emb_tensor = torch.tensor(
            np.stack(embeddings), dtype=torch.float32, device=device
        )
        # L2 normalize
        emb_tensor = torch.nn.functional.normalize(emb_tensor, p=2, dim=-1)
        return emb_tensor


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
        warmup_epochs: int = 5,
        c_mel: int = 45,
        c_kl: float = 1.0,
        grad_clip: float | None = None,
        num_workers: int = 2,
        seed: int = 1234,
        num_test_examples: int = 2,
        validation_split: float = 0.1,
        max_phoneme_ids: int | None = None,
        # Zero-shot TTS (enabled by default for multi-speaker models)
        use_zero_shot: bool = True,
        spk_embed_dim: int = 192,
        c_spk: float = 1.0,
        c_dino: float = 0.5,
        speaker_encoder_path: str | None = None,
        # Differentiable SCL (v8.1): torch 版 CAM++ の重み (campplus_cn_common.bin)。
        # 指定時は SCL がこの frozen encoder を通して y_hat まで backprop する。
        # 未指定時は従来の ONNX no_grad 経路 (= 勾配ゼロ、monitoring のみ)。
        speaker_encoder_torch_path: str | None = None,
        # SCL の損失形式: "cosine" (従来) | "infonce" (in-batch 対比、話者判別を要求)
        spk_loss_type: str = "cosine",
        # SCL InfoNCE の正例定義 (Phase 1 B-1、v10 roadmap):
        # "same_utt" (従来、対角正例) | "cross_utt" (同一話者・別発話正例、
        # SupCon 形式。same-utt 一致の Goodhart 経路を遮断し話者転写に直接の
        # 勾配を与える。samples_per_speaker > 1 が前提)
        spk_loss_positives: str = "same_utt",
        # B-3 (v10 roadmap): SCL 専用に posterior z を detach した decoder
        # forward を追加 (opt-in)。SCL 勾配を g (spk_proj) + decoder のみに
        # 制限し、「decoder が GT 由来の z から音色を読む」posterior leak を
        # 遮断する。decoder forward が 1 回増えるため step 時間が増加する
        scl_detach_z: bool = False,
        # v10 S1 (swap-SCL、design doc §3.1): flow を同一言語の別話者
        # embedding で逆走させた波形に speaker loss を当てる (ASCL 型)。
        # z_p の中身は元話者由来なので same-utt Goodhart が経路的に不可能。
        # scl_encoder (--speaker-encoder-torch-path) 必須。default 0.0 = off
        c_swap_spk: float = 0.0,
        swap_spk_start_epoch: int = 10,
        swap_spk_ramp_epochs: int = 5,
        # v10 §3.2 (SupCon 改良): DDP 全 rank の SCL embedding を勾配が通る
        # all_gather で結合してから InfoNCE へ (負例プール x world_size)
        spk_loss_gather: bool = False,
        # InfoNCE/SupCon の softmax 温度 (v10 recipe は 0.1 を指定)
        spk_loss_temperature: float = 0.07,
        # v10 §3.3 (Latent Filling、arXiv:2310.03538): 確率 τ の step で
        # 条件 embedding を同一言語補間 or 微小 noise に置換し、LFCL のみで
        # G を更新 (D 更新 skip)。σ noise (F7 で廃止) の置換。0.0 = off
        latent_filling_tau: float = 0.0,
        # Speaker embedding dropout for dual-mode training (DEPRECATED: no longer used,
        # spk_proj is now the sole speaker conditioning path)
        spk_emb_dropout: float = 0.0,
        # KL annealing: linearly increase KL weight from 0.1 to c_kl over this many epochs
        kl_annealing_epochs: int = 10,
        # WavLM Discriminator (enabled by default for improved audio quality)
        use_wavlm_discriminator: bool = True,
        wavlm_model_name: str = "microsoft/wavlm-base-plus",
        c_wavlm: float = 0.5,
        wavlm_every_n_steps: int = 1,
        # MRD: UnivNet 型 multi-resolution spectrogram discriminator (v9)。
        # 22.05kHz ネイティブの線形周波数 magnitude STFT を判別 — mel loss の
        # 高域粗さと WavLM の 16kHz 盲点が残す 5-11kHz の敵対的監督を埋める
        # (zero-shot がびがびの副次要因 1、root-cause doc §3)
        use_mrd: bool = False,
        c_mrd: float = 1.0,
        # --- v10b 識別器系 (default は全て v10a-r2 と bit 互換。
        # docs/design/zero-shot-v10b-quality-plan.md §3.1 H-3 / §3.2 S-1) ---
        # S-1a: MRD の各 resolution に GANSpeech 型 JCU 条件分岐を足す
        # (speaker embedding を FC → 時間展開 → 共有 body に concat)。
        # 話者監督が共進化する識別器経由になるため、frozen encoder cosine を
        # 目的化した v10a §10 の崩壊機構が構造的に成立しない
        use_jcu_mrd: bool = False,
        # H-3: MRD に高分解能 resolution を 1 本 **追加** (置換ではない)。
        # "off" / MRD_HIRES_RESOLUTIONS のキー ("2048" / "4096")
        mrd_hires_resolution: str = "off",
        # S-1b: 共進化 adversarial speaker classifier。C は実音声を真の話者、
        # 生成音声を「生成」クラスに分類するよう学習し (= 生成分布上でも
        # 更新される)、G は生成音声が条件話者に分類されるよう CE 最小化する。
        # 実音声のみで学習する静的 classifier は plan §2.2 で禁止
        use_adv_spk_classifier: bool = False,
        c_adv_spk: float = 1.0,
        adv_spk_start_epoch: int = 10,
        adv_spk_ramp_epochs: int = 5,
        # S-1b classifier の出力クラス数。0 = num_speakers を使う (後方互換)。
        # 案 Z ゲート等で speaker_id が疎 (欠番あり) な dataset では
        # num_speakers (個数) < max_id+1 となり out-of-range で即死するため、
        # __main__ が jsonl から max_id+1 を自動算出して渡す (v10b smoke で実測
        # した事故: num_speakers=3692 に対し max id 3763)
        adv_spk_num_classes: int = 0,
        # v9 decoder 再適応 FT: decoder 以外の generator パラメータを凍結
        train_decoder_only: bool = False,
        # MB-iSTFT options
        c_sub_stft: float = 1.0,
        sub_stft_fft_sizes: tuple[int, ...] = (171, 384, 683),
        sub_stft_hop_sizes: tuple[int, ...] = (10, 30, 60),
        sub_stft_win_sizes: tuple[int, ...] = (60, 150, 300),
        # Full-band linear-frequency MR-STFT loss (v9)。mel L1 は高域で bin が
        # 数百 Hz 幅と粗く、multi-speaker 学習の高域平均化を許す。線形周波数の
        # spectral convergence + log-mag L1 を fullband o vs y に直接かける
        # (root-cause doc §3 副次要因 1 の regression 側対策。MRD が敵対的側)
        c_full_stft: float = 0.0,
        full_stft_fft_sizes: tuple[int, ...] = (512, 1024, 2048),
        full_stft_hop_sizes: tuple[int, ...] = (128, 256, 512),
        full_stft_win_sizes: tuple[int, ...] = (512, 1024, 2048),
        # v11 柱2 (A2'): 6-11kHz (9-11kHz は 2 倍の厚み) band-weighted GT 参照
        # MR-STFT magnitude 回帰。mel L1 / 既存 STFT loss が実質盲目な帯域を
        # GT waveform を教師として直接監督する (残存ノイズ診断 doc §3 対策 ii)。
        # GT 教師回帰 = zs-eval-contract §2 の例外形 (評価メトリクスの loss 化
        # ではない)。default 0 = off (v10b bit 互換)。
        c_hiband_stft: float = 0.0,
        # v11 A′ (--use-carrier-head): 担体化 harmonic-plus-noise head
        # (docs/design/zero-shot-v11-harmonic-head-design.md)。use_f0_path 必須。
        # default off = v10b bit 互換。
        use_carrier_head: bool = False,
        carrier_harmonics: int = 32,
        # A′ の L_src hinge (σ 氾濫の事前登録緩和策、設計 doc §4.3)。
        # default 0 = off — Phase D 監視 #6 発火時のみ arm する。
        c_src_reg: float = 0.0,
        src_reg_tau: float = 0.0,
        # Training loop optimization
        # D:G update ratio (D updates every step, G updates every d_update_interval steps)
        d_update_interval: int = 2,
        max_spec_length: int = 700,
        # T1: channels_last memory format for Conv2d Discriminator (opt-in, default OFF).
        # Targets NHWC Tensor Core kernels on A100 SXM4 / Ada 6000; silent
        # fallback on sm_75 (T4) and older. Affects DiscriminatorP (Conv2d)
        # actively; DiscriminatorS (Conv1d) and Generator (MBiSTFTGenerator,
        # Conv1d-only) receive the flag as a silent no-op via PyTorch's
        # ``Module.to(memory_format=...)`` which skips 3D tensors (t.dim() in
        # (4, 5) guard). T1 拡張: Generator にも propagate することで、 (a) D と G
        # 間で hparam を対称に扱う、 (b) 将来 Generator に Conv2d を追加した際に
        # 自動的に NHWC 化される、 の 2 目的を満たす。
        use_channels_last: bool = False,
        # T6: Discriminator forward precision override (hybrid precision, opt-in).
        # "inherit" (default) → D forward follows Lightning trainer precision (status
        # quo). "bf16-mixed" → wrap D forward (MPD/MSD + optional WavLM disc) in
        # torch.autocast(bf16) even when trainer runs at ``--precision 32-true``,
        # keeping SCL / DINO / loss compute at fp32 via the existing outer
        # ``autocast(enabled=False)`` blocks in ``training_step_g/d`` plus the
        # explicit inner wrap around the SCL block. "32-true" → forces D forward
        # to fp32 (``autocast(enabled=False)``) even under ``--precision
        # bf16-mixed`` for debugging numerical parity vs the 32-true baseline.
        # Motivation: on v8 A100 SXM4 real-config traces, ``--precision 32-true``
        # (5.15 sec/step simplified) was faster than ``bf16-mixed`` (14.0 sec/step
        # real config) due to SCL/DINO instability under bf16; hybrid precision
        # keeps the D-forward speed win of bf16 (~20-30% expected) without
        # exposing SCL to bf16 numerics.
        disc_precision: str = "inherit",
        # T3: opt-in SDPA fast path for TextEncoder self-attention. Default OFF
        # preserves the manual matmul path (bit-parity vs prior checkpoints).
        # When True, ``TextEncoder.encoder`` (attentions.Encoder) swaps its
        # per-layer MultiHeadAttention to ``F.scaled_dot_product_attention``
        # with the relative-K bias folded into ``attn_mask``. The relative-V
        # correction is dropped (SDPA does not surface p_attn). Expected win:
        # +2-5% throughput, activation memory -60MB/batch on v8 real config.
        attn_drop_rel_v: bool = False,
        # v10 構造介入 (M1/M2/M3/E1、default は全て off / 0 = v9 bit 互換。
        # docs/design/zero-shot-v10-design.md §4):
        # M2: enc_p の話者注入を transformer 第 N 層入口へ (0 = 従来の後段加算)
        speaker_cond_layer: int = 0,
        # M3: duration 勾配を spk_proj_dp 残差ヘッドへ通す (spk_proj 本体は保護)
        dp_spk_head: bool = False,
        # M1+E2: flow coupling の SNAC 化 + flow logdet の KL 配線
        use_snac_flow: bool = False,
        # v11 P2 (--use-adaln-encp): enc_p transformer の LayerNorm 12 本を
        # AdaLN-Zero 化 (共有低ランク trunk、入力は g_spk のみ = P0-4 の
        # lang 干渉分離)。zero-init で on 直後は素の LN と一致。M2
        # (speaker_cond_layer) とは独立 flag で共存 (重複の要否は smoke A/B、
        # conditioning 設計 doc §10.5)。default off = v10b bit 互換
        use_adaln_encp: bool = False,
        # v11 P5 (--no-snac-stats): SNAC の SN/SDN 統計注入のみを恒等化
        # (sn_linear 非構築、−394k param。Phase 0 D-3/D-4 で LOO −0.017 =
        # 無害な死荷重と実測)。SNAC flow 構造 (可逆性・logdet の KL 配線) は
        # 不変。use_snac_flow=True が前提。default off = 従来どおり統計注入
        no_snac_stats: bool = False,
        # v11 D-2: 変調統計テレメトリ常設 — 各注入点の話者依存分散比
        # (話者間分散/総分散) 等を N step ごとに log する。0 で無効。
        # 「総量だけでは SNAC 型死荷重を検知できない」教訓の制度化
        # (conditioning 設計 doc §10.6-4 / §10.3-1)
        telemetry_every: int = 500,
        # E1: dec FiLM (cond_layers) の zero-init を N(0, std) に置換
        film_init_std: float = 0.0,
        # v11 P0 (--film-free-scale): dec FiLM scale を sigmoid+0.5 の
        # [0.5, 1.5] 制限から 1+γ̂ (無界、zero-init 層では on 直後 = off) に
        # 開放 (conditioning 設計 doc §5.2 b-1)。default off = v10b bit 互換
        film_free_scale: bool = False,
        # v11 P3 (--use-adain-decoder): decoder resblock 単位の zero-init
        # 残差 AdaIN (s1 重心レイアウト、conditioning 設計 doc §5.1 a-2 /
        # §10.5)。既存 FiLM と独立に共存。default off = v10b bit 互換
        use_adain_decoder: bool = False,
        # v10b Phase B デコーダ系 (default は v10a-r2 bit 互換。
        # docs/design/zero-shot-v10b-quality-plan.md §3.1):
        # H-1: upsampler の resize+conv 化 ("transposed" | "resize")
        upsample_mode: str = "transposed",
        # H-2b: PQMF taps (PQMF_DESIGN の preset) / 合成フィルタの学習可能化。
        # 両者は decoder と GT analysis が共有する PQMF に適用される。
        pqmf_taps: int = 62,
        trainable_pqmf_synthesis: bool = False,
        # --- v10b S-2 (F0 明示経路。default off = v10a-r2 bit 互換。
        # docs/design/zero-shot-v10b-s2-f0-design.md) ---
        # S-2a + S-2c + S-2p を一括で有効化する。GT F0 キャッシュが必須
        # (``tools/extract_f0.py`` で作る)。
        use_f0_path: bool = False,
        # GT F0 キャッシュのディレクトリ (未指定なら {dataset_dir}/f0)
        f0_dir: str | None = None,
        # 予測器 (S-2p) の loss 係数。§4.3 の λ は grad-probe で較正する
        c_f0: float = 1.0,
        c_vuv: float = 1.0,
        f0_predictor_hidden: int = 96,
        f0_feat_channels: int = 8,
        f0_head_channels: int = 8,
        f0_harmonics: int = 8,
        # S-2r: prior 側 F0 残差 (zero-init、B1 を動かす主経路と見る)
        f0_prior_residual: bool = False,
        # F0 loss の勾配を spk_proj 本体 / enc_p へ通すか (default は保護側)
        f0_spk_grad: bool = False,
        f0_detach_input: bool = True,
        # teacher forcing アニール (§4.4): epoch K 以降 R epoch かけて
        # GT F0 → 予測 F0 へ確率 p_max まで寄せる
        f0_teacher_forcing_epochs: int = 10,
        f0_teacher_forcing_ramp: int = 10,
        f0_pred_prob_max: float = 0.5,
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

        # v11 P5: --no-snac-stats は SNAC の修飾 flag なので、SNAC flow なしで
        # 指定された構成は黙って no-op にせず即エラーにする (意図の取り違えを
        # 1 週間の学習で払わせない)
        if no_snac_stats and not use_snac_flow:
            raise ValueError(
                "--no-snac-stats requires --use-snac-flow: it removes only the "
                "SN/SDN statistics injection from the SNAC coupling layers, "
                "which do not exist without the SNAC flow."
            )

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
            attn_drop_rel_v=self.hparams.attn_drop_rel_v,
            use_channels_last=self.hparams.use_channels_last,
            speaker_cond_layer=self.hparams.speaker_cond_layer,
            dp_spk_head=self.hparams.dp_spk_head,
            use_snac_flow=self.hparams.use_snac_flow,
            use_adaln_encp=self.hparams.use_adaln_encp,
            snac_stats=not self.hparams.no_snac_stats,
            film_init_std=self.hparams.film_init_std,
            upsample_mode=self.hparams.upsample_mode,
            pqmf_taps=self.hparams.pqmf_taps,
            trainable_pqmf_synthesis=self.hparams.trainable_pqmf_synthesis,
            use_f0_path=self.hparams.use_f0_path,
            f0_predictor_hidden=self.hparams.f0_predictor_hidden,
            f0_feat_channels=self.hparams.f0_feat_channels,
            f0_head_channels=self.hparams.f0_head_channels,
            f0_harmonics=self.hparams.f0_harmonics,
            f0_prior_residual=self.hparams.f0_prior_residual,
            f0_spk_grad=self.hparams.f0_spk_grad,
            f0_detach_input=self.hparams.f0_detach_input,
            use_carrier_head=self.hparams.use_carrier_head,
            carrier_harmonics=self.hparams.carrier_harmonics,
            use_adain_decoder=self.hparams.use_adain_decoder,
            sample_rate=self.hparams.sample_rate,
            hop_length=self.hparams.hop_length,
        )
        # v11 P0 (--film-free-scale): forward 時の scale 式だけを切り替える
        # 挙動 flag (パラメータ・初期化・state_dict は不変) なので、
        # SynthesizerTrn の signature を経由せず decoder 属性へ直接設定する。
        # hparams には save_hyperparameters() で保存済み → resume / ONNX
        # export (load_from_checkpoint → 本 __init__) でも再現される。
        # tests/test_film_free_scale.py がこの統合点を pin する。
        if self.hparams.film_free_scale:
            self.model_g.dec.film_free_scale = True
        self.model_d = MultiPeriodDiscriminator(
            use_spectral_norm=self.hparams.use_spectral_norm,
            use_channels_last=self.hparams.use_channels_last,
        )
        if self.hparams.use_channels_last:
            _LOGGER.info(
                "channels_last enabled: MultiPeriodDiscriminator (DiscriminatorP "
                "Conv2d → NHWC, active) + SynthesizerTrn.dec (MBiSTFTGenerator, "
                "Conv1d-only → silent no-op, plumbing for future Conv2d)."
            )

        # DINO center buffer for zero-shot speaker embedding regularization
        use_zero_shot = self.hparams.use_zero_shot and self.hparams.num_speakers > 1
        if use_zero_shot:
            self.register_buffer("dino_center", torch.zeros(self.hparams.gin_channels))

        # DINO EMA teacher for spk_proj (must be after model_g creation)
        self.spk_proj_teacher = None
        if use_zero_shot and hasattr(self.model_g, "spk_proj"):
            self.spk_proj_teacher = copy.deepcopy(self.model_g.spk_proj)
            self.spk_proj_teacher.requires_grad_(False)

        # Differentiable CAM++ for SCL (v8.1) — 指定時は SCL が y_hat まで backprop。
        # ONNX 経路 (下) は torch.no_grad + ORT で勾配ゼロ = monitoring にしか
        # ならない (v7/v8 で loss_spk が動かなかった根因、design doc §3.15)。
        self.scl_encoder = None
        if use_zero_shot and self.hparams.speaker_encoder_torch_path is not None:
            torch_encoder_path = Path(self.hparams.speaker_encoder_torch_path)
            if torch_encoder_path.exists():
                from ..speaker_encoder.campplus_torch import (
                    DifferentiableCamPPEncoder,
                )

                self.scl_encoder = DifferentiableCamPPEncoder(
                    str(torch_encoder_path),
                    source_sr=self.hparams.sample_rate,
                )
                _LOGGER.info(
                    "Differentiable SCL enabled (torch CAM++, spk_loss_type=%s, "
                    "spk_loss_positives=%s, scl_detach_z=%s)",
                    self.hparams.spk_loss_type,
                    getattr(self.hparams, "spk_loss_positives", "same_utt"),
                    getattr(self.hparams, "scl_detach_z", False),
                )
            else:
                _LOGGER.warning(
                    "speaker_encoder_torch_path not found, differentiable SCL "
                    "disabled: %s",
                    torch_encoder_path,
                )
        # cross_utt 正例モードで speaker_ids 欠落時の警告は一度だけ出す
        self._warned_cross_utt_no_sid = False

        # v10 F8: DINO は本実装の構成 (frozen CAM++ / 同一入力 / view 拡張なし)
        # では慣性項に退化していることが確定している (design doc F8 —
        # DINO-VITS の効果の本体は「ノイズ拡張 view + speaker encoder joint FT
        # の正則化」で、我々の版にはどちらもない)。c_dino > 0 のまま学習を
        # 始めるユーザに構築時 1 回だけ警告する。
        if self.hparams.c_dino > 0 and self.spk_proj_teacher is not None:
            _PKG_LOGGER.warning(
                "c_dino=%s > 0 but the DINO loss is known to degenerate into "
                "an inertia term in this implementation (frozen CAM++, "
                "identical student/teacher inputs, no view augmentation — "
                "v10 design doc F8). The v10 recipe recommends c_dino=0 "
                "(cross-utt SupCon is the functional superset).",
                self.hparams.c_dino,
            )

        # v10 S1 / §3.3: swap-SCL と Latent Filling は微分可能 CAM++
        # (scl_encoder) が学習信号の実体。encoder 無しでは勾配ゼロなので
        # 黙って劣化させず、構築時に警告して無効化する。
        if getattr(self.hparams, "c_swap_spk", 0.0) > 0 and self.scl_encoder is None:
            _PKG_LOGGER.warning(
                "c_swap_spk=%s > 0 but no differentiable speaker encoder is "
                "loaded (--speaker-encoder-torch-path) — swap-SCL disabled.",
                self.hparams.c_swap_spk,
            )
        if (
            getattr(self.hparams, "latent_filling_tau", 0.0) > 0
            and self.scl_encoder is None
        ):
            _PKG_LOGGER.warning(
                "latent_filling_tau=%s > 0 but no differentiable speaker "
                "encoder is loaded (--speaker-encoder-torch-path) — Latent "
                "Filling disabled.",
                self.hparams.latent_filling_tau,
            )
        # Latent Filling step flag: training_step_g が set し、training_step が
        # D 更新 skip の判断に使う (LF step は LFCL のみで G を更新する契約)
        self._lf_step_active = False

        # CAM++ Speaker Encoder for SCL (optional, CPU-only ONNX, not an nn.Module)
        self.speaker_encoder = None
        if use_zero_shot and self.hparams.speaker_encoder_path is not None:
            encoder_path = Path(self.hparams.speaker_encoder_path)
            if encoder_path.exists():
                self.speaker_encoder = CamPPSpeakerEncoder(
                    str(encoder_path),
                    source_sr=self.hparams.sample_rate,
                )
                _LOGGER.info("CamPPSpeakerEncoder loaded: %s", encoder_path)
            else:
                _LOGGER.warning(
                    "speaker_encoder_path not found, SCL disabled: %s", encoder_path
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

        # MRD: multi-resolution spectrogram discriminator (optional, v9)
        # v10b: S-1a JCU 条件分岐 + H-3 高分解能 resolution 追加 (両方 opt-in)
        self.model_d_mrd = None
        use_jcu = bool(getattr(self.hparams, "use_jcu_mrd", False))
        hires_name = getattr(self.hparams, "mrd_hires_resolution", "off") or "off"
        if self.hparams.use_mrd:
            hires = (
                MRD_HIRES_RESOLUTIONS.get(hires_name) if hires_name != "off" else None
            )
            if hires_name != "off" and hires is None:
                raise ValueError(
                    f"unknown mrd_hires_resolution: {hires_name!r} "
                    f"(expected 'off' or one of {sorted(MRD_HIRES_RESOLUTIONS)})"
                )
            _LOGGER.info(
                "Initializing MRD (multi-resolution spectrogram discriminator), "
                "c_mrd=%s jcu=%s hires=%s",
                self.hparams.c_mrd,
                use_jcu,
                hires or "off",
            )
            self.model_d_mrd = MultiResolutionSpectrogramDiscriminator(
                spk_cond_dim=192 if use_jcu else 0,
                hires_resolution=hires,
            )
        elif use_jcu or hires_name != "off":
            # 黙って無視しない: JCU / hires は MRD 本体の分岐なので、MRD 無しで
            # 指定されたら効かないことを明示する (CLI 側でも fail-fast する)
            _PKG_LOGGER.warning(
                "--use-jcu-mrd / --mrd-hires-resolution require --use-mrd; "
                "MRD is disabled so both options have no effect."
            )

        # v10b S-1b: 共進化 adversarial speaker classifier (学習時のみ、
        # zero-shot 推論 / ONNX 契約には影響しない閉集合分類器)
        self.model_c_spk = None
        if getattr(self.hparams, "use_adv_spk_classifier", False):
            if self.hparams.num_speakers < 2:
                _PKG_LOGGER.warning(
                    "--use-adv-spk-classifier requires a multi-speaker dataset "
                    "(num_speakers=%d) — the classifier is disabled.",
                    self.hparams.num_speakers,
                )
            else:
                if float(getattr(self.hparams, "c_adv_spk", 0.0) or 0.0) <= 0:
                    _PKG_LOGGER.warning(
                        "--use-adv-spk-classifier is set but c_adv_spk=%s, so the "
                        "adversarial speaker classifier contributes nothing. Pass "
                        "--c-adv-spk > 0 (grad-probe calibrated) to enable it.",
                        getattr(self.hparams, "c_adv_spk", 0.0),
                    )
                n_classes = int(getattr(self.hparams, "adv_spk_num_classes", 0) or 0)
                if n_classes <= 0:
                    n_classes = self.hparams.num_speakers
                elif n_classes < self.hparams.num_speakers:
                    raise ValueError(
                        f"adv_spk_num_classes={n_classes} < "
                        f"num_speakers={self.hparams.num_speakers} — the "
                        "classifier head cannot be smaller than the distinct "
                        "speaker count"
                    )
                self.model_c_spk = AdversarialSpeakerClassifier(
                    num_speakers=n_classes,
                )
                _LOGGER.info(
                    "Adversarial speaker classifier enabled (v10b S-1b): "
                    "%d speaker classes + 1 generated class, c_adv_spk=%s, ramp "
                    "start=%s over %s epochs (classifier itself trains from "
                    "step 0; only the generator term ramps)",
                    n_classes,
                    self.hparams.c_adv_spk,
                    self.hparams.adv_spk_start_epoch,
                    self.hparams.adv_spk_ramp_epochs,
                )

        # MB-iSTFT: PQMF for GT analysis + sub-band STFT loss.
        # NOTE: this bank REPLACES the one the decoder built for itself, so the
        # v10b H-2b options must be repeated here — forgetting them would
        # silently discard --pqmf-taps / --trainable-pqmf-synthesis for every
        # run that goes through VitsModel (default behaviour stays correct,
        # which is exactly what makes the omission hard to notice).
        # tests/test_v10b_decoder_cli.py pins this integration point.
        self.pqmf = PQMF(
            subbands=4,
            taps=self.hparams.pqmf_taps,
            trainable_synthesis=self.hparams.trainable_pqmf_synthesis,
        )
        # Share PQMF instance with the decoder to avoid duplicate buffers and to
        # keep the sub-band loss target and the decoder synthesis on one bank.
        self.model_g.dec.pqmf = self.pqmf
        self.sub_stft_loss = MultiResolutionSTFTLoss(
            fft_sizes=self.hparams.sub_stft_fft_sizes,
            hop_sizes=self.hparams.sub_stft_hop_sizes,
            win_sizes=self.hparams.sub_stft_win_sizes,
        )
        # Full-band MR-STFT loss (v9, active when c_full_stft > 0)
        self.full_stft_loss = MultiResolutionSTFTLoss(
            fft_sizes=self.hparams.full_stft_fft_sizes,
            hop_sizes=self.hparams.full_stft_hop_sizes,
            win_sizes=self.hparams.full_stft_win_sizes,
        )
        # v11 柱2: 高域 band-weighted GT 参照 MR-STFT (active when
        # c_hiband_stft > 0)。帯域重みは固定 buffer (学習不能 — gaming 面を
        # 増やさない)。
        self.hiband_stft_loss = HighBandSTFTLoss(sample_rate=self.hparams.sample_rate)

        # Dataset splits
        self._train_dataset: Dataset | None = None
        self._val_dataset: Dataset | None = None
        self._test_dataset: Dataset | None = None
        self._load_datasets(validation_split, num_test_examples, max_phoneme_ids)

        # State kept between training optimizers
        self._y = None
        self._y_hat = None
        # v10b S-1a: JCU MRD が D 更新でも使う条件 embedding (noise 加算後)
        self._spk_cond = None

        # T1 (roadmap A-1c): per-loss grad-norm probe state。probe が due の
        # step でのみ training_step_g が loss 成分 dict をここに置き、
        # training_step が combined backward の前に消費する。無効時
        # (--grad-probe-every 0, default) は常に None のままで追加コストなし。
        self._grad_probe_losses: dict[str, torch.Tensor] | None = None

        # KL-cap sticking guard state (see _update_kl_cap_guard)
        self._kl_cap_consecutive = 0
        self._kl_cap_abort_steps = _kl_cap_abort_steps_from_env()

    def _load_test_dataset(self, test_utterances_path: Path):
        """Load fixed test dataset for WandB audio logging.

        Ensures Japanese, English, and cross-lingual ja-en sentences are
        covered. Mixed sentences (language_id == -1) are auto-phonemized with
        the bilingual ``ja-en`` phonemizer (see ``get_phonemizer("ja-en")``
        below); extending to 6lang mixed phonemization is a TODO.
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

        # ``--precomputed-mel`` flag → resolve ``{dataset_dir}/mel`` and pass to
        # PiperDataset. Missing directory falls back to legacy ``.spec.pt`` cache
        # per utterance (see PiperDataset.__init__ diagnostics).
        precomputed_mel_dir: Path | None = None
        if self.hparams.get("precomputed_mel", False):
            precomputed_mel_dir = Path(self.hparams.dataset_dir) / "mel"
            _LOGGER.info("Precomputed mel cache enabled: %s", precomputed_mel_dir)

        # v10b S-2: GT F0 cache (``tools/extract_f0.py`` の出力)。既定は
        # ``{dataset_dir}/f0``。ディレクトリが無ければ PiperDataset 側が警告して
        # 「F0 なし」に倒す (--use-f0-path 有効時は training_step が fail-fast)。
        f0_dir: Path | None = None
        if self.hparams.get("use_f0_path", False):
            f0_dir = Path(
                self.hparams.get("f0_dir") or (Path(self.hparams.dataset_dir) / "f0")
            )
            _LOGGER.info("v10b S-2: F0 target cache = %s", f0_dir)

        # Try to load fixed test dataset first
        test_utterances_path = self.hparams.dataset_dir / "test_utterances.jsonl"
        if test_utterances_path.exists():
            self._test_dataset = self._load_test_dataset(test_utterances_path)
            # Load train/val datasets without test examples
            full_dataset = PiperDataset(
                self.hparams.dataset,
                max_phoneme_ids=max_phoneme_ids,
                validate_cache=validate_cache,
                precomputed_mel_dir=precomputed_mel_dir,
                f0_dir=f0_dir,
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
                precomputed_mel_dir=precomputed_mel_dir,
                f0_dir=f0_dir,
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

    def on_load_checkpoint(self, checkpoint: dict) -> None:
        """Normalise older checkpoints in place before Lightning loads them.

        Lightning calls this hook *before* ``load_state_dict``, which is the
        only place a fix can land for ``VitsModel.load_from_checkpoint`` and
        ``trainer.fit(ckpt_path=...)`` alike — both raise on a size mismatch
        before any caller-side code gets a chance to intervene, and
        ``strict=False`` does not help (it tolerates missing/unexpected keys,
        never mismatched shapes).

        Handles checkpoints predating the Multi-scale FiLM decoder (issue
        #616), plus the ``torch.compile`` and DDP weight-norm key formats.
        """
        model_sd = self.state_dict()

        state_dict = checkpoint.get("state_dict")
        if state_dict:
            checkpoint["state_dict"], stats = normalize_checkpoint_state_dict(
                state_dict, model_sd
            )
            if stats["cond_migrated"]:
                _LOGGER.info(
                    "Loaded a pre-FiLM checkpoint; decoder conditioning was "
                    "migrated to the Multi-scale FiLM layout (issue #616)."
                )

        # EMA shadow params live in the decoder's own namespace and are applied
        # by EMACallback later in the restore sequence. Migrating them here as
        # well keeps the two halves of the checkpoint consistent; the migration
        # is idempotent, so EMACallback re-running it is harmless.
        ema_state = checkpoint.get("ema_generator_state")
        if isinstance(ema_state, dict) and ema_state.get("shadow_params"):
            ema_state["shadow_params"], _ = migrate_prefilm_decoder_cond(
                ema_state["shadow_params"], self.model_g.dec.state_dict()
            )

        # Adam moments are shaped like the parameters they track, so the
        # decoder migration invalidates them too. `optimizer.load_state_dict`
        # does not check shapes, so leaving them alone means the resume dies at
        # the first `step()` — and the caller's fallback then silently restarts
        # from epoch 0. Widen them when the parameter ordering can be
        # validated; otherwise drop them loudly.
        if optimizer_states_need_migration(checkpoint, model_sd):
            if (
                migrate_prefilm_optimizer_states(
                    checkpoint, self._generator_named_params()
                )
                == 0
            ):
                checkpoint.pop("optimizer_states", None)
                checkpoint.pop("lr_schedulers", None)
                _LOGGER.warning(
                    "Optimizer state is in the pre-FiLM layout and its parameter "
                    "ordering could not be validated, so it was discarded. "
                    "Training resumes from epoch %s with the checkpoint's weights "
                    "but freshly initialised optimizer moments.",
                    checkpoint.get("epoch", "?"),
                )

    def _generator_named_params(self) -> list:
        """``(name, tensor)`` in the order the generator optimizer receives them.

        Mirrors ``configure_optimizers``: the generator optimizer is built from
        ``model_g.parameters()`` filtered by ``requires_grad``. ``freeze_dp`` is
        applied there, i.e. *after* this hook runs, so the filter is replayed
        from hparams instead of read off the live flags.
        """
        freeze_dp = bool(getattr(self.hparams, "freeze_dp", False))
        return [
            (f"model_g.{name}", param)
            for name, param in self.model_g.named_parameters()
            if param.requires_grad and not (freeze_dp and name.startswith("dp."))
        ]

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
        # DataLoader prefetch_factor (per worker, only meaningful when num_workers > 0).
        # Default raised from 2 → 4 to keep the H2D pipeline warm now that Batch pins
        # memory (see Batch.pin_memory in dataset.py). 4 doubles the queue depth
        # while staying safely below RAM pressure at typical multi-speaker batch sizes.
        prefetch_factor_val = int(getattr(self.hparams, "prefetch_factor", 4))

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
            length_bucket = bool(
                getattr(self.hparams, "enable_length_bucketing", False)
            )
            self._train_batch_sampler = SpeakerBalancedBatchSampler(
                self._train_dataset,
                batch_size=self.hparams.batch_size,
                samples_per_speaker=samples_per_speaker,
                drop_last=True,
                language_group_balance=language_group_balance,
                length_bucket=length_bucket,
            )
            _LOGGER.info(
                "Using SpeakerBalancedBatchSampler: batch_size=%d, samples_per_speaker=%d, "
                "speakers_per_batch=%d, length_bucket=%s",
                self.hparams.batch_size,
                samples_per_speaker,
                self.hparams.batch_size // samples_per_speaker,
                length_bucket,
            )
            return DataLoader(
                self._train_dataset,
                collate_fn=collate_fn,
                batch_sampler=self._train_batch_sampler,
                num_workers=self.hparams.num_workers,
                pin_memory=pin_memory,
                persistent_workers=(self.hparams.num_workers > 0),
                prefetch_factor=(
                    prefetch_factor_val if self.hparams.num_workers > 0 else None
                ),
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
                prefetch_factor=(
                    prefetch_factor_val if self.hparams.num_workers > 0 else None
                ),
            )

    def val_dataloader(self):
        # Check if pin_memory should be disabled (for memory-constrained multi-GPU setups)
        pin_memory = not getattr(self.hparams, "no_pin_memory", False)
        # Cap val workers to 2 to avoid RAM exhaustion in DDP multi-GPU setups
        # (total workers = num_workers × devices; val doesn't need many workers)
        num_workers = min(self.hparams.num_workers, 2)
        # Validation intentionally keeps the legacy prefetch_factor=2. Val runs briefly
        # and only every --val-every-n-epochs epochs, so a smaller queue reduces peak
        # RAM without a throughput cost. The train loader (which runs continuously)
        # is where the raised default matters.
        return DataLoader(
            self._val_dataset,
            collate_fn=UtteranceCollate(
                is_multispeaker=self.hparams.num_speakers > 1,
                segment_size=self.hparams.segment_size,
                is_multilanguage=self.hparams.num_languages > 1,
            ),
            num_workers=num_workers,
            batch_size=self.hparams.batch_size,
            pin_memory=pin_memory,
            persistent_workers=(num_workers > 0),
            prefetch_factor=(2 if num_workers > 0 else None),
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

    def _disc_autocast_ctx(self):
        """Return the autocast context wrapping Discriminator forward passes.

        Hybrid-precision knob (``--disc-precision`` / hparam ``disc_precision``):

        - ``"inherit"`` (default): return a ``contextlib.nullcontext`` so the D
          forward inherits Lightning's global precision setting. This is the
          status-quo behaviour and matches every existing training config.
        - ``"bf16-mixed"``: return
          ``torch.autocast(device_type=self.device.type, dtype=torch.bfloat16)``
          so MPD/MSD (and optional WavLM disc) run at bf16 even under
          ``--precision 32-true``. SCL / DINO / loss compute stay at fp32 via
          the outer ``autocast(enabled=False)`` blocks and the explicit inner
          ``_scl_autocast_ctx`` wrap.
        - ``"32-true"``: return
          ``torch.autocast(device_type=self.device.type, enabled=False)``
          forcing the D forward to fp32 even under ``--precision bf16-mixed``
          (useful for debugging numerical parity vs 32-true baseline).

        The autocast object is only meaningful on CUDA. On CPU / MPS it acts as
        a no-op which is what we want for unit tests.
        """
        mode = getattr(self.hparams, "disc_precision", "inherit")
        if mode == "bf16-mixed":
            return torch.autocast(
                device_type=self.device.type,
                dtype=torch.bfloat16,
                enabled=True,
            )
        if mode == "32-true":
            return torch.autocast(device_type=self.device.type, enabled=False)
        # inherit → no override
        return contextlib.nullcontext()

    def _scl_autocast_ctx(self):
        """Return an explicit ``autocast(enabled=False)`` context for SCL / DINO.

        SCL and DINO are numerically sensitive (see PR history: CAM++ embedding
        L2-normalize, DINO center EMA, teacher_emb NaN guard) and any bf16
        precision leakage risks NaN-masking the loss and stalling training. The
        outer ``autocast(enabled=False)`` at the top of ``training_step_g``
        already forces fp32 for the whole loss-compute block, but this helper
        makes the fp32 requirement visible and unit-testable at the SCL call
        site itself so a future refactor cannot accidentally hoist SCL out of
        the fp32 region.
        """
        return torch.autocast(device_type=self.device.type, enabled=False)

    # ------------------------------------------------------------------
    # v10b S-1a: JCU MRD の loss (無条件項 + 条件項を 1/2 ずつ)
    # ------------------------------------------------------------------

    def _mrd_generator_losses(self, y, y_hat, spk_cond):
        """MRD の G 側 loss を返す ``(adv, fm, adv_cond)``。

        JCU 有効時は無条件項と条件項を **1/2 ずつ平均**する。条件項を単純に
        足すと MRD の敵対項が 2 倍になり、grad-probe で mel の 5-15% に
        合わせた ``c_mrd`` の較正値が黙って崩れるため。``adv_cond`` は
        監視ログ用 (None = JCU 非適用)。
        """
        with self._disc_autocast_ctx():
            _y_d_r, y_d_g, fmap_r, fmap_g = self.model_d_mrd(
                y, y_hat, speaker_embeddings=spk_cond
            )
        n = self.model_d_mrd.n_resolutions
        uncond_g, cond_g = jcu_split(y_d_g, n)
        loss_adv, _ = generator_loss(uncond_g)
        loss_adv_cond = None
        if cond_g:
            loss_adv_cond, _ = generator_loss(cond_g)
            loss_adv = 0.5 * (loss_adv + loss_adv_cond)
        # FM loss は共有 body の fmap のみ (条件ヘッドは fmap を出さない)
        loss_fm = feature_loss(fmap_r, fmap_g)
        return loss_adv, loss_fm, loss_adv_cond

    def _mrd_discriminator_loss(self, y, y_hat_detached, spk_cond):
        """MRD の D 側 loss を返す ``(loss, loss_cond)`` (JCU は 1/2 ずつ平均)。"""
        with self._disc_autocast_ctx():
            y_d_r, y_d_g, _, _ = self.model_d_mrd(
                y, y_hat_detached, speaker_embeddings=spk_cond
            )
        n = self.model_d_mrd.n_resolutions
        uncond_r, cond_r = jcu_split(y_d_r, n)
        uncond_g, cond_g = jcu_split(y_d_g, n)
        loss, _, _ = discriminator_loss(uncond_r, uncond_g)
        loss_cond = None
        if cond_r:
            loss_cond, _, _ = discriminator_loss(cond_r, cond_g)
            loss = 0.5 * (loss + loss_cond)
        return loss, loss_cond

    # ------------------------------------------------------------------
    # v10b S-1b: 共進化 adversarial speaker classifier
    # ------------------------------------------------------------------

    def _adv_spk_ramp(self, epoch: int | None = None) -> float:
        """G 側敵対項の ramp 重み (0.0-1.0)。epoch のみの純関数 = DDP 整合。"""
        if epoch is None:
            epoch = self.current_epoch
        return swap_spk_ramp_weight(
            epoch,
            getattr(self.hparams, "adv_spk_start_epoch", 10),
            getattr(self.hparams, "adv_spk_ramp_epochs", 5),
        )

    def _adv_spk_classifier_active(
        self, epoch: int | None = None, has_speaker_ids: bool = True
    ) -> bool:
        """C 自身を更新するか。**step 0 から有効** (ramp に従わない)。

        C が未学習のまま G に「C を騙せ」と要求するとゴミ勾配を与えるため、
        分類器側は最初から学習させ、G 側の敵対項だけを ramp する
        (``_adv_spk_generator_active``)。この非対称性は意図的。

        判定は epoch / hparams / speaker_ids の有無のみに依存する — batch 内容
        や RNG に依存すると rank 間で分岐が食い違い、NCCL all_reduce mismatch
        (30 分 timeout、「CUDA illegal access」の偽装症状) になる。
        """
        del epoch  # C 側は epoch に依存しない (署名の対称性のために受ける)
        return (
            self.model_c_spk is not None
            and float(getattr(self.hparams, "c_adv_spk", 0.0) or 0.0) > 0
            and has_speaker_ids
        )

    def _adv_spk_generator_active(
        self, epoch: int | None = None, has_speaker_ids: bool = True
    ) -> bool:
        """G 側の敵対項 (生成音声 → 条件話者 CE) を足すか。ramp 後のみ。"""
        return (
            self._adv_spk_classifier_active(has_speaker_ids=has_speaker_ids)
            and self._adv_spk_ramp(epoch) > 0
        )

    def _adv_spk_classifier_loss_d(self, y, y_hat_detached, speaker_ids):
        """C 側の損失と監視統計を返す ``(loss, stats)``。

        **fake 入力に対する更新が仕様の核心** (plan §2.2): C の決定境界を
        生成分布上でも更新し続けることで、frozen encoder 型の静的な gaming 面
        (v10a §10 の崩壊機構) が構造的に成立しなくなる。
        """
        with self._disc_autocast_ctx():
            real_logits = self.model_c_spk(y)
            fake_logits = self.model_c_spk(y_hat_detached)
        fake_index = self.model_c_spk.fake_class_index
        loss = adv_speaker_classifier_loss_d(
            real_logits, fake_logits, speaker_ids, fake_index
        )
        stats = adv_speaker_classifier_stats(
            real_logits.detach(), fake_logits.detach(), speaker_ids, fake_index
        )
        return loss, stats

    def _adv_spk_classifier_loss_g(self, y_hat, speaker_ids):
        """G 側の損失: 生成音声が条件話者に分類されるよう CE 最小化。"""
        with self._disc_autocast_ctx():
            fake_logits = self.model_c_spk(y_hat)
        return adv_speaker_classifier_loss_g(fake_logits, speaker_ids)

    @staticmethod
    def _ddp_synced_is_finite(loss: torch.Tensor) -> bool:
        """全 rank 同期で loss が有限かを判定する (skip-batch 決定用)。

        DDP では loss skip が rank ごとにバラつくと all_reduce が mismatch して
        NCCL collective timeout (default 30 分後にプロセス終了) を引き起こす。
        ``is_finite`` を ``ReduceOp.MIN`` で同期し、**1 rank でも非有限なら
        全 rank で False** を返す (= 全 rank skip)。

        Single GPU や DDP 未初期化環境ではローカル判定のみ。
        """
        is_finite = torch.isfinite(loss).to(torch.uint8).reshape(())
        if torch.distributed.is_available() and torch.distributed.is_initialized():
            torch.distributed.all_reduce(is_finite, op=torch.distributed.ReduceOp.MIN)
        return is_finite.item() == 1

    def _update_kl_cap_guard(self, kl_raw: float) -> None:
        """Detect raw KL pinned at the ``_KL_CAP`` safety cap and abort.

        2026-08 v8 incident: a silently broken Super-MAS kernel corrupted the
        MAS alignments, keeping raw KL at the cap for a *whole 80-epoch run*
        while every other health signal (non_finite_skip=0%, decreasing mel)
        looked normal. The cap masks divergence from the non-finite skip
        machinery by design, so the guard watches the *raw* (pre-clamp,
        pre-weight) value: hundreds of consecutive capped steps mean the KL
        term carries no gradient signal and continuing the run only burns GPU
        hours on garbage. Aborting loudly is strictly cheaper.

        DDP note: the divergence lives in the replicated weights, so all
        ranks cross the threshold within a few steps of each other; the first
        rank to raise takes the whole job down via NCCL error propagation.
        This crash-style stop is intentional for an unrecoverable state.

        NaN raw KL does not count as capped (``nan >= cap`` is False) — that
        case is handled by the non-finite skip machinery instead.

        Env override: ``PIPER_PLUS_KL_CAP_ABORT_STEPS`` (default 300,
        0 disables the abort; the error logs still fire).
        """
        if not kl_raw >= _KL_CAP:
            self._kl_cap_consecutive = 0
            return

        self._kl_cap_consecutive += 1
        if self._kl_cap_consecutive % 50 == 0:
            _LOGGER.error(
                "Raw KL has been pinned at the %.0e cap for %d consecutive "
                "steps (step=%s) — the KL term carries no gradient signal. "
                "Training has likely diverged (check MAS alignments and "
                "loss_dur; see PIPER_PLUS_DISABLE_SUPER_MAS).",
                _KL_CAP,
                self._kl_cap_consecutive,
                self.global_step,
            )
        if 0 < self._kl_cap_abort_steps <= self._kl_cap_consecutive:
            raise RuntimeError(
                f"Raw KL pinned at the {_KL_CAP:.0e} cap for "
                f"{self._kl_cap_consecutive} consecutive steps "
                f"(step={self.global_step}). Training has diverged and cannot "
                f"recover — aborting instead of completing a garbage run. "
                f"Check MAS alignment integrity (PIPER_PLUS_DISABLE_SUPER_MAS "
                f"=1 forces the Cython reference) and loss_dur before "
                f"resuming. Set PIPER_PLUS_KL_CAP_ABORT_STEPS=0 to disable "
                f"this guard."
            )

    def _grad_probe_due(self) -> bool:
        """この step が per-loss grad-norm probe の対象かを判定する (A-1c)。

        判定は ``global_step`` と hparams のみに依存するため DDP 全 rank で
        同一の結果になる (rank 分岐で autograd を呼ばないための前提条件)。
        無効時 (default: grad_probe_every=0) は int 比較 1 回で即 False を
        返し、テンソル操作は一切発生しない。
        """
        every = int(self.hparams.get("grad_probe_every", 0) or 0)
        if every <= 0 or not self.training or not torch.is_grad_enabled():
            return False
        return self.global_step % every == 0

    def _run_grad_probe(self, batch: Batch) -> None:
        """収集済み loss 成分の勾配ノルムを probe して logger に記録する。

        combined backward (``manual_backward(loss_g)``) の**前**に呼ぶこと。
        probe 内の ``torch.autograd.grad`` は全て ``retain_graph=True`` かつ
        ``.grad`` 非蓄積のため本 backward を壊さない。また AccumulateGrad を
        経由しないので DDP reducer の hook も発火しない (all_reduce mismatch
        を起こさない)。DDP 安全性のため probe 自体は全 rank で同一に実行し、
        log のみ rank 0 に限定する (``rank_zero_only=True`` + sync なし)。
        """
        from .grad_probe import collect_probe_params, compute_grad_probe

        losses = self._grad_probe_losses
        # 消費と同時に必ず参照を手放す (graph を step を跨いで保持しない)
        self._grad_probe_losses = None
        if not losses:
            return
        try:
            probe_params = collect_probe_params(self.model_g)
            if not probe_params:
                return
            metrics = compute_grad_probe(losses, probe_params)
        except RuntimeError:
            # 診断機能で学習本体を落とさない。graph は retain_graph=True で
            # 保持されたままなので後続の manual_backward は影響を受けない。
            _LOGGER.exception(
                "grad probe failed at step=%d (training continues)",
                self.global_step,
            )
            return
        batch_size = batch.phoneme_ids.size(0)
        for key, value in metrics.items():
            self.log(
                key,
                value,
                batch_size=batch_size,
                rank_zero_only=True,
                sync_dist=False,
            )

    def _telemetry_due(self) -> bool:
        """この step が変調統計テレメトリ (v11 D-2) の対象かを判定する。

        ``global_step`` と hparams のみに依存するため DDP 全 rank で同一
        (rank 分岐で計算量が変わっても collective を含まないので安全側だが、
        due 判定自体も決定論に揃えておく)。無効時 (telemetry_every=0) は
        int 比較 1 回で即 False。
        """
        every = int(self.hparams.get("telemetry_every", 0) or 0)
        if every <= 0 or not self.training:
            return False
        return self.global_step % every == 0

    def _log_modulation_telemetry(
        self, batch: Batch, speaker_embeddings, language_ids
    ) -> None:
        """各注入点の変調統計 (話者依存分散比ほか) を logger に記録する。

        全て ``torch.no_grad`` の発話単位 1x1 conv/MLP なので計算コストは
        無視できる。DDP 安全性のため log は rank 0 のみ (sync なし) —
        ``_run_grad_probe`` と同じ流儀。診断機能で学習本体は落とさない。
        """
        from .telemetry import collect_modulation_telemetry

        try:
            metrics = collect_modulation_telemetry(
                self.model_g,
                speaker_embeddings,
                lid=language_ids,
                speaker_ids=batch.speaker_ids,
            )
        except RuntimeError:
            _LOGGER.exception(
                "modulation telemetry failed at step=%d (training continues)",
                self.global_step,
            )
            return
        batch_size = batch.phoneme_ids.size(0)
        for key, value in metrics.items():
            self.log(
                key,
                value,
                batch_size=batch_size,
                rank_zero_only=True,
                sync_dist=False,
            )

    def training_step(self, batch: Batch, batch_idx: int):
        # Manual optimization for multiple optimizers
        opt_g, opt_d = self.optimizers()

        # D:G update ratio: G forward is always needed (produces _y, _y_hat for D),
        # but G backward+step only runs every d_update_interval steps.
        d_update_interval = self.hparams.d_update_interval
        grad_clip = getattr(self.hparams, "grad_clip", None)
        update_generator = self.global_step % d_update_interval == 0

        # Periodic batch-info log for debugging (CUDA illegal access の発生位置特定用)
        if batch_idx % 50 == 0:
            try:
                _LOGGER.info(
                    "[batch-info] step=%d batch_idx=%d B=%d phoneme_max=%d "
                    "audio_max=%d spec_max=%d",
                    self.global_step,
                    batch_idx,
                    batch.phoneme_ids.shape[0],
                    int(batch.phoneme_lengths.max().item()),
                    int(batch.audio_lengths.max().item()),
                    int(batch.spectrogram_lengths.max().item()),
                )
            except Exception:
                pass

        # Always run G forward pass (needed for _y, _y_hat used by D)
        loss_g = self.training_step_g(batch)

        # Forward NaN/Inf detection: backward 中の数値的問題および DDP の
        # all_reduce mismatch (30 分タイムアウト → "CUDA illegal" 偽装) を防ぐため、
        # loss が non-finite なら batch ごと skip する。DDP 全 rank で同期する。
        if not self._ddp_synced_is_finite(loss_g):
            local_finite = bool(torch.isfinite(loss_g).item())
            _LOGGER.warning(
                "Non-finite loss_g detected (DDP-synced skip) at step=%d, "
                "batch_idx=%d, local_finite=%s. Skipping batch to maintain "
                "all_reduce consistency.",
                self.global_step,
                batch_idx,
                local_finite,
            )
            self._log_with_batch_info("non_finite_skip", 1.0, batch)
            opt_g.zero_grad(set_to_none=True)
            opt_d.zero_grad(set_to_none=True)
            self._y = None
            self._y_hat = None
            self._spk_cond = None
            # T1 (A-1c): skip 時も probe 用の loss 参照を解放 (graph を保持しない)
            self._grad_probe_losses = None
            return

        # T1 (roadmap A-1c): per-loss grad-norm probe。combined backward の前に
        # retain_graph=True で各 loss 成分の勾配ノルムを測る (probe due の step
        # のみ dict が置かれる。DDP 全 rank で同一に実行、log は rank 0 のみ)。
        if self._grad_probe_losses is not None:
            self._run_grad_probe(batch)

        if update_generator:
            # Train generator: backward + optimizer step
            opt_g.zero_grad()
            self.manual_backward(loss_g)
            if grad_clip is not None:
                torch.nn.utils.clip_grad_norm_(self.model_g.parameters(), grad_clip)
            opt_g.step()
        else:
            # Skip G update on this step (D-only step)
            self._log_with_batch_info("g_step_skipped", 1.0, batch)

        # v10 §3.3 (Latent Filling): LF step は LFCL のみで G を更新し、D 更新
        # は skip する (論文準拠 — s̃ に対応する実波形が存在しないため D の
        # real/fake ペアが定義できない)。should_run_latent_filling_step が
        # global_step の決定論的関数なので全 rank が同時に skip し DDP 整合が
        # 保たれる。LF は G 更新 step に限定される (d_update_interval 配線)
        # ため、ここに来た時点で opt_g.step() は必ず実行済み = global_step は
        # 前進しており、update_generator=False との重なりで optimizer.step()
        # ゼロのまま return する決定論的ラッチは構造的に起きない。
        if self._lf_step_active:
            self._lf_step_active = False
            self._log_with_batch_info("lf_step", 1.0, batch)
            self._y = None
            self._y_hat = None
            self._spk_cond = None
            return

        # Train discriminator (every step)
        opt_d.zero_grad()
        loss_d = self.training_step_d(batch)

        # DDP-synced finite check for D (同上: 全 rank 同期で skip)
        if not self._ddp_synced_is_finite(loss_d):
            local_finite = bool(torch.isfinite(loss_d).item())
            _LOGGER.warning(
                "Non-finite loss_d (DDP-synced skip) at step=%d, batch_idx=%d, "
                "local_finite=%s. Skipping D update.",
                self.global_step,
                batch_idx,
                local_finite,
            )
            opt_d.zero_grad(set_to_none=True)
            self._y = None
            self._y_hat = None
            self._spk_cond = None
            return

        self.manual_backward(loss_d)
        if grad_clip is not None:
            d_params = list(self.model_d.parameters())
            if self.model_d_wavlm is not None:
                d_params = d_params + list(self.model_d_wavlm.parameters())
            if self.model_d_mrd is not None:
                d_params = d_params + list(self.model_d_mrd.parameters())
            if self.model_c_spk is not None:
                d_params = d_params + list(self.model_c_spk.parameters())
            torch.nn.utils.clip_grad_norm_(d_params, grad_clip)
        opt_d.step()

        # Clear instance variables to release references
        self._y = None
        self._y_hat = None
        self._spk_cond = None

        # NOTE (perf, 2026-07-09): 500-batch 周期の
        # ``torch.cuda.synchronize() + torch.cuda.empty_cache()`` flush を撤去。
        # T4/V100 (16GB) 時代に memory fragmentation 対策で入れたが、
        #   * A100 SXM4 80GB / H100 等の現行 GPU では VRAM に十分な余裕がある
        #   * ``PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`` で caching
        #     allocator が fragmentation を自律解消する
        #   * ``synchronize()`` は全 outstanding CUDA op を待ち、続く
        #     ``empty_cache()`` で allocator を丸ごと reset するため 500 batch
        #     ごとに数百 ms 〜数秒の GPU 停止が発生し throughput を落とす
        # 期待効果: +2-3% throughput (500 batch 毎の GPU 全停止除去)。
        # 旧挙動を復旧する必要が出た場合は CLI ``--enable-legacy-flush`` を
        # 追加して ``MEMORY_CLEANUP_FREQUENCY`` gated な flush を再有効化する
        # (今のところ需要が確認されるまでは未実装)。

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

    def _latent_filling_step_g(
        self,
        batch: Batch,
        x,
        x_lengths,
        spec,
        spec_lengths,
        language_ids,
        prosody_features,
        speaker_embeddings,
    ):
        """Latent Filling step の G 損失 (v10 §3.3、arXiv:2310.03538 準拠)。

        条件 embedding を s̃ (同一言語 2 話者の λ~Beta(0.5,0.5) 補間 or
        s + N(0, 1e-4)) に置換して通常 forward し、generator 損失を
        LFCL = 1 - cos(CAM++(y_hat), s̃) **のみ**に置換する。s̃ は実在参照を
        持たないため recon/mel/KL/GAN は定義できず skip する (論文準拠)。
        D 更新 skip は training_step が ``_lf_step_active`` flag で行う。

        NaN ガードについて: LFCL が G 損失の全体なので、既存 SCL のような
        「0 を返す」ガードは graph を失い ``manual_backward`` が失敗する。
        non-finite はそのまま返し、training_step の DDP-synced non-finite
        skip (全 rank 一致) に処理を委ねる。
        """
        self._lf_step_active = True
        # LF step は mel/kl 等の probe 対象成分を持たない — probe は見送る
        # (graph を跨いで保持しないよう参照も解放)
        self._grad_probe_losses = None

        # 乱数は global_step 由来 seed の CPU generator から引く: 再現性 +
        # グローバル RNG stream (rand_slice_segments 等) を汚さない
        g_lf = torch.Generator()
        g_lf.manual_seed((int(self.global_step) * 2654435761 + 0x9E3779B9) % (2**63))
        # speaker_ids を渡し同一話者ペアの補間 (≒恒等) を除外する。
        # language-balanced sampling + samples_per_speaker>1 では言語グループ
        # が 1 話者の複数発話だけになる batch が典型的にあり、これがないと
        # 補間 branch が同一話者補間に希釈される
        s_tilde = build_latent_filling_embeddings(
            speaker_embeddings,
            language_ids=language_ids,
            speaker_ids=batch.speaker_ids,
            generator=g_lf,
        )

        g_output = self.model_g(
            x,
            x_lengths,
            spec,
            spec_lengths,
            None,  # sid=None: spk_proj is the sole speaker conditioning path
            lid=language_ids,
            prosody_features=prosody_features,
            speaker_embeddings=s_tilde,
            # v10b S-2: LF step も decoder を通るので F0 が要る。s̃ は実在参照を
            # 持たない架空話者なので GT F0 は使わず、常に予測 F0 で走らせる
            # (この step の損失は LFCL のみで、F0 回帰は課さない)。
            f0=getattr(batch, "f0", None),
            f0_pred_prob=1.0,
        )
        y_hat = g_output.waveform
        # D は skip されるが、non-finite skip 経路が self._y/_y_hat を触るため
        # 参照を一貫させておく
        self._y_hat = y_hat.contiguous()
        self._y = None
        self._spk_cond = None

        with autocast(self.device.type, enabled=False):
            with self._scl_autocast_ctx():
                emb_gen = self.scl_encoder(y_hat.squeeze(1).float())
                loss_lf = (
                    1.0 - F.cosine_similarity(emb_gen, s_tilde.float(), dim=-1)
                ).mean()
            self._log_with_batch_info("loss_lf", loss_lf, batch)
        return loss_lf

    def training_step_g(self, batch: Batch):
        (
            x,
            x_lengths,
            y,
            _,
            spec,
            spec_lengths,
            _speaker_ids,
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
        speaker_embeddings = getattr(batch, "speaker_embeddings", None)

        # T1 (roadmap A-1c): probe due の step でのみ loss 成分収集 dict を
        # 用意する。無効時は None のままで、以降の収集は全て None チェック
        # 1 回に潰れる (テンソル演算・graph 保持なし = 既存動作に影響ゼロ)。
        probe_losses: dict[str, torch.Tensor] | None = (
            {} if self._grad_probe_due() else None
        )
        self._grad_probe_losses = probe_losses

        # Speaker embedding perturbation for zero-shot generalization.
        # v10 F7: default は 0.0 (無効)。σ=0.05 は Latent Filling の文献値
        # σ=1e-4 の 500 倍で破壊的と判明 (design doc F7、Phase 0 Arm D)。
        # v9 以前の再現は --spk-emb-noise-sigma 0.05 の明示指定で可能。
        # NOTE: noise 加算後に L2 再正規化を行う。CAM++ 出力 (norm=1.0) に対し、
        # ``+ N(0, σ² I)`` を加えると期待 norm が ``√(1 + σ²·dim)`` (sigma=0.05,
        # dim=192 で約 1.22) に増加する。再正規化しないと spk_proj の入力分布が
        # train/inference で magnitude 不一致 (~22%) となり、学習進行と共に
        # spk_proj の重み増大に伴って ``log_softmax(student_emb / τ)`` が発散、
        # ``loss_dino`` が NaN マスクで 0 に貼り付く現象が発生する
        # (multi-6lang スクラッチで step ~1249 から実測)。
        if self.training and speaker_embeddings is not None:
            sigma = getattr(self.hparams, "spk_emb_noise_sigma", 0.0)
            speaker_embeddings = (
                speaker_embeddings + torch.randn_like(speaker_embeddings) * sigma
            )
            speaker_embeddings = torch.nn.functional.normalize(
                speaker_embeddings, p=2, dim=-1
            )

        # v11 D-2: 変調統計テレメトリ (--telemetry-every、default 500 step 毎)。
        # forward に依存しない (g からの発話単位 1x1 conv のみ) ので LF 分岐の
        # 前に置き、due step では必ず記録する。noise 加算「後」の embedding =
        # 実際に conditioning に使う値で測る。
        if speaker_embeddings is not None and self._telemetry_due():
            self._log_modulation_telemetry(batch, speaker_embeddings, language_ids)

        # --- Latent Filling step (v10 §3.3、arXiv:2310.03538 準拠) ---
        # 確率 τ の step で条件 embedding を s̃ (同一言語補間 or 微小 noise) に
        # 置換し、G の損失を LFCL のみに置換する (recon/mel/KL/GAN skip。
        # D 更新 skip は training_step 側が _lf_step_active flag で行う)。
        # should_run_latent_filling_step は global_step の決定論的関数なので
        # 全 rank が同時に LF step になり DDP の all_reduce 整合が保たれる。
        # d_update_interval を配線するのはラッチ防止 (G 更新なしの D-only
        # step で LF が発動すると optimizer.step() ゼロ → global_step 凍結 →
        # 全 batch が永久に同一分岐の no-op になる)。詳細は
        # should_run_latent_filling_step の docstring 参照。
        self._lf_step_active = False
        if self.training and speaker_embeddings is not None:
            lf_tau = float(getattr(self.hparams, "latent_filling_tau", 0.0) or 0.0)
            if (
                lf_tau > 0
                and self.scl_encoder is not None
                and should_run_latent_filling_step(
                    self.global_step,
                    lf_tau,
                    d_update_interval=self.hparams.d_update_interval,
                )
            ):
                return self._latent_filling_step_g(
                    batch,
                    x,
                    x_lengths,
                    spec,
                    spec_lengths,
                    language_ids,
                    prosody_features,
                    speaker_embeddings,
                )

        # --- v10b S-2: GT F0 と teacher forcing 確率 ---
        # 有効化したのに F0 キャッシュが無い構成は黙って劣化させず即エラーに
        # する (無言で S-2 なしの学習が 1 週間走るほうが遥かに高くつく)。
        f0_gt = None
        f0_pred_prob = 0.0
        if self.hparams.use_f0_path:
            f0_gt = getattr(batch, "f0", None)
            if f0_gt is None:
                raise RuntimeError(
                    "use_f0_path is enabled but the batch carries no GT F0. "
                    "Run `python -m piper_train.tools.extract_f0 --dataset "
                    "<dataset.jsonl> --output-dir <dataset_dir>/f0` first, or "
                    "point --f0-dir at an existing cache."
                )
            f0_pred_prob = f0_teacher_forcing_prob(
                self.current_epoch,
                self.hparams.f0_teacher_forcing_epochs,
                self.hparams.f0_teacher_forcing_ramp,
                self.hparams.f0_pred_prob_max,
            )

        g_output = self.model_g(
            x,
            x_lengths,
            spec,
            spec_lengths,
            None,  # sid=None: emb_g disabled, spk_proj is the sole speaker conditioning path
            lid=language_ids,
            prosody_features=prosody_features,
            speaker_embeddings=speaker_embeddings,
            f0=f0_gt,
            f0_pred_prob=f0_pred_prob,
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
        # v10b S-1a: JCU MRD の条件は **noise 加算後** の embedding
        # (conditioning に使ったものと同一) を D 更新でも使う
        self._spk_cond = speaker_embeddings

        # T6: Discriminator forward runs under _disc_autocast_ctx (nullcontext by
        # default; bf16 or fp32 override when disc_precision != "inherit").
        with self._disc_autocast_ctx():
            _y_d_hat_r, y_d_hat_g, fmap_r, fmap_g = self.model_d(y, y_hat)

        with autocast(self.device.type, enabled=False):
            # KL annealing: linearly increase from 0.1*c_kl to c_kl
            if (
                self.hparams.kl_annealing_epochs > 0
                and self.current_epoch < self.hparams.kl_annealing_epochs
            ):
                kl_weight = self.hparams.c_kl * (
                    0.1 + 0.9 * self.current_epoch / self.hparams.kl_annealing_epochs
                )
            else:
                kl_weight = self.hparams.c_kl

            # Generator loss
            loss_dur = torch.sum(l_length.float())
            # Clamp SDP NLL to prevent loss_dur from dominating loss_gen_all
            loss_dur = torch.clamp(loss_dur, min=-100.0)
            loss_mel = F.l1_loss(y_mel, y_hat_mel) * self.hparams.c_mel
            # Cap raw kl_loss to 1e4 as an extra safety net independent of the
            # logs_p / m_p source clamps in models.py. Even with tight source
            # clamps ([-8, 8] and [-100, 100]), the worst-case
            # ((z_p - m_p)^2) * exp(-2 * logs_p) product can approach fp32 max
            # during the first few dozen batches when the flow / prior are
            # completely random. Capping at 1e4 preserves the gradient
            # direction (relu-like clip) while preventing runaway magnitudes
            # that overwhelm gradient_clip_val=1.0. Once training stabilises
            # (typically < 100 batches) kl_loss falls below 100 and the cap
            # becomes a no-op. Observed on v8 A100 SXM4 real-config smoke:
            # without this cap, batch 31 onwards diverges 100% (262/300 skip)
            # despite the source clamps.
            # v10 M1 (SNAC flow): flow forward の logdet を KL に配線する。
            # log p(z) = log N(flow(z); m_p, logs_p) + logdet なので負号で
            # 効く (kl_loss 内部で - Σ logdet / Σ z_mask)。snac off では
            # flow_logdet=None で従来と厳密一致。
            loss_kl_raw = kl_loss(
                z_p, logs_q, m_p, logs_p, z_mask, logdet=g_output.flow_logdet
            )
            loss_kl = loss_kl_raw.clamp(max=_KL_CAP) * kl_weight
            # The cap hides divergence from the non-finite skip machinery, so
            # watch the raw value for cap sticking (aborts an unrecoverable
            # run — see _update_kl_cap_guard).
            self._update_kl_cap_guard(float(loss_kl_raw.detach()))

            loss_fm = feature_loss(fmap_r, fmap_g)
            loss_gen, _losses_gen = generator_loss(y_d_hat_g)

            loss_gen_all = loss_gen + loss_fm + loss_mel + loss_dur + loss_kl

            # T1 (A-1c): grad probe 用に loss 成分を収集 (probe due の step のみ)
            if probe_losses is not None:
                probe_losses["mel"] = loss_mel
                probe_losses["kl"] = loss_kl
                probe_losses["mpd_msd"] = loss_gen + loss_fm

            # MB-iSTFT: sub-band STFT loss
            if o_mb is not None:
                y_mb = self.pqmf.analysis(y)  # GT subbands [B, 4, T//4]
                loss_sub_stft = self.sub_stft_loss(o_mb, y_mb) * self.hparams.c_sub_stft
                loss_gen_all = loss_gen_all + loss_sub_stft
                self._log_with_batch_info("loss_sub_stft", loss_sub_stft, batch)
                if probe_losses is not None:
                    probe_losses["sub_stft"] = loss_sub_stft

            # --- v10b S-2p: F0 / V-UV predictor の GT 回帰 loss ---
            # GT frame-level F0 を教師とする per-frame 回帰であり、生成音声の
            # F0 統計は一切参照しない (zs-eval-contract §2 禁止事項 4 の
            # 例外条項に正面から乗る形。構造ガードは
            # tests/test_f0_contract_guard.py)。
            if g_output.f0_pred is not None and batch.f0 is not None:
                loss_f0_raw, loss_vuv_raw = f0_prediction_loss(
                    g_output.f0_pred[0],
                    g_output.f0_pred[1],
                    batch.f0,
                    batch.vuv,
                    z_mask,
                )
                loss_f0 = loss_f0_raw * self.hparams.c_f0
                loss_vuv = loss_vuv_raw * self.hparams.c_vuv
                loss_gen_all = loss_gen_all + loss_f0 + loss_vuv
                self._log_with_batch_info("loss_f0", loss_f0, batch)
                self._log_with_batch_info("loss_vuv", loss_vuv, batch)
                self._log_with_batch_info("f0_pred_prob", f0_pred_prob, batch)
                if probe_losses is not None:
                    probe_losses["f0"] = loss_f0 + loss_vuv

            # Full-band linear-frequency MR-STFT loss (v9, opt-in)
            if self.hparams.c_full_stft > 0:
                loss_full_stft = (
                    self.full_stft_loss(y_hat, y) * self.hparams.c_full_stft
                )
                loss_gen_all = loss_gen_all + loss_full_stft
                self._log_with_batch_info("loss_full_stft", loss_full_stft, batch)
                if probe_losses is not None:
                    probe_losses["full_stft"] = loss_full_stft

            # --- v11 柱2 (A2'): 6-11kHz band-weighted GT 参照 MR-STFT (opt-in) ---
            # GT waveform y を教師とする magnitude 回帰 (zs-eval-contract §2 の
            # 例外形 = mel / sub-band STFT / MRD と同族)。E-4 コム指標や帯域
            # 評価メトリクスの loss 化ではない (import 隔離は
            # scripts/check_zs_metric_isolation.py が強制)。mel L1 が実質盲目な
            # 帯域に GAN がノイズを置く経路 (trainable PQMF ドリフト事故、
            # 残存ノイズ診断 doc §3) への regression 側の防壁。
            if self.hparams.c_hiband_stft > 0:
                loss_hiband_stft = (
                    self.hiband_stft_loss(y_hat, y) * self.hparams.c_hiband_stft
                )
                loss_gen_all = loss_gen_all + loss_hiband_stft
                self._log_with_batch_info("loss_hiband_stft", loss_hiband_stft, batch)
                if probe_losses is not None:
                    probe_losses["hiband_stft"] = loss_hiband_stft

            # --- v11 A′ L_src hinge (opt-in、σ 氾濫の事前登録緩和策) ---
            # carrier head の枝エネルギー比のみを参照 (評価器を消費しない、
            # harmonic-head 設計 doc §4.3)。default 0 = off。
            if (
                self.hparams.c_src_reg > 0
                and getattr(self.model_g.dec, "last_carrier_energies", None) is not None
                and g_output.f0_decoder is not None
            ):
                e_h, e_n = self.model_g.dec.last_carrier_energies
                loss_src_reg = (
                    carrier_source_regularization(
                        e_h, e_n, f0=g_output.f0_decoder, tau=self.hparams.src_reg_tau
                    )
                    * self.hparams.c_src_reg
                )
                loss_gen_all = loss_gen_all + loss_src_reg
                self._log_with_batch_info("loss_src_reg", loss_src_reg, batch)
                if probe_losses is not None:
                    probe_losses["src_reg"] = loss_src_reg

            # --- Speaker Consistency Loss (SCL) ---
            # B-3 (v10 roadmap、opt-in): SCL 専用に posterior z を detach した
            # decoder forward を追加する。SCL 勾配は g (spk_proj / emb_lang) と
            # decoder のみに流れ、enc_q (posterior) には流れない — 「decoder が
            # GT 由来の z から音色を読んで SCL を満たす」posterior leak 経路を
            # 遮断する。主経路の y_hat は従来どおり mel/GAN loss で enc_q を
            # 学習するため、この re-forward は autocast 文脈 (bf16 可) で行い、
            # 数値精度は下の fp32 ctx 内の .float() cast で従来と揃える。
            scl_wave = y_hat
            if (
                getattr(self.hparams, "scl_detach_z", False)
                and self.hparams.c_spk > 0
                and speaker_embeddings is not None
                and self.scl_encoder is not None
            ):
                scl_wave = self.model_g.scl_waveform_detached_z(
                    g_output.latents[0],
                    ids_slice,
                    speaker_embeddings=speaker_embeddings,
                    lid=language_ids,
                    f0=g_output.f0_decoder,
                )

            # T6: SCL is explicitly wrapped in _scl_autocast_ctx (= autocast
            # enabled=False) so a future refactor cannot silently hoist SCL out
            # of the outer fp32 block and expose it to bf16 numerics.
            with self._scl_autocast_ctx():
                # Differentiable torch CAM++ path (v8.1, primary when loaded):
                # gradient flows y_hat → decoder。ONNX 経路より優先。
                if (
                    self.hparams.c_spk > 0
                    and speaker_embeddings is not None
                    and self.scl_encoder is not None
                ):
                    gen_embedding = self.scl_encoder(scl_wave.squeeze(1).float())
                    ref_embedding = speaker_embeddings.float()
                    if self.hparams.spk_loss_type == "infonce":
                        positive_mode = getattr(
                            self.hparams, "spk_loss_positives", "same_utt"
                        )
                        if positive_mode == "cross_utt" and batch.speaker_ids is None:
                            # cross_utt は speaker_ids 必須 — 欠落時は従来挙動で
                            # 継続 (single-speaker FT 等)。黙って劣化しないよう警告
                            if not self._warned_cross_utt_no_sid:
                                _LOGGER.warning(
                                    "spk_loss_positives='cross_utt' requires "
                                    "speaker_ids but batch has none — falling "
                                    "back to 'same_utt' positives"
                                )
                                self._warned_cross_utt_no_sid = True
                            positive_mode = "same_utt"
                        # v10 §3.2: --spk-loss-gather で DDP 全 rank の embedding
                        # を結合 (勾配が通る torch.distributed.nn.all_gather —
                        # 素の all_gather は勾配を切る)。負例 28 → world_size 倍
                        gen_for_loss = gen_embedding
                        ref_for_loss = ref_embedding
                        sids_for_loss = batch.speaker_ids
                        if getattr(self.hparams, "spk_loss_gather", False):
                            gen_for_loss, ref_for_loss, sids_for_loss = (
                                gather_speaker_loss_inputs(
                                    gen_for_loss, ref_for_loss, sids_for_loss
                                )
                            )
                        loss_spk = (
                            speaker_infonce_loss(
                                gen_for_loss,
                                ref_for_loss,
                                speaker_ids=sids_for_loss,
                                temperature=getattr(
                                    self.hparams, "spk_loss_temperature", 0.07
                                ),
                                positive_mode=positive_mode,
                            )
                            * self.hparams.c_spk
                        )
                    else:
                        loss_spk = (
                            speaker_consistency_loss(gen_embedding, ref_embedding)
                            * self.hparams.c_spk
                        )
                    loss_gen_all = loss_gen_all + loss_spk
                    self._log_with_batch_info("loss_spk", loss_spk, batch)
                    if probe_losses is not None:
                        probe_losses["spk"] = loss_spk
                # CAM++ ONNX encoder path (fallback)。ORT session は backprop
                # 不能なため torch.no_grad — この経路の loss_spk は勾配ゼロで
                # **monitoring にしかならない** (v7/v8 で loss_spk が動かなかった
                # 根因、design doc §3.15)。学習で効かせるには
                # --speaker-encoder-torch-path を使うこと。
                elif (
                    self.hparams.c_spk > 0
                    and speaker_embeddings is not None
                    and self.speaker_encoder is not None
                ):
                    with torch.no_grad():
                        gen_embedding = self.speaker_encoder(y_hat.squeeze(1))
                    loss_spk = (
                        speaker_consistency_loss(
                            gen_embedding, speaker_embeddings.float()
                        )
                        * self.hparams.c_spk
                    )
                    loss_gen_all = loss_gen_all + loss_spk
                    self._log_with_batch_info("loss_spk", loss_spk, batch)
                    # ONNX no-grad 経路の loss_spk は勾配ゼロだが、probe 側は
                    # requires_grad=False をゼロノルムとして記録できる
                    if probe_losses is not None:
                        probe_losses["spk"] = loss_spk
                # Mel-domain SCL fallback (differentiable, no external encoder needed)
                elif (
                    self.hparams.num_speakers > 1
                    and self.hparams.c_spk > 0
                    and self.speaker_encoder is None
                    and self.scl_encoder is None
                ):
                    loss_spk = mel_speaker_consistency_loss(
                        y_hat,
                        y,
                        n_fft=self.hparams.filter_length,
                        n_mels=self.hparams.mel_channels,
                        hop_length=self.hparams.hop_length,
                        win_length=self.hparams.win_length,
                        sample_rate=self.hparams.sample_rate,
                        mel_fmin=self.hparams.mel_fmin,
                        mel_fmax=self.hparams.mel_fmax,
                    )
                    loss_gen_all = loss_gen_all + loss_spk * self.hparams.c_spk
                    self._log_with_batch_info("loss_spk", loss_spk, batch)
                    # probe は loss_gen_all への寄与 (重み付き) を記録する
                    if probe_losses is not None:
                        probe_losses["spk"] = loss_spk * self.hparams.c_spk

            # --- S1 swap-SCL (v10 §3.1、ASCL 型) ---
            # batch 内の同一言語別話者 embedding g_q で flow を逆走させた波形に
            # speaker loss を当てる。z_p の中身は元話者由来なので decoder は
            # z から目標話者 q の音色を読めず、same-utt Goodhart が経路的に
            # 不可能 (F2)。flow reverse + decoder FiLM に初めて話者勾配が届く。
            # weight は KL annealing 完了後 (start_epoch) から ramp (§3.4)。
            c_swap = float(getattr(self.hparams, "c_swap_spk", 0.0) or 0.0)
            if (
                self.training
                and c_swap > 0
                and speaker_embeddings is not None
                and self.scl_encoder is not None
            ):
                ramp = swap_spk_ramp_weight(
                    self.current_epoch,
                    getattr(self.hparams, "swap_spk_start_epoch", 10),
                    getattr(self.hparams, "swap_spk_ramp_epochs", 5),
                )
                if ramp > 0:
                    # perm は global_step 由来 seed で決定論 (グローバル RNG
                    # stream を消費しない — default-off 経路の再現性を守る)。
                    # speaker_ids を渡し同一話者ペアを valid=False にする:
                    # swap 相手が同一話者だと z_p の中身の話者 = 目標話者と
                    # なり「decoder が z から目標話者の音色を読めない」という
                    # Goodhart 耐性 (design doc §3.1 / F2) が崩れ、swap-SCL が
                    # 通常 SCL に退化するため
                    g_swap = torch.Generator()
                    g_swap.manual_seed(
                        (int(self.global_step) * 2654435761 + 0x517CC1B7) % (2**63)
                    )
                    perm, valid_mask = build_same_language_permutation(
                        speaker_embeddings.size(0),
                        language_ids=language_ids,
                        speaker_ids=batch.speaker_ids,
                        generator=g_swap,
                    )
                    if bool(valid_mask.any()):
                        # noise 加算後の embedding を流用 (σ default 0.0)
                        emb_q = speaker_embeddings[perm]
                        y_swap = self.model_g.swap_scl_waveform(
                            z_p,
                            z_mask,
                            ids_slice,
                            speaker_embeddings=emb_q,
                            lid=language_ids,  # lid は自分の行のまま (テキストの言語は不変)
                            # S-2: 主経路と同一の F0 スライス。話者だけを
                            # 入れ替える ASCL の趣旨どおり、位相参照は動かさない
                            f0=g_output.f0_decoder,
                        )
                        with self._scl_autocast_ctx():
                            emb_gen_swap = self.scl_encoder(y_swap.squeeze(1).float())
                            emb_q_ref = emb_q.float()
                            # NaN ガード: 既存 SCL と同じく 0 を返す (additive
                            # なので loss_gen_all の graph は保たれる)
                            if (
                                torch.isnan(emb_gen_swap).any()
                                or torch.isnan(emb_q_ref).any()
                            ):
                                loss_swap = torch.tensor(
                                    0.0, device=emb_gen_swap.device
                                )
                            else:
                                cos_swap = F.cosine_similarity(
                                    emb_gen_swap, emb_q_ref, dim=-1
                                )
                                valid_mask = valid_mask.to(cos_swap.device)
                                loss_swap = (1.0 - cos_swap)[valid_mask].mean()
                        loss_swap_spk = loss_swap * (c_swap * ramp)
                        loss_gen_all = loss_gen_all + loss_swap_spk
                        self._log_with_batch_info("loss_swap_spk", loss_swap_spk, batch)
                        if probe_losses is not None:
                            probe_losses["swap_spk"] = loss_swap_spk

            # --- DINO Self-Distillation Loss ---
            if (
                self.hparams.c_dino > 0
                and speaker_embeddings is not None
                and self.spk_proj_teacher is not None
            ):
                student_emb = self.model_g.spk_proj(speaker_embeddings)
                with torch.no_grad():
                    teacher_emb = self.spk_proj_teacher(speaker_embeddings)
                loss_dino = (
                    dino_loss(student_emb, teacher_emb, self.dino_center)
                    * self.hparams.c_dino
                )
                loss_gen_all = loss_gen_all + loss_dino
                self._log_with_batch_info("loss_dino", loss_dino, batch)
                if probe_losses is not None:
                    probe_losses["dino"] = loss_dino

                # EMA update for teacher
                if self.training:
                    with torch.no_grad():
                        # spk_proj_teacher の重みは student と一緒に NaN になる
                        # 可能性があるので、student の各層の重みが有限な時のみ更新する
                        student_finite = all(
                            torch.isfinite(p.data).all()
                            for p in self.model_g.spk_proj.parameters()
                        )
                        if student_finite:
                            for p_ema, p in zip(
                                self.spk_proj_teacher.parameters(),
                                self.model_g.spk_proj.parameters(),
                                strict=True,
                            ):
                                p_ema.mul_(0.996).add_(p.data, alpha=0.004)

                        # dino_center の汚染防御: teacher_emb mean が non-finite の
                        # 場合、center を更新しない (一度 NaN 化すると以降の
                        # dino_loss が常に 0 マスクされて DINO が完全停止する)
                        batch_center = teacher_emb.mean(dim=0)
                        if torch.isfinite(batch_center).all():
                            if not torch.isfinite(self.dino_center).all():
                                # Recovery: dino_center 自身が NaN 汚染された
                                # 場合、 EMA (NaN*0.996 + x*0.004 = NaN) では
                                # 永続的に回復しない。 clean な batch_center で
                                # 再シードする。
                                self.dino_center.copy_(batch_center.float())
                                _LOGGER.warning(
                                    "dino_center had non-finite values at "
                                    "step=%d; re-seeded from clean batch_center.",
                                    self.global_step,
                                )
                            else:
                                self.dino_center.mul_(0.996).add_(
                                    batch_center.float(), alpha=0.004
                                )
                            self.dino_center.clamp_(min=-10, max=10)
                        else:
                            _LOGGER.warning(
                                "dino_center update skipped at step=%d: "
                                "teacher_emb mean has non-finite values "
                                "(NaN=%d/%d). dino_center preserved.",
                                self.global_step,
                                int(torch.isnan(batch_center).sum().item()),
                                batch_center.numel(),
                            )

            # WavLM Discriminator loss (optional, computed every N steps)
            if self.model_d_wavlm is not None and (
                self.global_step % self.hparams.wavlm_every_n_steps == 0
            ):
                # T6: WavLM disc forward also honours _disc_autocast_ctx.
                with self._disc_autocast_ctx():
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
                if probe_losses is not None:
                    probe_losses["wavlm"] = loss_wavlm

            # MRD generator loss (optional, v9 — full-band spectral supervision)
            # v10b S-1a: JCU 有効時は無条件項 + 条件項を 1/2 ずつ (spk_cond は
            # noise 加算後の embedding。conditioning に使ったものと同一)
            if self.model_d_mrd is not None:
                loss_gen_mrd, loss_fm_mrd, loss_gen_mrd_cond = (
                    self._mrd_generator_losses(y, y_hat, speaker_embeddings)
                )
                loss_mrd = (loss_gen_mrd + loss_fm_mrd) * self.hparams.c_mrd
                loss_gen_all = loss_gen_all + loss_mrd
                self._log_with_batch_info("loss_gen_mrd", loss_gen_mrd, batch)
                self._log_with_batch_info("loss_fm_mrd", loss_fm_mrd, batch)
                if loss_gen_mrd_cond is not None:
                    self._log_with_batch_info(
                        "loss_gen_mrd_cond", loss_gen_mrd_cond, batch
                    )
                if probe_losses is not None:
                    probe_losses["mrd"] = loss_mrd

            # v10b S-1b: adversarial speaker classifier の G 側敵対項。
            # 生成音声が条件話者に分類されるよう CE 最小化する (frozen encoder
            # cosine ではなく共進化する分類器が相手なので静的に game できない)
            if self.model_c_spk is not None and self._adv_spk_generator_active(
                has_speaker_ids=batch.speaker_ids is not None
            ):
                ramp = self._adv_spk_ramp()
                loss_adv_spk = self._adv_spk_classifier_loss_g(
                    y_hat, batch.speaker_ids
                ) * (self.hparams.c_adv_spk * ramp)
                loss_gen_all = loss_gen_all + loss_adv_spk
                self._log_with_batch_info("loss_adv_spk", loss_adv_spk, batch)
                self._log_with_batch_info("adv_spk_ramp", ramp, batch)
                if probe_losses is not None:
                    probe_losses["adv_spk"] = loss_adv_spk

            self._log_with_batch_info("loss_gen_all", loss_gen_all, batch)
            self._log_with_batch_info("loss_mel", loss_mel, batch)
            self._log_with_batch_info("loss_kl", loss_kl, batch)
            self._log_with_batch_info("loss_dur", loss_dur, batch)
            self._log_with_batch_info("loss_fm", loss_fm, batch)
            self._log_with_batch_info("loss_gen", loss_gen, batch)
            self._log_with_batch_info("kl_weight", kl_weight, batch)

            return loss_gen_all

    def training_step_d(self, batch: Batch):
        # From training_step_g
        y = self._y
        y_hat = self._y_hat
        # Ensure detached tensors are contiguous
        y_hat_detached = y_hat.detach().contiguous()
        # T6: Discriminator forward runs under _disc_autocast_ctx (nullcontext by
        # default; bf16 or fp32 override when disc_precision != "inherit").
        with self._disc_autocast_ctx():
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
                # T6: WavLM disc forward also honours _disc_autocast_ctx.
                with self._disc_autocast_ctx():
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

            # MRD discriminator loss (optional, v9; v10b S-1a で JCU 条件項)
            if self.model_d_mrd is not None:
                loss_disc_mrd, loss_disc_mrd_cond = self._mrd_discriminator_loss(
                    y, y_hat_detached, getattr(self, "_spk_cond", None)
                )
                loss_disc_all = loss_disc_all + loss_disc_mrd * self.hparams.c_mrd
                self._log_with_batch_info("loss_disc_mrd", loss_disc_mrd, batch)
                if loss_disc_mrd_cond is not None:
                    self._log_with_batch_info(
                        "loss_disc_mrd_cond", loss_disc_mrd_cond, batch
                    )

            # v10b S-1b: 分類器 C 自身の更新 (実音声 = 真の話者 / 生成音声 =
            # 「生成」クラス)。**ramp に従わず step 0 から学習する** — C が
            # 未学習のまま G に敵対項を課すとゴミ勾配になるため。
            # fake 側は detach 済み波形なので G に勾配は戻らない。
            if self.model_c_spk is not None and self._adv_spk_classifier_active(
                has_speaker_ids=batch.speaker_ids is not None
            ):
                loss_c_spk, c_stats = self._adv_spk_classifier_loss_d(
                    y, y_hat_detached, batch.speaker_ids
                )
                loss_disc_all = loss_disc_all + loss_c_spk * self.hparams.c_adv_spk
                self._log_with_batch_info("loss_c_spk", loss_c_spk, batch)
                # Phase D 検証項目 ③ / 本走 R3 監視: fake に対する C の判別推移。
                # acc_fake_as_generated が 1.0 に貼り付いたら C の生成分布上の
                # 更新が仕事をしていない (= S-1b の前提が崩れている) 兆候
                for key, value in c_stats.items():
                    self._log_with_batch_info(f"c_spk_{key}", value, batch)

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
                            # Generate audio.
                            # non_blocking=True on H2D copies keeps the pipeline
                            # non-serializing when the source tensor is pageable
                            # (safe here: we do not read the destination until the
                            # infer call below implicitly syncs on the same stream).
                            text = test_utt.phoneme_ids.unsqueeze(0).to(
                                self.device, non_blocking=True
                            )
                            text_lengths = torch.LongTensor(
                                [len(test_utt.phoneme_ids)]
                            ).to(self.device, non_blocking=True)
                            scales = [0.4, 1.0, 0.5]

                            # Resolve speaker embedding for zero-shot
                            spk_emb = None
                            if (
                                self.hparams.get("use_zero_shot", True)
                                and self.hparams.num_speakers > 1
                            ):
                                if (
                                    hasattr(test_utt, "speaker_embedding")
                                    and test_utt.speaker_embedding is not None
                                ):
                                    spk_emb = test_utt.speaker_embedding.unsqueeze(
                                        0
                                    ).to(self.device, non_blocking=True)
                                else:
                                    spk_emb = torch.zeros(
                                        1,
                                        self.hparams.get("spk_embed_dim", 192),
                                        device=self.device,
                                    )

                            # language_id may be int or Tensor
                            # (Subset from random_split wraps them as LongTensor)
                            raw_lid = test_utt.language_id
                            if raw_lid is not None:
                                if isinstance(raw_lid, torch.Tensor):
                                    lid = (
                                        raw_lid.unsqueeze(0)
                                        if raw_lid.dim() == 0
                                        else raw_lid
                                    ).to(self.device, non_blocking=True)
                                else:
                                    lid = torch.LongTensor([raw_lid]).to(
                                        self.device, non_blocking=True
                                    )
                            else:
                                lid = None

                            noise_scale, length_scale, noise_scale_w = scales
                            test_audio, *_ = self.model_g.infer(
                                text,
                                text_lengths,
                                sid=None,
                                lid=lid,
                                noise_scale=noise_scale,
                                length_scale=length_scale,
                                noise_scale_w=noise_scale_w,
                                speaker_embeddings=spk_emb,
                            )
                            test_audio = test_audio.detach()
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
                                "zero-shot" if spk_emb is not None else "single"
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
                            del test_audio, text, text_lengths, spk_emb, lid
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
        from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR

        # Freeze Duration Predictor parameters if requested
        freeze_dp = getattr(self.hparams, "freeze_dp", False)
        if freeze_dp:
            for name, param in self.model_g.named_parameters():
                if name.startswith("dp."):
                    param.requires_grad = False
            _LOGGER.info("Froze Duration Predictor parameters (--freeze-dp)")

        # Decoder-only re-adaptation (v9): freeze everything except the
        # decoder. Used to re-adapt a checkpoint trained against the buggy
        # PQMF bank to the fixed bank (--reinit-pqmf) without disturbing the
        # text encoder / posterior / flow / DP / speaker projection — the
        # sub-band-loss target contamination only ever back-propagated
        # through dec.* (docs/design/zero-shot-noise-root-cause-pqmf.md).
        if getattr(self.hparams, "train_decoder_only", False):
            frozen = 0
            for name, param in self.model_g.named_parameters():
                if not name.startswith("dec."):
                    param.requires_grad = False
                    frozen += 1
            _LOGGER.info(
                "Decoder-only training: froze %d non-decoder generator params "
                "(--train-decoder-only)",
                frozen,
            )

        # Collect generator parameters (exclude frozen params)
        g_params = [p for p in self.model_g.parameters() if p.requires_grad]

        # Collect discriminator parameters (including WavLM / MRD / adversarial
        # speaker classifier if enabled). The classifier belongs to the D
        # optimizer: it is updated adversarially against the generator, and any
        # gradient it picks up during the G backward is cleared by the
        # ``opt_d.zero_grad()`` that precedes ``training_step_d``.
        d_params = list(self.model_d.parameters())
        if self.model_d_wavlm is not None:
            d_params = d_params + list(self.model_d_wavlm.parameters())
        if self.model_d_mrd is not None:
            d_params = d_params + list(self.model_d_mrd.parameters())
        if self.model_c_spk is not None:
            d_params = d_params + list(self.model_c_spk.parameters())

        optimizers = [
            torch.optim.AdamW(
                g_params,
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

        # --- LR Schedule ---
        max_epochs = None
        try:
            max_epochs = self.trainer.max_epochs
        except RuntimeError:
            pass
        if not max_epochs:
            max_epochs = self.hparams.get("max_epochs", 200)
        # Support both lr_warmup_epochs (CLI arg) and warmup_epochs (legacy hparam name)
        warmup_epochs = getattr(self.hparams, "lr_warmup_epochs", None)
        if warmup_epochs is None:
            warmup_epochs = getattr(self.hparams, "warmup_epochs", 5)
        eta_min = getattr(self.hparams, "lr_min", 1e-5)

        lr_scheduler_type = getattr(self.hparams, "lr_scheduler", "cosine")

        schedulers = []
        if lr_scheduler_type == "exponential":
            lr_decay = getattr(self.hparams, "lr_decay", 0.999875)
            for opt in optimizers:
                scheduler = torch.optim.lr_scheduler.ExponentialLR(opt, gamma=lr_decay)
                schedulers.append(scheduler)
            _LOGGER.info(
                "LR schedule: ExponentialLR (gamma=%.6f, base_lr=%.1e)",
                lr_decay,
                self.hparams.learning_rate,
            )
        else:
            # cosine (default)
            for opt in optimizers:
                if warmup_epochs > 0 and warmup_epochs < max_epochs:
                    warmup = LinearLR(opt, start_factor=0.01, total_iters=warmup_epochs)
                    cosine = CosineAnnealingLR(
                        opt, T_max=max_epochs - warmup_epochs, eta_min=eta_min
                    )
                    scheduler = SequentialLR(
                        opt,
                        schedulers=[warmup, cosine],
                        milestones=[warmup_epochs],
                    )
                else:
                    scheduler = CosineAnnealingLR(
                        opt, T_max=max_epochs, eta_min=eta_min
                    )
                schedulers.append(scheduler)
            _LOGGER.info(
                "LR schedule: %s warmup epochs + cosine annealing over %d total epochs "
                "(eta_min=%.1e, base_lr=%.1e)",
                warmup_epochs if warmup_epochs > 0 else "no",
                max_epochs,
                eta_min,
                self.hparams.learning_rate,
            )

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
        parser.add_argument(
            "--c-spk",
            type=float,
            default=1.0,
            help="Weight for mel speaker consistency loss (default: 1.0). "
            "Active only for multi-speaker models. Set to 0 to disable.",
        )
        return parent_parser
