"""MB-iSTFT-VITS2 decoder components: PQMF and MBiSTFTGenerator.

Implements the Multi-Band inverse STFT decoder from:
  Kawamura et al., "Lightweight and High-Fidelity End-to-End Text-to-Speech
  with Multi-Band Generation and Inverse Short-Time Fourier Transform",
  ICASSP 2023 (arXiv:2210.15975)
"""

import math

import numpy as np
import torch
from torch import nn
from torch.nn import Conv1d, ConvTranspose1d, functional as F
from torch.nn.utils import remove_weight_norm, weight_norm

from .commons import init_weights
from .modules import ResBlock1, ResBlock2
from .stft_onnx import OnnxISTFT


LRELU_SLOPE = 0.1


# Co-designed PQMF prototype parameters per filter length (v10b H-2b).
#
# ``taps`` alone is NOT a free knob: the Kaiser-windowed-sinc prototype must be
# re-tuned whenever the filter length changes, because a longer filter has a
# narrower transition band and the near-perfect-reconstruction property depends
# on adjacent bands overlapping by exactly the right amount. Keeping the
# taps=62 values while bumping to 126 *improves* the stopband (-99 -> -110 dB)
# yet collapses round-trip reconstruction (64.0 -> 16.1 dB) and breaks power
# complementarity (sum|G_k|^2 ripple 0.01 -> 1.80 dB) — i.e. the naive bump is
# exactly the kind of change a stopband-only acceptance criterion would wave
# through. See tests/test_pqmf_taps_trainable.py for the measured evidence and
# docs/design/zero-shot-noise-root-cause-pqmf.md §4 for why we no longer accept
# single-metric criteria here.
#
#   taps  (cutoff_ratio, beta)   round-trip   stopband   ripple
#     62  (0.1420, 9.00)          64.05 dB    -99.2 dB   0.010 dB   canonical
#    126  (0.1336, 9.50)          65.17 dB   -107.1 dB   0.015 dB   H-2b
PQMF_DESIGN: dict[int, tuple[float, float]] = {
    62: (0.142, 9.0),
    126: (0.1336, 9.5),
}


