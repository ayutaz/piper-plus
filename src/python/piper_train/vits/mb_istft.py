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
        # v10b H-1 (--upsample-mode): "transposed" (default、v10a bit 互換) か
        # "resize" (nearest resize + kernel 縮小 Conv1d、checkerboard 除去)。
        upsample_mode: str = "transposed",
        # v10b H-2b: PQMF を自前構築する場合の taps / 学習可能合成フィルタ。
        # ``pqmf`` を渡した場合は無視される (共有インスタンス側の設定が勝つ)。
        pqmf_taps: int = 62,
        trainable_pqmf_synthesis: bool = False,
    ):
        super().__init__()
        if upsample_mode not in ("transposed", "resize"):
            raise ValueError(
                f"upsample_mode must be 'transposed' or 'resize', got {upsample_mode!r}"
            )
        self.num_kernels = len(resblock_kernel_sizes)
        self.num_upsamples = len(upsample_rates)
        self.subbands = subbands
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.onnx_export_mode = False
        self.use_channels_last = use_channels_last
        self.upsample_mode = upsample_mode

        # --- conv_pre ---
        self.conv_pre = weight_norm(
            Conv1d(initial_channel, upsample_initial_channel, 7, 1, padding=3)
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

        # --- Sub-band convolution (no weight_norm) ---
        post_in_channels = upsample_initial_channel // (2 ** len(upsample_rates))
        self.subband_conv_post = Conv1d(
            post_in_channels, subbands * (n_fft + 2), 7, padding=3
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

        # T1 拡張: channels_last をモジュール全体に伝播。 現状 Generator は
        # Conv1d のみのため PyTorch は 3D weight に対し memory_format 変換を
        # skip する (torch/nn/modules/module.py::_apply → convert: t.dim() in
        # (4, 5) guard)。 従ってこの呼び出しは Conv1d weight tensor を書き換えず、
        # forward 挙動も bit-identical。 将来 Generator に Conv2d が追加された
        # 時、 その 4D weight は自動で NHWC 化される (D の T1 実装と同型)。
        if self.use_channels_last:
            self.to(memory_format=torch.channels_last)

    @staticmethod
    def _apply_film(x: torch.Tensor, scale_shift: torch.Tensor) -> torch.Tensor:
        """FiLM (Feature-wise Linear Modulation) を適用する。

        ``scale_shift`` を channel 軸で 2 分割し、前半を scale_raw、後半を shift とする。
        ``scale = sigmoid(scale_raw) + 0.5`` で [0.5, 1.5] のレンジに制限し、
        ``x = x * scale + shift`` を計算する。
        sigmoid 中心 0.5 によりチャネル完全抑制 (=0) を起こさず安定。
        """
        scale_raw, shift = scale_shift.split(scale_shift.size(1) // 2, dim=1)
        scale = torch.sigmoid(scale_raw) + 0.5
        return x * scale + shift

    def forward(
        self, x: torch.Tensor, g: torch.Tensor | None = None
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """Generate waveform from latent representation.

        Args:
            x: Latent ``[B, initial_channel, T_frames]``.
            g: Speaker embedding ``[B, gin_channels, 1]`` (optional).

        Returns:
            If ``onnx_export_mode`` is False (training):
                ``(fullband, subbands)`` where fullband is ``[B, 1, T]``
                and subbands is ``[B, subbands, T_sub]``.
            If ``onnx_export_mode`` is True (ONNX inference):
                ``fullband`` only ``[B, 1, T]``.
        """
        x = self.conv_pre(x)
        if g is not None and self.gin_channels != 0:
            # Input-stage FiLM (scale + shift) — 旧加算のみから FiLM へ強化
            x = self._apply_film(x, self.cond(g))

        for i, up in enumerate(self.ups):
            x = F.leaky_relu(x, LRELU_SLOPE)
            x = up(x)
            xs = None
            for j, resblock in enumerate(self.resblocks):
                index = j - (i * self.num_kernels)
                if index == 0:
                    xs = resblock(x)
                elif (index > 0) and (index < self.num_kernels):
                    xs = xs + resblock(x)
            x = xs / self.num_kernels
            # Multi-scale FiLM: 各 upsample 段の出力に speaker 条件付けを注入
            if g is not None and self.gin_channels != 0:
                x = self._apply_film(x, self.cond_layers[i](g))

        x = F.leaky_relu(x, LRELU_SLOPE)
        x = self.subband_conv_post(x)  # [B, subbands * (n_fft + 2), T_frames]

        B = x.size(0)
        T_frames = x.size(-1)
        n_half = self.n_fft // 2 + 1  # 9

        # Reshape: [B, subbands, n_fft+2, T_frames]
        x = x.reshape(B, self.subbands, self.n_fft + 2, T_frames)

        # Magnitude (positive via exp) and phase (bounded to [-pi, pi] via sin)
        mag = torch.exp(x[:, :, :n_half, :])  # [B, subbands, 9, T_frames]
        phase = torch.sin(x[:, :, n_half:, :]) * math.pi  # [B, subbands, 9, T_frames]

        # Flatten subbands into batch for iSTFT (expects [B, n_fft//2+1, T])
        mag = mag.reshape(B * self.subbands, n_half, T_frames)
        phase = phase.reshape(B * self.subbands, n_half, T_frames)
        sub_wav = self.istft(mag, phase)  # [B*subbands, 1, T_sub_raw]
        subbands_signal = sub_wav.reshape(
            B, self.subbands, -1
        )  # [B, subbands, T_sub_raw]

        # Trim iSTFT output to expected length.
        # conv_transpose1d produces (T-1)*stride + kernel extra samples;
        # trim to T_frames * hop_length so PQMF synthesis yields exact segment_size.
        expected_sub_T = T_frames * self.hop_length
        subbands_signal = subbands_signal[..., :expected_sub_T]  # [B, subbands, T_sub]

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