class PQMF(nn.Module):
    """Pseudo Quadrature Mirror Filterbank (canonical near-perfect design).

    Decomposes a fullband signal into *subbands* equal-width sub-band signals
    (analysis) and reconstructs the fullband signal from sub-bands (synthesis).

    Coefficients follow the canonical cosine-modulated design (Nguyen 1994,
    "Near-perfect-reconstruction pseudo-QMF banks"; reference implementation:
    kan-bayashi/ParallelWaveGAN ``pqmf.py``). Round-trip reconstruction SNR is
    ~60 dB with the default Kaiser prototype — alias components of adjacent
    bands cancel in synthesis thanks to the ``±(-1)^k·π/4`` modulation phase.

    HISTORY (2026-08, docs/design/zero-shot-noise-root-cause-pqmf.md): the
    original implementation omitted the phase term, centred the modulation at
    ``subbands/2`` instead of ``taps/2``, and decimated band *k* at offset *k*
    (grouped-eye updown filter). Alias cancellation was broken (round-trip
    SNR 7-8 dB; band-edge tones down to -1.6 dB) and the resulting
    sub-band-loss target contamination is the root cause of the audible
    zero-shot "gabi-gabi" noise. All buffer SHAPES are unchanged, so legacy
    checkpoints restore their original (buggy) coefficients via state_dict
    and keep their trained behaviour; only newly-constructed banks get the
    canonical coefficients.

    All filter tensors are registered as buffers so that they follow the
    module's device automatically (no ``.cuda()`` hard-coding).
    """

    def __init__(
        self,
        subbands: int = 4,
        taps: int = 62,
        cutoff_ratio: float | None = None,
        beta: float | None = None,
        trainable_synthesis: bool = False,
    ):
        super().__init__()
        if cutoff_ratio is None or beta is None:
            if taps not in PQMF_DESIGN:
                raise ValueError(
                    f"no co-designed prototype for taps={taps}; supported: "
                    f"{sorted(PQMF_DESIGN)}. Pass cutoff_ratio and beta "
                    f"explicitly to explore a new length, and verify round-trip "
                    f"SNR >= 55 dB plus power complementarity before using it "
                    f"for training (see tests/test_pqmf_taps_trainable.py)."
                )
            default_cutoff, default_beta = PQMF_DESIGN[taps]
            cutoff_ratio = default_cutoff if cutoff_ratio is None else cutoff_ratio
            beta = default_beta if beta is None else beta
        self.subbands = subbands
        self.taps = taps
        self.cutoff_ratio = cutoff_ratio
        self.beta = beta
        self.trainable_synthesis = trainable_synthesis

        # --- Prototype lowpass filter: Kaiser-windowed sinc ---
        filter_length = taps + 1  # 63
        omega_c = np.pi * cutoff_ratio
        t = np.arange(-(taps // 2), taps // 2 + 1, dtype=np.float64)

        # sinc(omega_c * t / pi) * omega_c / pi  (normalised cutoff)
        with np.errstate(divide="ignore", invalid="ignore"):
            sinc = np.where(t == 0, omega_c / np.pi, np.sin(omega_c * t) / (np.pi * t))
        window = np.kaiser(filter_length, beta)
        prototype = sinc * window

        # --- Cosine-modulated analysis / synthesis filter banks ---
        # h_k[n] = 2h[n]·cos((2k+1)·π/(2M)·(n − taps/2) + (−1)^k·π/4)
        # g_k[n] = 2h[n]·cos((2k+1)·π/(2M)·(n − taps/2) − (−1)^k·π/4)
        # The ±(−1)^k·π/4 phase pair is what makes adjacent-band aliases
        # cancel on reconstruction — do NOT remove it.
        n = np.arange(filter_length, dtype=np.float64)
        analysis_filter = np.zeros((subbands, 1, filter_length), dtype=np.float64)
        synthesis_filter = np.zeros((subbands, 1, filter_length), dtype=np.float64)
        for k in range(subbands):
            arg = (2 * k + 1) * np.pi / (2 * subbands) * (n - taps / 2)
            phase = (-1) ** k * np.pi / 4
            analysis_filter[k, 0] = 2.0 * prototype * np.cos(arg + phase)
            synthesis_filter[k, 0] = 2.0 * prototype * np.cos(arg - phase)

        # Register as buffers (float32). The analysis bank is ALWAYS fixed: it
        # produces the sub-band training target from ground-truth audio, so
        # making it learnable would let the model move the target it is scored
        # against. Only the synthesis bank may be trainable (v10b H-2b,
        # MS-iSTFT-VITS style) — and because the coefficients are identical to
        # the canonical ones at construction, ``state_dict`` keys and shapes are
        # unchanged either way, so checkpoints interoperate in both directions.
        self.register_buffer(
            "analysis_filter", torch.from_numpy(analysis_filter).float()
        )
        synthesis_tensor = torch.from_numpy(synthesis_filter).float()
        if trainable_synthesis:
            self.synthesis_filter = nn.Parameter(synthesis_tensor)
        else:
            self.register_buffer("synthesis_filter", synthesis_tensor)

        # Up/down-sampling filter: every band decimates/interpolates at the
        # SAME polyphase offset (j=0). The previous grouped-eye construction
        # (band k sampled at offset k) skewed the bands against each other
        # and was part of the alias-cancellation breakage.
        updown = np.zeros((subbands, 1, subbands), dtype=np.float32)
        updown[:, 0, 0] = 1.0
        self.register_buffer("updown_filter", torch.from_numpy(updown))

        # Padding
        self.pad = nn.ConstantPad1d(taps // 2, 0.0)

    def analysis(self, x: torch.Tensor) -> torch.Tensor:
        """Decompose fullband signal into sub-band signals.

        Args:
            x: Fullband waveform ``[B, 1, T]``.

        Returns:
            Sub-band signals ``[B, subbands, T // subbands]``.
        """
        x = self.pad(x)  # [B, 1, T + taps]
        x = F.conv1d(x, self.analysis_filter)  # [B, subbands, T]
        # Polyphase downsampling: stride-decimate each subband independently
        # updown_filter: [subbands, 1, subbands] -- groups=subbands
        # Input x: [B, subbands, T] -> output: [B, subbands, T // subbands]
        x = F.conv1d(
            x,
            self.updown_filter,
            stride=self.subbands,
            groups=self.subbands,
        )
        return x

    def synthesis(self, x: torch.Tensor) -> torch.Tensor:
        """Reconstruct fullband signal from sub-band signals.

        Args:
            x: Sub-band signals ``[B, subbands, T_sub]``.

        Returns:
            Fullband waveform ``[B, 1, T]`` where ``T = T_sub * subbands``.
        """
        # Upsample: insert zeros between samples
        # updown_filter: [subbands, 1, subbands] -- groups=subbands conv_transpose1d
        # Input x: [B, subbands, T_sub] -> output: [B, subbands, T_sub * subbands]
        x = F.conv_transpose1d(
            x,
            self.updown_filter * self.subbands,
            stride=self.subbands,
            groups=self.subbands,
        )
        x = self.pad(x)  # [B, subbands, T + taps]
        # Synthesis filter: (1, subbands, filter_length)
        x = F.conv1d(x, self.synthesis_filter.permute(1, 0, 2))  # [B, 1, T]
        return x


class NearestResizeUpsample(nn.Module):
    """Nearest-neighbour resize followed by a stride-1 Conv1d (v10b H-1).

    Drop-in replacement for ``ConvTranspose1d(C_in, C_out, k, stride=u)`` that
    removes the transposed-convolution *checkerboard* / tonal artifact: with a
    strided transposed conv each output phase ``p in [0, u)`` is produced by a
    different weight subset, so any non-zero activation mean is modulated with
    the stage grid period and shows up as a stationary comb in the spectrum
    (Pons et al., arXiv:2010.14356 — present from initialisation, surviving
    training). Resizing first and convolving with stride 1 makes every output
    sample share one filter, so the modulation has no mechanism to appear.

    Motivation for piper-plus specifically: the observed comb series
    (SR/64 = 344.5 Hz strongest) coincides exactly with the ``ups[0]`` output
    grid — see docs/design/zero-shot-v10b-quality-plan.md §1.3 (suspect #1).

    MACs (docstring requirement of plan §3.1 H-1【算術】/ §4.3 cost gate)::

        ConvTranspose1d(C_in, C_out, k, stride=u)   MACs = L_in · k · C_in · C_out
        resize(xu) + Conv1d(C_in, C_out, k')        MACs = u · L_in · k' · C_in · C_out

    Keeping the same kernel would therefore cost ``u`` times more MACs per
    stage (4x for our ``upsample_rates=(4, 4)``), which would put the CPU
    real-time budget of MB-iSTFT at risk. We shrink the kernel proportionally,
    ``k' = k // u`` (16 // 4 = 4), making the replacement **MACs-neutral**.

    The Conv1d is initialised as an interpolation (lowpass) filter: the weight
    is the outer product of a random channel-mixing matrix and a Hann-windowed
    sinc of cutoff ``pi/u``, plus a small perturbation that breaks the exact
    rank-1 degeneracy along the tap axis. Combined with the nearest resize
    (itself a length-``u`` box filter) the stage starts life as a proper
    ``xu`` interpolator with strongly suppressed images.

    Both ops are ONNX standard operators (Resize / Pad / Conv), so the export
    contract is unchanged.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        upsample: int,
        perturb_ratio: float = 0.1,
    ):
        super().__init__()
        self.upsample = upsample
        # k' = k / u keeps MACs identical to the transposed conv it replaces.
        k = max(1, kernel_size // upsample)
        self.kernel_size = k
        # Even kernels cannot be centred symmetrically by ``Conv1d(padding=)``,
        # so pad explicitly to keep the output length exactly L_in * u.
        self.pad = nn.ConstantPad1d((k // 2, k - 1 - k // 2), 0.0)

        conv = Conv1d(in_channels, out_channels, k)
        with torch.no_grad():
            h = torch.from_numpy(self._interpolation_kernel(k, upsample)).float()
            # Match the output variance of PyTorch's default Conv init
            # (kaiming_uniform with a=sqrt(5) => Var(out) = Var(x)/3):
            #   Var(out) = C_in * Var(A) * ||h||^2 * Var(x)
            var_a = 1.0 / (3.0 * in_channels * float((h**2).sum()))
            a = torch.randn(out_channels, in_channels, 1) * math.sqrt(var_a)
            weight = a * h.reshape(1, 1, k)
            weight = weight + torch.randn_like(weight) * (perturb_ratio * weight.std())
            conv.weight.copy_(weight)
            conv.bias.zero_()
        self.conv = weight_norm(conv)

    @staticmethod
    def _interpolation_kernel(k: int, upsample: int) -> np.ndarray:
        """Hann-windowed sinc lowpass of cutoff ``pi/upsample``, unity DC gain."""
        n = np.arange(k, dtype=np.float64) - (k - 1) / 2.0
        window = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(k) + 0.5) / k)
        h = np.sinc(n / upsample) * window
        return h / h.sum()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, scale_factor=float(self.upsample), mode="nearest")
        return self.conv(self.pad(x))


class HarmonicPhaseTemplate(nn.Module):
    """frame 格子 F0 → head 格子の調波位相テンプレート (v10b S-2c)。

    ``f0 [B, 1, T_frames]`` (Hz、無声 = 0) を受け取り、iSTFT head が消費する
    格子 (``SR / (frame_hop / upsample)`` = 1378.125 Hz) で

        Φ_t = Σ_{i≤t} f0_i / frame_rate            (cycles)
        template = [cos(2πmΦ)]_{m=1..M} ⊕ [sin(2πmΦ)]_{m=1..M} ⊕ log f0 ⊕ V/UV

    を返す (``[B, 2M+2, T_frames * upsample]``)。学習パラメータは持たない。

    **なぜ head 格子なのか** (docs/design/zero-shot-v10b-s2-f0-design.md §1):
    この decoder で「周期性」が実際に存在するのは head が出す per-frame 位相の
    frame 間整合だけで、subband iSTFT の bin 幅は 344.5Hz と F0 の倍音間隔を
    分解できない。従って位相参照を置いて意味がある格子は head 格子しかなく、
    frame 格子 (86Hz) への注入は「値」情報にしかならない (それは S-2a の担当)。

    実装上の要点 2 つ:

    * **Chebyshev 漸化式**: ``cos(mθ) = 2cos(θ)cos((m−1)θ) − cos((m−2)θ)``
      で m ≥ 2 を Mul/Sub だけで展開する。超越関数の評価が head 格子で
      2 個/サンプル (M=8 なら 16 → 2) に減る。精度は M=8 で 2.9e-06 と
      直接評価と実用上同一 (設計 doc §3.1【実測】)。
    * **float64 位相累積**: fp32 の ``cumsum`` は torch と ORT で加算順序が
      異なり、誤差が長さとともに増幅する (T=2000 で相対 1.7e-01)。位相の
      累積のみ float64 にすると長さ非依存で 3e-05 に収まり、レイテンシ
      コストは測定誤差以下だった (設計 doc §3.4【実測】)。ONNX parity を
      長尺で書けるようにするための必須条件。

    学習時は一様乱数の初期位相 ``U(0, 1)`` cycles をサンプルごとに加算する
    (§4.4)。学習は ``segment_size // hop`` フレームのスライスで行うため、
    これがないと「slice 先頭の位相は常に 0」を模型が学習しうる。``eval()``
    では常に 0 — ONNX graph に乱数 op を出さないための構造的保証も兼ねる。
    """

    def __init__(
        self,
        n_harmonics: int = 8,
        upsample: int = 16,
        sample_rate: int = 22050,
        frame_hop: int = 256,
        f0_log_scale: float = 6.0,
    ):
        super().__init__()
        if n_harmonics < 1:
            raise ValueError(f"n_harmonics must be >= 1, got {n_harmonics}")
        self.n_harmonics = n_harmonics
        self.upsample = upsample
        # head 格子 = frame 格子 (sample_rate / frame_hop) の upsample 倍。
        self.frame_rate = sample_rate * upsample / frame_hop
        self.f0_log_scale = f0_log_scale

    @property
    def out_channels(self) -> int:
        return 2 * self.n_harmonics + 2

    def forward(self, f0: torch.Tensor) -> torch.Tensor:
        """``f0 [B, 1, T]`` (Hz、無声 0) → ``[B, 2M+2, T * upsample]``."""
        uv = (f0 > 1.0).to(f0.dtype)
        f0_up = F.interpolate(
            f0, scale_factor=float(self.upsample), mode="linear", align_corners=False
        )
        uv_up = F.interpolate(uv, scale_factor=float(self.upsample), mode="nearest")

        # --- 位相累積 (float64) ---
        # 除算も float64 で行う: fp32 で割ってから cast すると 1 frame あたりの
        # 位相ステップが fp32 に量子化され、その丸め **バイアス** が長さに比例して
        # 蓄積する (T=1024 で 5e-06 cycles → 8 次調波の振幅誤差 2.4e-04、
        # T=13,760 で 3.8e-03)。cast 位置を 1 つ手前に置くだけで長さ非依存になる。
        phase = torch.cumsum(f0_up.double() / self.frame_rate, dim=-1)
        if self.training:
            # サンプルごとに独立な初期位相 (位相オフセット不変性の獲得)
            phase = phase + torch.rand(
                phase.size(0), 1, 1, dtype=phase.dtype, device=phase.device
            )
        # 倍音を掛ける **前** に小数部を取る = 位相精度の保護
        frac = phase - torch.floor(phase)
        # **必ず float32 で三角関数と漸化式を回す** (入力 dtype に従わない)。
        # autocast(bf16) 下では f0 が bf16 で来るが、bf16 の cos/sin は絶対誤差
        # ~4e-3 で、Chebyshev 漸化式はその誤差を ~m² 倍に増幅する — M=8 では
        # 0.25 に達し、高次調波のテンプレートが壊れる。テンプレートは head 格子で
        # 超越関数 2 個 + Mul/Sub だけなので、fp32 固定のコストは無視できる。
        arg = (2.0 * math.pi * frac).float()

        c1 = torch.cos(arg)  # 超越関数の評価はこの 2 個だけ
        s1 = torch.sin(arg)
        two_c1 = 2.0 * c1
        cos_terms = [torch.ones_like(c1), c1]
        sin_terms = [torch.zeros_like(s1), s1]
        for _ in range(2, self.n_harmonics + 1):
            cos_terms.append(two_c1 * cos_terms[-1] - cos_terms[-2])
            sin_terms.append(two_c1 * sin_terms[-1] - sin_terms[-2])

        harmonics = torch.cat(cos_terms[1:] + sin_terms[1:], dim=1) * uv_up.float()
        log_f0 = torch.log(f0_up.float().clamp(min=1.0)) / self.f0_log_scale
        return torch.cat([harmonics, log_f0, uv_up.float()], dim=1)


class CarrierHead(nn.Module):
    """v11 A′: 解析重み付き 2-band 担体描画 (harmonic branch) の oscillator bank。

    docs/design/zero-shot-v11-harmonic-head-design.md §2.2 / §3。倍音 m·F0 を
    「PQMF 解析フィルタの複素周波数応答 conj(H_k(m·F0)) を固定重みとして
    band0 と band1 の両 subband に描画する」ことで、voiced 帯域 (≤3kHz) の
    調波エネルギーを出せる経路をこの head に限定する (A3 がびがびの構造根治)。

    構造保証の 3 本柱 (いずれも学習で外せない固定要素):

    1. **ゲイン格子 = frame 格子 (86.1Hz) + 固定 Hann k=5 depthwise 平滑**。
       ゲイン変調帯域 W が調波中間点 (F0/2) より狭ければ、敵対的 (i.i.d.) な
       ゲインでも comb 構造が壊れない — 実測 comb-HNR@1-3kHz は F0=220Hz で
       42.4dB、F0=90Hz でも 36.8dB (設計 doc §5.1)。head 格子ゲインにすると
       0.5dB まで崩壊するため、格子選択そのものが保証の本体。
    2. **解析重み conj(H_k)**: 理想 fullband 倍音を ``PQMF.analysis`` に通した
       結果の解析形。synthesis の隣接 band alias 相殺 (±(−1)^k·π/4 modulation
       位相対) が構造的に働き、band 端 (2756.25Hz) の鏡像 spur が −98dB 以下に
       消える (素朴 band0 単独描画は −1.4dB@2700Hz、設計 doc §5.2)。
       **符号に注意**: ``F.conv1d`` は相関なので重みは conj(H_k)。H_k のまま
       使うと alias が逆に強め合い +16dB になる (E1c で踏んだ罠 —
       ``test_carrier_head.py`` の alias regression が fixture として固定)。
    3. **hard cap f_max = 3000Hz** (mask=0、構造的)。2700-3000Hz の線形 taper
       は gameable な prior にすぎない (設計 doc §4.1 #4) — 構造境界は mask=0。

    実装形は **MatMul 融合** (設計 doc §3.6 の指定): ゲイン適用を per-frame
    batched MatMul ``[B,T,4,M] @ [B,T,M,64]`` にし、線形補間をランプ重みで
    表現する。素朴な elementwise 実装 (4M-ch Resize + mul-reduce) は ORT CPU
    で +61〜72% と gate を大幅超過する (設計 doc §5.5) ため禁止。補間の定義
    (セグメント端点補間 vs align_corners=False) だけが素朴形と異なるが、
    ゲイン帯域制限 = 構造保証は同一。

    位相は ``HarmonicPhaseTemplate`` と同じ float64 累積 (ONNX parity の長さ
    非依存性) + 学習時のみ一様乱数の初期位相 (slice 先頭位相の過学習防止、
    ``eval()`` では 0 = graph に位相系乱数 op を出さない)。三角関数と MatMul は
    fp32 固定 (autocast(bf16) 下でも) — bf16 cos/sin の絶対誤差 ~4e-3 は
    位相参照として大きすぎる (S-2c と同じ理由)。

    N_TABLE = 4097 (設計 doc §3 の 513 からの deviation):
    設計 doc の alias 実測 (−98dB 以下、E1c) はテーブルではなく **H_k の厳密値**
    で測っていた。513 点の線形補間を通すと補間誤差が band0/band1 の重み対を
    崩し、alias 相殺は −70〜−82dB で床を打つ【実測 (本実装時)。誤差は点数の
    2 乗で減る: 513→−70dB / 1025→−80 / 2049→−92 / 4097→−96dB (worst over
    2400-2900Hz)】。事前登録の CI gate (§8 R4: spur ≤ −90dB) が支配するため
    テーブルを 4097 点に採る — メモリ 64KB、ONNX Gather のコストは点数に非依存。
    """

    N_TABLE = 4097

    def __init__(
        self,
        in_channels: int,
        pqmf: PQMF,
        n_harmonics: int = 32,
        f_max: float = 3000.0,
        f_taper: float = 300.0,
        gain_smooth_k: int = 5,
        sample_rate: int = 22050,
        frame_hop: int = 256,
        gain_init_std: float = 1e-2,
    ):
        super().__init__()
        if n_harmonics < 1:
            raise ValueError(f"n_harmonics must be >= 1, got {n_harmonics}")
        self.n_harmonics = n_harmonics
        self.f_max = f_max
        self.f_taper = f_taper
        self.gain_smooth_k = gain_smooth_k
        # subband レート (SR/4 = 5512.5Hz) と frame → subband サンプル比 (64)
        self.sub_rate = sample_rate / pqmf.subbands
        self.sub_up = frame_hop // pqmf.subbands

        M = n_harmonics
        # 担体の唯一の学習自由度: frame 格子の複素ゲイン (a_m, b_m)。
        # small-Gaussian init (zero-init ではない): 学習初期から comb が微弱に
        # 存在し、D が「初期 G はノイズ声」を過学習するのを防ぐ (設計 doc §3.2 /
        # §8 R6)。post の ch 数が変わる時点で bit 互換退避は成立しないので、
        # S-2c 流の zero-init に意味がない。
        self.gain_net = Conv1d(in_channels, 2 * M, 3, padding=1)
        nn.init.normal_(self.gain_net.weight, 0.0, gain_init_std)
        nn.init.zeros_(self.gain_net.bias)

        # 固定 Hann 平滑 (depthwise、学習しない = モデルは Nyquist 近傍の
        # ゲイン変調を復元できない。これが低 F0 話者の構造保証)。
        if gain_smooth_k > 1:
            w = torch.hann_window(gain_smooth_k + 2, periodic=False)[1:-1]
            w = (w / w.sum()).reshape(1, 1, -1).repeat(2 * M, 1, 1)
            self.register_buffer("smooth_w", w)

        self.register_buffer(
            "m_idx", torch.arange(1, M + 1, dtype=torch.float32).reshape(1, M, 1)
        )

        # H_k(f) lookup テーブル (f = 0..sub_rate、513 点線形補間 — ONNX Gather)。
        # conj は forward 側の結合式で処理する (テーブルは H_k そのもの)。
        taps_len = pqmf.analysis_filter.size(-1)
        tau = np.arange(taps_len)
        fs = np.linspace(0.0, self.sub_rate, self.N_TABLE)
        tables = []
        for k in (0, 1):
            hk = pqmf.analysis_filter[k, 0].detach().cpu().numpy().astype(np.float64)
            Hk = (
                hk[None, :] * np.exp(-2j * np.pi * fs[:, None] * tau / sample_rate)
            ).sum(1)
            tables += [Hk.real, Hk.imag]
        self.register_buffer(
            "h_table", torch.from_numpy(np.stack(tables)).float()
        )  # [4, N_TABLE] = (ReH0, ImH0, ReH1, ImH1)

    def forward(
        self, x_frame: torch.Tensor, f0: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """``x_frame [B, C, T]`` (frame 格子 trunk、FiLM 済) + ``f0 [B, 1, T]``
        → ``(s0, s1)`` 各 ``[B, 1, T * sub_up]`` (SR/4 の subband 担体波形)。
        """
        return self.synthesize_from_gains(self.gain_net(x_frame), f0)

    def synthesize_from_gains(
        self, raw_gains: torch.Tensor, f0: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """ゲイン注入点を公開した合成本体 (敵対的ゲインの構造テスト用)。

        ``raw_gains [B, 2M, T]`` は ``gain_net`` 出力と同じ意味 (前半 M ch が
        a_m、後半が b_m)。ここから先 (平滑 → mask → H lookup → oscillator) は
        全て固定演算で、モデルが触れる自由度はこの引数だけ — つまり本 method に
        i.i.d. ランダムゲインを入れた時の comb-HNR が構造保証の実測値になる。
        """
        M = self.n_harmonics
        b = f0.size(0)
        gains = raw_gains.float()
        if self.gain_smooth_k > 1:
            p = self.gain_smooth_k // 2
            gains = F.conv1d(
                F.pad(gains, (p, p), mode="replicate"),
                self.smooth_w,
                groups=2 * M,
            )

        f0 = f0.float()
        uv = (f0 > 1.0).float()
        # 担体は hard VUV gate (f0=0 で消灯) + f_max hard cap (taper は prior)
        mask = ((self.f_max - self.m_idx * f0) / self.f_taper).clamp(0.0, 1.0) * uv
        ga = gains[:, :M] * mask
        gb = gains[:, M:] * mask

        # H_k(m·f0) lookup (frame 格子、線形補間)。conj(H_k) 重みなので
        #   s_k = Σ_m (a·ReH_k − b·ImH_k)·cos(2πmΦ) + (a·ImH_k + b·ReH_k)·sin(2πmΦ)
        fm = (self.m_idx * f0).clamp(max=self.sub_rate)
        pos = fm * ((self.N_TABLE - 1) / self.sub_rate)
        i0 = pos.floor().clamp(max=self.N_TABLE - 2)
        w1 = (pos - i0).unsqueeze(0)  # [1,B,M,T]
        idx = i0.long().reshape(-1)
        # 動的 T のため reshape は -1 (trace 時に shape を焼き込まない)
        tab0 = self.h_table[:, idx].reshape(4, b, M, -1)
        tab1 = self.h_table[:, idx + 1].reshape(4, b, M, -1)
        re0, im0, re1, im1 = tab0 + (tab1 - tab0) * w1  # 各 [B,M,T]
        a0 = ga * re0 - gb * im0
        b0 = ga * im0 + gb * re0
        a1 = ga * re1 - gb * im1
        b1 = ga * im1 + gb * re1

        # --- 位相累積 (float64、S-2c と同じ理由: torch↔ORT parity の長さ非依存) ---
        f0_up = F.interpolate(
            f0, scale_factor=float(self.sub_up), mode="linear", align_corners=False
        )
        phase = torch.cumsum(f0_up.double() / self.sub_rate, dim=-1)
        if self.training:
            # サンプルごとに独立な初期位相 (slice 先頭位相 0 の過学習防止)。
            # eval() では常に 0 — ONNX graph に位相系乱数 op を出さない。
            phase = phase + torch.rand(b, 1, 1, dtype=phase.dtype, device=phase.device)
        frac = (phase - torch.floor(phase)).float()

        # --- oscillator + ゲイン適用 (MatMul 融合形、fp32 固定) ---
        with torch.autocast(device_type=f0.device.type, enabled=False):
            mph = self.m_idx * frac  # [B,M,N]
            arg = 2.0 * math.pi * (mph - torch.floor(mph))
            cos4 = torch.cos(arg).reshape(b, M, -1, self.sub_up).permute(0, 2, 1, 3)
            sin4 = torch.sin(arg).reshape(b, M, -1, self.sub_up).permute(0, 2, 1, 3)
            # ゲイン行列 [B,T,4,M]: (band0, band1) × (cur, next) — 線形補間を
            # ランプ重みで表現し、4M-ch の Resize を作らない (E5 の教訓)
            ga4 = torch.stack([a0, a1], dim=1)  # [B,2,M,T]
            gb4 = torch.stack([b0, b1], dim=1)
            ga4 = torch.cat(
                [ga4, torch.cat([ga4[..., 1:], ga4[..., -1:]], dim=-1)], dim=1
            )
            gb4 = torch.cat(
                [gb4, torch.cat([gb4[..., 1:], gb4[..., -1:]], dim=-1)], dim=1
            )
            out = torch.matmul(ga4.permute(0, 3, 1, 2), cos4) + torch.matmul(
                gb4.permute(0, 3, 1, 2), sin4
            )  # [B,T,4,sub_up]
            ramp = (
                torch.arange(self.sub_up, dtype=out.dtype, device=out.device) + 0.5
            ) / self.sub_up
            s = out[:, :, 0:2, :] * (1.0 - ramp) + out[:, :, 2:4, :] * ramp
            s = s.permute(0, 2, 1, 3).reshape(b, 2, -1)  # [B,2,T*sub_up]
        return s[:, 0:1], s[:, 1:2]


def carrier_source_regularization(
    e_h: torch.Tensor,
    e_n: torch.Tensor,
    f0: torch.Tensor,
    tau: float = 0.0,
    eps: float = 1e-8,
) -> torch.Tensor:
    """uSFGAN 型 source 正則化の hinge 版 L_src (設計 doc §4.3、default off)。

    ``L_src = mean_{voiced frames}( ReLU( log E_n − log E_h − τ ) )``

    A′ では source (担体) が解析形なので uSFGAN 本来の正則化は構造が代替済み。
    残る唯一のレベル系リスク「推論時 σ 氾濫」(§4.1 #7) に対する事前登録の
    緩和策で、**Phase D の監視指標 #6 が発火した場合のみ arm する** (CLI
    ``--c-src-reg``、default 0.0 = この項は学習に入らない)。

    - hinge + 緩い τ (GT の band0 noise/harmonic 比 p95 から Phase C で校正)
      なので正常な breathiness には勾配ゼロ、病的な氾濫のみ罰する
    - 参照するのは枝エネルギーと GT 由来定数のみ — 評価器 (frozen encoder /
      契約統計量) を消費しないため zs-eval-contract §2 に非抵触

    Args:
        e_h: 担体枝の frame エネルギー ``[B, T]``
             (``MBiSTFTGenerator.last_carrier_energies[0]``)
        e_n: noise 枝 (band0) の frame エネルギー ``[B, T]``
        f0: decoder に渡した frame 格子 F0 ``[B, 1, T]`` (voiced 判定に使用)
        tau: 許容上限 (log 比)。余裕をもった上限として校正する
        eps: log の数値安定化
    """
    voiced = (f0.squeeze(1) > 1.0).float()
    hinge = F.relu(torch.log(e_n + eps) - torch.log(e_h + eps) - tau)
    denom = voiced.sum().clamp(min=1.0)
    return (hinge * voiced).sum() / denom


class AdaIN1d(nn.Module):
    """v11 P3: resblock 単位の zero-init 残差 AdaIN (StyleTTS 2 系譜)。

    conditioning 設計 doc §5.1 (a-2) / §10.5。StyleTTS 2 のテンプレートは
    ``(1+γ)·IN(x)+β`` だが、そのままでは γ̂=0 でも ``IN(x) ≠ x`` となり
    「zero-init = off と bit 一致」の退避保証 (v11 の全 opt-in flag に共通の
    契約) を満たせない。そこで AdaLN-Zero (DiT) と同じ残差ゲート形に置く:

        y = x + γ̂(g) ⊙ IN(x) + β(g)

    - ``IN`` は affine なし InstanceNorm1d (発話内の per-channel 統計を除去) —
      話者アフィンが source 統計に汚染されず支配できる、という AdaIN の機構は
      維持される (変調枝は正規化座標で書かれる)。
    - ``γ̂ = β = 0`` (zero-init) で恒等 = flag off と bit 一致。
    - γ̂/β は ``g [B, gin_channels, 1]`` から発話あたり 1 回の 1x1 Conv で
      計算して時間軸へ broadcast — 時間格子に同期した変調機構を持たないため
      コム (がびがび) を構造的に作れない (帯域 gate は
      tests/test_adain_decoder.py が pin)。
    """

    def __init__(self, gin_channels: int, channels: int):
        super().__init__()
        self.channels = channels
        self.norm = nn.InstanceNorm1d(channels, affine=False)
        self.fc = Conv1d(gin_channels, channels * 2, 1)
        nn.init.zeros_(self.fc.weight)
        nn.init.zeros_(self.fc.bias)

    def forward(self, x: torch.Tensor, g: torch.Tensor) -> torch.Tensor:
        gamma, beta = self.fc(g).split(self.channels, dim=1)
        return x + gamma * self.norm(x) + beta


class MBiSTFTGenerator(nn.Module):
    """Multi-Band inverse STFT Generator.

    The sole VITS decoder. Generates fullband audio from latents via two
    upsample stages followed by sub-band iSTFT and PQMF synthesis. Total
    upsample factor is
    ``upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x``.

    The upsample stages are ``ConvTranspose1d`` by default; ``upsample_mode
    ="resize"`` (v10b H-1) swaps them for :class:`NearestResizeUpsample` to
    remove the transposed-conv tonal comb.
    """

    def __init__(
        self,
        initial_channel: int,
        resblock: str | None,
        resblock_kernel_sizes: tuple[int, ...],
        resblock_dilation_sizes: tuple[tuple[int, ...], ...],
        upsample_rates: tuple[int, ...] = (4, 4),
        upsample_initial_channel: int = 256,
        upsample_kernel_sizes: tuple[int, ...] = (16, 16),
        gin_channels: int = 0,
        n_fft: int = 16,
        hop_length: int = 4,
        subbands: int = 4,
        pqmf: "PQMF | None" = None,
        # T1 拡張: MBiSTFTGenerator にも channels_last plumbing を通す (opt-in、 default OFF)。
        # 現状の Generator は Conv1d/ConvTranspose1d のみで構成されるため、
        # ``self.to(memory_format=torch.channels_last)`` は 3D weight に対して
        # silent no-op (PyTorch の ``Module.to()`` は t.dim() in (4, 5) の
        # tensor のみ NHWC 化する)。 従って本 flag は今すぐの perf 変化を
        # 意図せず、 (a) Discriminator と CLI/hparam の統一 (b) 将来 Conv2d
        # 系 (例: 2D spectrogram head) を Generator に追加する時の
        # future-proofing plumbing、 の 2 目的で通す。 crash-safe: 対象 tensor
        # がゼロでも torch は例外を出さない。
        use_channels_last: bool = False,
        # v10 E1 (--film-init-std): Multi-scale FiLM (cond_layers) の
        # zero-init を N(0, std) small-Gaussian に置換する opt-in
        # (AdaLN-Zero 分析: 同等品質に ~46% 少ない学習時間)。0.0 (default)
        # は従来どおり zero-init (v9 bit 互換)。bias は常に 0。
        film_init_std: float = 0.0,
        # v11 P0 (--film-free-scale): FiLM scale を sigmoid(raw)+0.5 の
        # [0.5, 1.5] 制限から 1+γ̂ (無界) に開放する opt-in。FiLM 原典が
        # 「γ の sigmoid/tanh 制限は劣化」を実証済み (conditioning 設計 doc
        # §5.2 b-1)。zero-init 層では raw=0 → scale=1.0 で両形式が一致する
        # ため on 直後の挙動は clamped 形と一致。default off = v10b bit 互換。
        film_free_scale: bool = False,
        # v10b H-1 (--upsample-mode): "transposed" (default、v10a bit 互換) か
        # "resize" (nearest resize + kernel 縮小 Conv1d、checkerboard 除去)。
        upsample_mode: str = "transposed",
        # v10b H-2b: PQMF を自前構築する場合の taps / 学習可能合成フィルタ。
        # ``pqmf`` を渡した場合は無視される (共有インスタンス側の設定が勝つ)。
        pqmf_taps: int = 62,
        trainable_pqmf_synthesis: bool = False,
        # --- v10b S-2 (F0 明示経路、default off = v10a-r2 bit 互換。
        # docs/design/zero-shot-v10b-s2-f0-design.md §6.1) ---
        # S-2a + S-2c を一括で有効化する。有効時は forward に ``f0`` が必須。
        use_f0_path: bool = False,
        # S-2a: frame 格子 (SR/256) で [log f0, V/UV] を射影して conv_pre 入力へ
        f0_feat_channels: int = 8,
        # S-2c: head 格子 (SR/16) の位相テンプレートを射影して head 入力へ
        f0_head_channels: int = 8,
        f0_harmonics: int = 8,
        # 位相の格子計算に必要な音響パラメータ (mel hop = frame 格子の周期)
        sample_rate: int = 22050,
        f0_frame_hop: int = 256,
        # --- v11 A′ (--use-carrier-head、default off = v10b bit 互換。
        # docs/design/zero-shot-v11-harmonic-head-design.md) ---
        # 有効時: band0 の head 出力を log σ 9ch (random-phase noise 枝) に
        # 縮め、voiced 帯域 (≤3kHz) の調波エネルギーは CarrierHead (解析重み
        # 付き 2-band 担体) 経由でしか出せなくする。S-2c (head 位相テンプレート
        # concat) は担体で置換される (S-2a / S-2p / S-2r は共存)。
        use_carrier_head: bool = False,
        carrier_harmonics: int = 32,
        # --- v11 P3 (--use-adain-decoder、default off = v10b bit 互換。
        # conditioning 設計 doc §5.1 a-2 / §10.5) ---
        # resblock 単位の zero-init 残差 AdaIN。注入重心は s1 (ups[0] 後の
        # 中解像度段、LOO 実測 s1 ≫ s2 > 入口): s1 は全 resblock、以降の段は
        # 半分 (floor)、入口 (conv_pre 段) は省略。既存 FiLM (cond /
        # cond_layers) とは独立に共存する (置換ではなく追加 — 単変量で
        # 切り分けられるように)。
        use_adain_decoder: bool = False,
    ):
        super().__init__()
        if upsample_mode not in ("transposed", "resize"):
            raise ValueError(
                f"upsample_mode must be 'transposed' or 'resize', got {upsample_mode!r}"
            )
        if use_carrier_head and not use_f0_path:
            raise ValueError(
                "use_carrier_head requires use_f0_path=True: the carrier head "
                "consumes the frame-level F0 that the S-2 predictor provides."
            )
        self.num_kernels = len(resblock_kernel_sizes)
        self.num_upsamples = len(upsample_rates)
        self.subbands = subbands
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.onnx_export_mode = False
        self.use_channels_last = use_channels_last
        self.upsample_mode = upsample_mode
        self.use_f0_path = use_f0_path
        self.use_carrier_head = use_carrier_head
        self.film_free_scale = film_free_scale
        self.use_adain_decoder = use_adain_decoder
        if use_adain_decoder and gin_channels == 0:
            raise ValueError(
                "use_adain_decoder requires gin_channels > 0: the AdaIN "
                "affine (gamma, beta) is computed from the speaker "
                "conditioning g. Single-speaker models have no g to condition "
                "on."
            )

        # --- v10b S-2a: frame 格子の F0 特徴 (conv_pre 入力へ concat) ---
        # zero-init: 学習開始時は F0 の値に依存しない出力になり、smoke 失敗時に
        # 経路を切る退避が bit レベルで安全になる (設計 doc §6.2)。出力が 0 でも
        # 入力側重みの勾配は非ゼロなので学習は普通に進む
        # (test_zero_init_projections_still_receive_gradient が固定)。
        conv_pre_in = initial_channel
        if use_f0_path:
            self.f0_feat = Conv1d(2, f0_feat_channels, 1)
            nn.init.zeros_(self.f0_feat.weight)
            nn.init.zeros_(self.f0_feat.bias)
            conv_pre_in += f0_feat_channels

        # --- conv_pre ---
        self.conv_pre = weight_norm(
            Conv1d(conv_pre_in, upsample_initial_channel, 7, 1, padding=3)
        )

        # --- ResBlock selection ---
        resblock_module = ResBlock1 if resblock == "1" else ResBlock2

        # --- Upsampling layers (2 stages: 4x, 4x = 16x total) ---
        self.ups = nn.ModuleList()
        for i, (u, k) in enumerate(
            zip(upsample_rates, upsample_kernel_sizes, strict=False)
        ):
            ch_in = upsample_initial_channel // (2**i)
            ch_out = upsample_initial_channel // (2 ** (i + 1))
            if upsample_mode == "resize":
                self.ups.append(NearestResizeUpsample(ch_in, ch_out, k, u))
            else:
                self.ups.append(
                    weight_norm(
                        ConvTranspose1d(
                            ch_in,
                            ch_out,
                            k,
                            u,
                            padding=(k - u) // 2,
                        )
                    )
                )

        # --- ResBlocks after each upsampling stage ---
        self.resblocks = nn.ModuleList()
        for i in range(len(self.ups)):
            ch = upsample_initial_channel // (2 ** (i + 1))
            for _j, (k, d) in enumerate(
                zip(resblock_kernel_sizes, resblock_dilation_sizes, strict=False)
            ):
                self.resblocks.append(resblock_module(ch, k, d))

        # --- v10b S-2c: head 格子の harmonic 位相テンプレート ---
        # 位相が実際に消費される唯一の格子 (head) に位相参照を置く。head_proj も
        # zero-init (S-2a と同じ理由)。
        post_in_channels = upsample_initial_channel // (2 ** len(upsample_rates))
        if use_f0_path and not use_carrier_head:
            # v11: carrier head 有効時は S-2c を置換する (担体そのものが位相
            # 参照の「線形結合への制限」なので、参照の concat は冗長)。
            head_upsample = 1
            for u in upsample_rates:
                head_upsample *= u
            self.phase_template = HarmonicPhaseTemplate(
                n_harmonics=f0_harmonics,
                upsample=head_upsample,
                sample_rate=sample_rate,
                frame_hop=f0_frame_hop,
            )
            self.head_proj = Conv1d(
                self.phase_template.out_channels, f0_head_channels, 1
            )
            nn.init.zeros_(self.head_proj.weight)
            nn.init.zeros_(self.head_proj.bias)
            post_in_channels += f0_head_channels

        # --- Sub-band convolution (no weight_norm) ---
        # v11 carrier head 有効時: band0 は log σ (n_fft//2+1 ch) のみ —
        # mag/phase の自由度を noise 枝に縮め、調波は担体経由に限定する。
        if use_carrier_head:
            post_out_channels = (n_fft // 2 + 1) + (subbands - 1) * (n_fft + 2)
        else:
            post_out_channels = subbands * (n_fft + 2)
        self.subband_conv_post = Conv1d(
            post_in_channels, post_out_channels, 7, padding=3
        )

        # --- iSTFT ---
        self.istft = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)

        # --- PQMF (shared instance or create new) ---
        self.pqmf = (
            pqmf
            if pqmf is not None
            else PQMF(
                subbands=subbands,
                taps=pqmf_taps,
                trainable_synthesis=trainable_pqmf_synthesis,
            )
        )

        # --- v11 A′: 担体化 harmonic-plus-noise head ---
        if use_carrier_head:
            # 担体の alias 相殺は canonical (固定) PQMF synthesis が前提
            # (設計 doc §4.1 #6 / §8 R5)。trainable synthesis と併用すると
            # 相殺が学習で壊れうるため構造的に排他にする。
            if isinstance(getattr(self.pqmf, "synthesis_filter", None), nn.Parameter):
                raise ValueError(
                    "use_carrier_head requires a fixed (canonical) PQMF "
                    "synthesis bank: the carrier's 2-band alias cancellation "
                    "assumes the ±(-1)^k·π/4 modulation phase pair. Disable "
                    "trainable_pqmf_synthesis."
                )
            self.carrier_head = CarrierHead(
                in_channels=upsample_initial_channel,
                pqmf=self.pqmf,
                n_harmonics=carrier_harmonics,
                sample_rate=sample_rate,
                frame_hop=f0_frame_hop,
            )
            # 学習時に forward が (E_h, E_n) の frame エネルギーを stash する
            # (L_src hinge = carrier_source_regularization の入力。default off)。
            self.last_carrier_energies: tuple[torch.Tensor, torch.Tensor] | None = None

        # --- Weight initialisation (ups only) ---
        # resize モードは NearestResizeUpsample が interpolation-filter init を
        # 済ませているため適用しない (init_weights は weight_norm 済み module の
        # ``weight`` 属性を書くだけで forward pre-hook に上書きされる = 実質
        # no-op だが、意図を明示するため mode で分ける)。
        if upsample_mode == "transposed":
            self.ups.apply(init_weights)

        # --- Speaker conditioning (Multi-scale FiLM) ---
        # ``conv_pre`` 直後の Input-stage FiLM と各 upsample 段ごとの FiLM 層を
        # 持つことで、speaker 情報を decoder の各解像度に注入する。
        # 旧 Generator (HiFi-GAN) の Multi-scale FiLM 構造を MB-iSTFT に移植
        # (zero-shot multi-6lang スクラッチ学習で 32-true 数値安定性向上が目的)。
        self.gin_channels = gin_channels
        if gin_channels != 0:
            # Input-stage FiLM: 出力 channel を 2 倍 (scale + shift)
            self.cond = nn.Conv1d(gin_channels, upsample_initial_channel * 2, 1)

            # Multi-scale FiLM: 各 upsample 段の出力チャネルに対する scale + shift
            self.cond_layers = nn.ModuleList()
            for i in range(self.num_upsamples):
                ch_stage = upsample_initial_channel // (2 ** (i + 1))
                layer = nn.Conv1d(gin_channels, ch_stage * 2, 1)
                if film_init_std > 0:
                    # v10 E1: zero-init を small-Gaussian に置換 (opt-in)。
                    # 対称性破りにより FiLM の条件付け獲得を早める。
                    nn.init.normal_(layer.weight, 0.0, film_init_std)
                    nn.init.zeros_(layer.bias)
                else:
                    # Zero-init: scale_raw=0 → sigmoid(0)+0.5=1.0, shift=0
                    # → 学習開始時 FiLM は identity、徐々に speaker 条件付けを獲得
                    nn.init.zeros_(layer.weight)
                    nn.init.zeros_(layer.bias)
                self.cond_layers.append(layer)

        # --- v11 P3: resblock 単位 AdaIN (s1 重心レイアウト) ---
        # key = self.resblocks のグローバル index (str)。s1 (stage 0、128ch 相当)
        # は全 num_kernels resblock、以降の段は floor(num_kernels/2) 個のみ
        # (LOO: s1 0.150 ≫ s2 0.067、conditioning doc §10.5)。medium 実構成
        # (gin=512, 256→128/64ch, num_kernels=3) で +0.46M params ≈ +0.92MB
        # fp16 — doc §5.1 (a-2) の +0.45M/+0.9MB 見積と一致し、FP16 40MB gate
        # (残り ~1.2MB) 内に収まる。
        if use_adain_decoder:
            self.adain_layers = nn.ModuleDict()
            for i in range(self.num_upsamples):
                ch_stage = upsample_initial_channel // (2 ** (i + 1))
                n_sites = self.num_kernels if i == 0 else self.num_kernels // 2
                for j in range(n_sites):
                    self.adain_layers[str(i * self.num_kernels + j)] = AdaIN1d(
                        gin_channels, ch_stage
                    )

        # T1 拡張: channels_last をモジュール全体に伝播。 現状 Generator は
        # Conv1d のみのため PyTorch は 3D weight に対し memory_format 変換を
        # skip する (torch/nn/modules/module.py::_apply → convert: t.dim() in
        # (4, 5) guard)。 従ってこの呼び出しは Conv1d weight tensor を書き換えず、
        # forward 挙動も bit-identical。 将来 Generator に Conv2d が追加された
        # 時、 その 4D weight は自動で NHWC 化される (D の T1 実装と同型)。
        if self.use_channels_last:
            self.to(memory_format=torch.channels_last)

    @staticmethod
    def _apply_film(
        x: torch.Tensor, scale_shift: torch.Tensor, free_scale: bool = False
    ) -> torch.Tensor:
        """FiLM (Feature-wise Linear Modulation) を適用する。

        ``scale_shift`` を channel 軸で 2 分割し、前半を scale_raw、後半を shift とする。

        - ``free_scale=False`` (default、v10b 互換):
          ``scale = sigmoid(scale_raw) + 0.5`` で [0.5, 1.5] のレンジに制限。
          sigmoid 中心 0.5 によりチャネル完全抑制 (=0) を起こさず安定。
        - ``free_scale=True`` (v11 P0、--film-free-scale):
          ``scale = 1 + scale_raw`` (無界、1+γ̂ 形式)。FiLM 原典は γ の
          sigmoid/tanh 制限が有害と実証しており、[0.5, 1.5] クランプは
          条件付け容量を狭める (conditioning 設計 doc §5.2 b-1)。zero-init
          層では scale_raw=0 → scale=1.0 となり両形式の初期挙動は一致する。

        ``x = x * scale + shift`` を計算する。
        """
        scale_raw, shift = scale_shift.split(scale_shift.size(1) // 2, dim=1)
        if free_scale:
            scale = 1.0 + scale_raw
        else:
            scale = torch.sigmoid(scale_raw) + 0.5
        return x * scale + shift

    def carrier_noise_band0(
        self, log_sigma: torch.Tensor, noise_ri: torch.Tensor
    ) -> torch.Tensor:
        """v11 A′ noise 枝: band0 の random-phase iSTFT 合成。

        ``X_n[k,t] = σ[k,t]·(n_r + j·n_i)/√2``、``n ~ N(0,1)`` i.i.d. per
        (bin, frame)。frame ごとに独立な複素位相なので OLA 後も frame 間
        コヒーレンスが皆無 = **持続トーン (調波) を構造的に生成できない**
        (敵対的な F0 同期 AM σ でも comb-HNR 0.19-0.54dB、設計 doc §5.1 #4)。
        表現できるのは「bin 幅 344.5Hz より粗いスペクトル包絡 × head 格子
        (689Hz) までの時間変調をもつノイズ」= 気息・摩擦成分のモデルクラス。

        Args:
            log_sigma: ``[B, n_fft//2+1, T_head]`` (clamp 前の head 出力)
            noise_ri: ``[B, n_fft+2, T_head]`` の N(0,1) (前半 real、後半 imag)

        Returns:
            band0 noise 波形 ``[B, 1, T_raw]`` (trim 前)
        """
        n_half = self.n_fft // 2 + 1
        sigma = torch.exp(log_sigma.clamp(min=-9.0, max=6.0))
        inv_sqrt2 = 0.7071067811865476
        real = sigma * noise_ri[:, :n_half] * inv_sqrt2
        imag = sigma * noise_ri[:, n_half:] * inv_sqrt2
        combined = torch.cat([real, imag], dim=1)
        return F.conv_transpose1d(
            combined, self.istft.inverse_basis, stride=self.hop_length
        )

    def forward(
        self,
        x: torch.Tensor,
        g: torch.Tensor | None = None,
        f0: torch.Tensor | None = None,
        carrier_noise: torch.Tensor | None = None,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """Generate waveform from latent representation.

        Args:
            x: Latent ``[B, initial_channel, T_frames]``.
            g: Speaker embedding ``[B, gin_channels, 1]`` (optional).
            f0: Frame-level F0 in Hz ``[B, 1, T_frames]`` (unvoiced = 0).
                Required when ``use_f0_path`` is enabled; ignored otherwise
                (so existing callers can pass it unconditionally).
            carrier_noise: v11 A′ noise 枝の N(0,1) ``[B, n_fft+2, T_head]``。
                None (default) なら内部でサンプル (ONNX export では
                ``RandomNormalLike`` になる)。決定的な parity テスト用の注入点。

        Returns:
            If ``onnx_export_mode`` is False (training):
                ``(fullband, subbands)`` where fullband is ``[B, 1, T]``
                and subbands is ``[B, subbands, T_sub]``.
            If ``onnx_export_mode`` is True (ONNX inference):
                ``fullband`` only ``[B, 1, T]``.
        """
        if self.use_f0_path:
            if f0 is None:
                raise ValueError(
                    "use_f0_path is enabled but f0 was not provided to "
                    "MBiSTFTGenerator.forward(). Pass frame-level f0 "
                    "[B, 1, T_frames] (Hz, unvoiced = 0)."
                )
            # S-2a: frame 格子で F0 の「値」情報 (音域・帯域包絡の F0 依存) を渡す
            f0_frame = f0.to(x.dtype)
            uv = (f0_frame > 1.0).to(x.dtype)
            log_f0 = torch.log(f0_frame.clamp(min=1.0)) / 6.0
            x = torch.cat([x, self.f0_feat(torch.cat([log_f0, uv], dim=1))], dim=1)

        x = self.conv_pre(x)
        if g is not None and self.gin_channels != 0:
            # Input-stage FiLM (scale + shift) — 旧加算のみから FiLM へ強化
            x = self._apply_film(x, self.cond(g), self.film_free_scale)
        # v11 A′: 担体ゲインは frame 格子 trunk (話者 FiLM 済) から出す。
        # frame 格子 (86.1Hz) + 固定平滑がゲイン変調帯域を制限する = 構造保証
        # の本体 (head 格子ゲインだと comb-HNR 0.5dB に崩壊、設計 doc §5.1)。
        x_frame = x if self.use_carrier_head else None

        for i, up in enumerate(self.ups):
            x = F.leaky_relu(x, LRELU_SLOPE)
            x = up(x)
            xs = None
            for j, resblock in enumerate(self.resblocks):
                index = j - (i * self.num_kernels)
                if index < 0 or index >= self.num_kernels:
                    continue
                h = x
                # v11 P3: resblock 入口に AdaIN。resblock は leaky_relu → conv
                # で始まるため、これで StyleTTS 2 テンプレート
                # (AdaIN → 活性 → Conv) の順序になる。
                if (
                    self.use_adain_decoder
                    and g is not None
                    and str(j) in self.adain_layers
                ):
                    h = self.adain_layers[str(j)](h, g)
                if index == 0:
                    xs = resblock(h)
                else:
                    xs = xs + resblock(h)
            x = xs / self.num_kernels
            # Multi-scale FiLM: 各 upsample 段の出力に speaker 条件付けを注入
            if g is not None and self.gin_channels != 0:
                x = self._apply_film(x, self.cond_layers[i](g), self.film_free_scale)

        x = F.leaky_relu(x, LRELU_SLOPE)
        if self.use_f0_path and not self.use_carrier_head:
            # S-2c: head 格子で位相参照を渡す。head は各 (band, bin) の位相を
            # この参照からの差分として出せばよく、自力で積分せずに済む。
            x = torch.cat(
                [x, self.head_proj(self.phase_template(f0).to(x.dtype))], dim=1
            )
        x = self.subband_conv_post(x)  # [B, post_out_channels, T_frames]

        B = x.size(0)
        T_frames = x.size(-1)
        n_half = self.n_fft // 2 + 1  # 9

        # Trim length: conv_transpose1d produces (T-1)*stride + kernel extra
        # samples; trim to T_frames * hop_length so PQMF synthesis yields
        # exact segment_size.
        expected_sub_T = T_frames * self.hop_length

        if self.use_carrier_head:
            # --- v11 A′: band0 = noise 枝 (log σ) + 担体 s0、
            #     band1 = 自由 head + 担体 s1、band2-3 = 自由 head のまま ---
            log_sigma = x[:, :n_half, :]
            if carrier_noise is None:
                # randn_like で dynamic shape を保つ (ONNX: RandomNormalLike。
                # 既存 piper graph の z サンプリングに前例あり)
                carrier_noise = torch.randn_like(
                    torch.cat([log_sigma, log_sigma], dim=1)
                )
            band0_noise = self.carrier_noise_band0(log_sigma, carrier_noise)
            noise0 = band0_noise.reshape(B, 1, -1)[..., :expected_sub_T]

            x123 = x[:, n_half:, :].reshape(
                B, self.subbands - 1, self.n_fft + 2, T_frames
            )
            mag = torch.exp(x123[:, :, :n_half, :]).reshape(
                B * (self.subbands - 1), n_half, T_frames
            )
            phase = (torch.sin(x123[:, :, n_half:, :]) * math.pi).reshape(
                B * (self.subbands - 1), n_half, T_frames
            )
            sub123 = self.istft(mag, phase).reshape(B, self.subbands - 1, -1)[
                ..., :expected_sub_T
            ]

            # 担体 (frame 格子ゲイン → SR/4 subband 波形、2-band 解析重み描画)
            s0, s1 = self.carrier_head(x_frame, f0)
            s0 = s0[..., :expected_sub_T]
            s1 = s1[..., :expected_sub_T]

            if not self.onnx_export_mode:
                # L_src hinge (carrier_source_regularization、default off) と
                # Phase D 縮退監視 (枝エネルギー比 ρ) 用の frame エネルギー。
                frames_in = f0.size(-1)
                e_h = s0.float().pow(2).reshape(B, frames_in, -1).sum(-1)
                e_h = e_h + s1.float().pow(2).reshape(B, frames_in, -1).sum(-1)
                e_n = noise0.float().pow(2).reshape(B, frames_in, -1).sum(-1)
                self.last_carrier_energies = (e_h, e_n)

            subbands_signal = torch.cat(
                [
                    noise0 + s0.to(noise0.dtype),
                    sub123[:, 0:1] + s1.to(noise0.dtype),
                    sub123[:, 1:],
                ],
                dim=1,
            )  # [B, subbands, T_sub]
        else:
            # Reshape: [B, subbands, n_fft+2, T_frames]
            x = x.reshape(B, self.subbands, self.n_fft + 2, T_frames)

            # Magnitude (positive via exp) and phase (bounded to [-pi, pi] via sin)
            mag = torch.exp(x[:, :, :n_half, :])  # [B, subbands, 9, T_frames]
            phase = (
                torch.sin(x[:, :, n_half:, :]) * math.pi
            )  # [B, subbands, 9, T_frames]

            # Flatten subbands into batch for iSTFT (expects [B, n_fft//2+1, T])
            mag = mag.reshape(B * self.subbands, n_half, T_frames)
            phase = phase.reshape(B * self.subbands, n_half, T_frames)
            sub_wav = self.istft(mag, phase)  # [B*subbands, 1, T_sub_raw]
            subbands_signal = sub_wav.reshape(
                B, self.subbands, -1
            )  # [B, subbands, T_sub_raw]

            subbands_signal = subbands_signal[
                ..., :expected_sub_T
            ]  # [B, subbands, T_sub]

        # PQMF synthesis: [B, subbands, T_sub] -> [B, 1, T]
        fullband = self.pqmf.synthesis(subbands_signal)

        if self.onnx_export_mode:
            return fullband
        return fullband, subbands_signal

    def remove_weight_norm(self):
        """Remove weight normalization from conv_pre and all upsampling layers.

        Called before ONNX export. ``subband_conv_post`` is excluded
        (no weight_norm was applied to it).
        """
        print("Removing weight norm...")
        remove_weight_norm(self.conv_pre)
        for l in self.ups:  # noqa: E741
            # resize モード (NearestResizeUpsample) は内側の Conv1d が持つ
            remove_weight_norm(l.conv if isinstance(l, NearestResizeUpsample) else l)
        for l in self.resblocks:  # noqa: E741
            l.remove_weight_norm()
