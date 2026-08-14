import math
from typing import NamedTuple

import torch
from torch import autocast, nn
from torch.nn import Conv1d, Conv2d, functional as F
from torch.nn.utils import spectral_norm, weight_norm

from . import attentions, commons, modules, monotonic_align
from .commons import get_padding
from .mb_istft import MBiSTFTGenerator


class InferOutput(NamedTuple):
    """Return type of :meth:`SynthesizerTrn.infer`.

    A NamedTuple so callers can use positional unpacking (``audio, *_ =``)
    or named access (``result.durations``).
    """

    audio: torch.Tensor
    attn: torch.Tensor
    y_mask: torch.Tensor
    latents: tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]
    durations: torch.Tensor


class StochasticDurationPredictor(nn.Module):
    def __init__(
        self,
        in_channels: int,
        filter_channels: int,
        kernel_size: int,
        p_dropout: float,
        n_flows: int = 4,
        gin_channels: int = 0,
        # v10 M3: False で duration NLL の勾配を g へ通す (--dp-spk-head)。
        # default True は従来の detach 維持 (v9 bit 互換)。
        detach_g: bool = True,
    ):
        super().__init__()
        filter_channels = in_channels  # it needs to be removed from future version.
        self.in_channels = in_channels
        self.filter_channels = filter_channels
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.n_flows = n_flows
        self.gin_channels = gin_channels
        self.detach_g = detach_g

        self.log_flow = modules.Log()
        self.flows = nn.ModuleList()
        self.flows.append(modules.ElementwiseAffine(2))
        for _i in range(n_flows):
            self.flows.append(
                modules.ConvFlow(2, filter_channels, kernel_size, n_layers=3)
            )
            self.flows.append(modules.Flip())

        self.post_pre = nn.Conv1d(1, filter_channels, 1)
        self.post_proj = nn.Conv1d(filter_channels, filter_channels, 1)
        self.post_convs = modules.DDSConv(
            filter_channels, kernel_size, n_layers=3, p_dropout=p_dropout
        )
        self.post_flows = nn.ModuleList()
        self.post_flows.append(modules.ElementwiseAffine(2))
        for _i in range(4):
            self.post_flows.append(
                modules.ConvFlow(2, filter_channels, kernel_size, n_layers=3)
            )
            self.post_flows.append(modules.Flip())

        self.pre = nn.Conv1d(in_channels, filter_channels, 1)
        self.proj = nn.Conv1d(filter_channels, filter_channels, 1)
        self.convs = modules.DDSConv(
            filter_channels, kernel_size, n_layers=3, p_dropout=p_dropout
        )
        if gin_channels != 0:
            self.cond = nn.Conv1d(gin_channels, filter_channels, 1)

    def forward(self, x, x_mask, w=None, g=None, reverse=False, noise_scale=1.0):
        x = torch.detach(x)
        x = self.pre(x)
        if g is not None:
            # v10 M3: detach_g=False で duration NLL の勾配を g へ通す。
            # 呼び出し側 (_get_dp_conditioning) は g_dp = g.detach() +
            # spk_proj_dp(g.detach()) を渡すため、勾配は残差ヘッドのみに届く。
            if self.detach_g:
                g = torch.detach(g)
            x = x + self.cond(g)
        x = self.convs(x, x_mask)
        x = self.proj(x) * x_mask

        if not reverse:
            flows = self.flows
            assert w is not None

            logdet_tot_q = 0
            h_w = self.post_pre(w)
            h_w = self.post_convs(h_w, x_mask)
            h_w = self.post_proj(h_w) * x_mask
            e_q = torch.randn(w.size(0), 2, w.size(2)).type_as(x) * x_mask
            z_q = e_q
            for flow in self.post_flows:
                z_q, logdet_q = flow(z_q, x_mask, g=(x + h_w))
                logdet_tot_q += logdet_q
            z_u, z1 = torch.split(z_q, [1, 1], 1)
            u = torch.sigmoid(z_u) * x_mask
            z0 = (w - u) * x_mask
            logdet_tot_q += torch.sum(
                (F.logsigmoid(z_u) + F.logsigmoid(-z_u)) * x_mask, [1, 2]
            )
            logq = (
                torch.sum(-0.5 * (math.log(2 * math.pi) + (e_q**2)) * x_mask, [1, 2])
                - logdet_tot_q
            )

            logdet_tot = 0
            z0, logdet = self.log_flow(z0, x_mask)
            logdet_tot += logdet
            z = torch.cat([z0, z1], 1)
            for flow in flows:
                z, logdet = flow(z, x_mask, g=x, reverse=reverse)
                logdet_tot = logdet_tot + logdet
            nll = (
                torch.sum(0.5 * (math.log(2 * math.pi) + (z**2)) * x_mask, [1, 2])
                - logdet_tot
            )
            return nll + logq  # [b]
        else:
            flows = list(reversed(self.flows))
            flows = flows[:-2] + [flows[-1]]  # remove a useless vflow
            # Use zeros for deterministic ONNX export
            if getattr(self, "onnx_export_mode", False):
                z = torch.zeros(x.size(0), 2, x.size(2)).type_as(x)
            else:
                z = torch.randn(x.size(0), 2, x.size(2)).type_as(x) * noise_scale

            for flow in flows:
                z = flow(z, x_mask, g=x, reverse=reverse)
            z0, z1 = torch.split(z, [1, 1], 1)
            logw = z0
            return logw


class DurationPredictor(nn.Module):
    def __init__(
        self,
        in_channels: int,
        filter_channels: int,
        kernel_size: int,
        p_dropout: float,
        gin_channels: int = 0,
        # v10 M3: False で duration loss の勾配を g へ通す (--dp-spk-head)。
        detach_g: bool = True,
    ):
        super().__init__()

        self.in_channels = in_channels
        self.filter_channels = filter_channels
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.gin_channels = gin_channels
        self.detach_g = detach_g

        self.drop = nn.Dropout(p_dropout)
        self.conv_1 = nn.Conv1d(
            in_channels, filter_channels, kernel_size, padding=kernel_size // 2
        )
        self.norm_1 = modules.LayerNorm(filter_channels)
        self.conv_2 = nn.Conv1d(
            filter_channels, filter_channels, kernel_size, padding=kernel_size // 2
        )
        self.norm_2 = modules.LayerNorm(filter_channels)
        self.proj = nn.Conv1d(filter_channels, 1, 1)

        if gin_channels != 0:
            self.cond = nn.Conv1d(gin_channels, in_channels, 1)

    def forward(self, x, x_mask, g=None):
        x = torch.detach(x)
        if g is not None:
            # v10 M3: detach_g=False で duration loss の勾配を g へ通す
            # (x = torch.detach(x) は常に維持)。
            if self.detach_g:
                g = torch.detach(g)
            x = x + self.cond(g)
        x = self.conv_1(x * x_mask)
        x = torch.relu(x)
        x = self.norm_1(x)
        x = self.drop(x)
        x = self.conv_2(x * x_mask)
        x = torch.relu(x)
        x = self.norm_2(x)
        x = self.drop(x)
        x = self.proj(x * x_mask)
        return x * x_mask


class TextEncoder(nn.Module):
    def __init__(
        self,
        n_vocab: int,
        out_channels: int,
        hidden_channels: int,
        filter_channels: int,
        n_heads: int,
        n_layers: int,
        kernel_size: int,
        p_dropout: float,
        gin_channels: int = 0,
        # T3: opt-in SDPA fast path for the transformer self-attention.
        # Default False preserves the manual path (bit-parity with prior
        # checkpoints). See attentions.MultiHeadAttention for the full contract.
        attn_drop_rel_v: bool = False,
        # v10 M2 (--speaker-cond-layer): 話者条件 cond_layer(g) の注入位置。
        # 0 (default) は従来どおり transformer 全層通過後の一括加算 (v9 bit
        # 互換)。N>=1 で加算を attentions.Encoder の第 N 層入口に移動する
        # (後段加算は行わない)。v10 推奨値 3 (VITS2 同構成、F3)。
        speaker_cond_layer: int = 0,
    ):
        super().__init__()
        self.n_vocab = n_vocab
        self.out_channels = out_channels
        self.hidden_channels = hidden_channels
        self.filter_channels = filter_channels
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.gin_channels = gin_channels
        if speaker_cond_layer < 0 or speaker_cond_layer > n_layers:
            raise ValueError(
                f"speaker_cond_layer must be in [0, n_layers={n_layers}], "
                f"got {speaker_cond_layer}"
            )
        self.speaker_cond_layer = speaker_cond_layer

        self.emb = nn.Embedding(n_vocab, hidden_channels)
        nn.init.normal_(self.emb.weight, 0.0, hidden_channels**-0.5)

        self.encoder = attentions.Encoder(
            hidden_channels,
            filter_channels,
            n_heads,
            n_layers,
            kernel_size,
            p_dropout,
            drop_rel_v=attn_drop_rel_v,
        )
        self.proj = nn.Conv1d(hidden_channels, out_channels * 2, 1)

        if gin_channels != 0:
            self.cond_layer = nn.Conv1d(gin_channels, hidden_channels, 1)

    def forward(self, x, x_lengths, g=None):
        x = self.emb(x) * math.sqrt(self.hidden_channels)  # [b, t, h]
        x = torch.transpose(x, 1, -1)  # [b, h, t]
        x_mask = torch.unsqueeze(
            commons.sequence_mask(x_lengths, x.size(2)), 1
        ).type_as(x)

        cond = None
        if g is not None and hasattr(self, "cond_layer"):
            cond = self.cond_layer(g)

        if cond is not None and self.speaker_cond_layer >= 1:
            # v10 M2: 第 N 層入口注入 (後段加算は行わない) — self-attention が
            # 話者情報を見られるようになる (F3 の修正)
            x = self.encoder(
                x * x_mask,
                x_mask,
                cond=cond,
                cond_layer_idx=self.speaker_cond_layer,
            )
        else:
            x = self.encoder(x * x_mask, x_mask)
            if cond is not None:
                x = (x + cond) * x_mask
        stats = self.proj(x) * x_mask

        m, logs = torch.split(stats, self.out_channels, dim=1)
        return x, m, logs, x_mask


class ResidualCouplingBlock(nn.Module):
    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        dilation_rate: int,
        n_layers: int,
        n_flows: int = 4,
        gin_channels: int = 0,
        # v10 M1 (--use-snac-flow): coupling を SNAC 化し、forward で
        # (x, logdet) を返す。default False は従来 API / 従来経路と bit 互換。
        use_snac: bool = False,
    ):
        super().__init__()
        self.channels = channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate
        self.n_layers = n_layers
        self.n_flows = n_flows
        self.gin_channels = gin_channels
        self.use_snac = use_snac

        self.flows = nn.ModuleList()
        for _i in range(n_flows):
            self.flows.append(
                modules.ResidualCouplingLayer(
                    channels,
                    hidden_channels,
                    kernel_size,
                    dilation_rate,
                    n_layers,
                    gin_channels=gin_channels,
                    mean_only=True,
                    use_snac=use_snac,
                )
            )
            self.flows.append(modules.Flip())

    def forward(self, x, x_mask, g=None, reverse=False, g_spk=None):
        if not reverse:
            if self.use_snac:
                # v10 M1: coupling ごとの logdet を累積して返す (捨てると
                # KL が静かに壊れる — design doc §4 M1 リスク)。snac 時のみ
                # (x, logdet) を返し、off 時は従来 API (x のみ) を維持する。
                logdet_tot = torch.zeros(x.size(0), dtype=x.dtype, device=x.device)
                for flow in self.flows:
                    x, logdet = flow(x, x_mask, g=g, reverse=reverse, g_spk=g_spk)
                    logdet_tot = logdet_tot + logdet
                return x, logdet_tot
            for flow in self.flows:
                x, _ = flow(x, x_mask, g=g, reverse=reverse)
            return x
        else:
            for flow in reversed(self.flows):
                x = flow(x, x_mask, g=g, reverse=reverse, g_spk=g_spk)
            return x


class PosteriorEncoder(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        hidden_channels: int,
        kernel_size: int,
        dilation_rate: int,
        n_layers: int,
        gin_channels: int = 0,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate
        self.n_layers = n_layers
        self.gin_channels = gin_channels

        self.pre = nn.Conv1d(in_channels, hidden_channels, 1)
        self.enc = modules.WN(
            hidden_channels,
            kernel_size,
            dilation_rate,
            n_layers,
            gin_channels=gin_channels,
        )
        self.proj = nn.Conv1d(hidden_channels, out_channels * 2, 1)

    def forward(self, x, x_lengths, g=None):
        x_mask = torch.unsqueeze(
            commons.sequence_mask(x_lengths, x.size(2)), 1
        ).type_as(x)
        x = self.pre(x) * x_mask
        x = self.enc(x, x_mask, g=g)
        stats = self.proj(x) * x_mask
        m, logs = torch.split(stats, self.out_channels, dim=1)
        z = (m + torch.randn_like(m) * torch.exp(logs)) * x_mask
        return z, m, logs, x_mask


class DiscriminatorP(torch.nn.Module):
    def __init__(
        self,
        period: int,
        kernel_size: int = 5,
        stride: int = 3,
        use_spectral_norm: bool = False,
        use_channels_last: bool = False,
    ):
        super().__init__()
        self.LRELU_SLOPE = 0.1
        self.period = period
        self.use_spectral_norm = use_spectral_norm
        # T1 (channels_last): after the 1D→2D view() reshape, tag the tensor with
        # torch.channels_last so subsequent Conv2d layers dispatch to nhwc
        # Tensor Core kernels (A100/Ada 6000). Silent fallback on unsupported
        # hardware (T4 sm_75). Default OFF; enabled via ``--channels-last`` CLI.
        self.use_channels_last = use_channels_last
        norm_f = weight_norm if not use_spectral_norm else spectral_norm
        self.convs = nn.ModuleList(
            [
                norm_f(
                    Conv2d(
                        1,
                        32,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(kernel_size, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        32,
                        128,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(kernel_size, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        128,
                        512,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(kernel_size, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        512,
                        1024,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(kernel_size, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        1024,
                        1024,
                        (kernel_size, 1),
                        1,
                        padding=(get_padding(kernel_size, 1), 0),
                    )
                ),
            ]
        )
        self.conv_post = norm_f(Conv2d(1024, 1, (3, 1), 1, padding=(1, 0)))

    def forward(self, x):
        fmap = []

        # 1d to 2d
        b, c, t = x.shape
        if t % self.period != 0:  # pad first
            n_pad = self.period - (t % self.period)
            x = F.pad(x, (0, n_pad), "reflect")
            t = t + n_pad
        x = x.view(b, c, t // self.period, self.period)

        # T1 (channels_last): promote to nhwc layout post-view. Conv2d weights
        # were converted to channels_last at construction time, so this
        # activation format matches the kernel's expected layout. No-op on
        # sm_75 / older hardware (PyTorch falls back to nchw kernels silently).
        if self.use_channels_last:
            x = x.contiguous(memory_format=torch.channels_last)

        for l in self.convs:  # noqa: E741
            x = l(x)
            x = F.leaky_relu(x, self.LRELU_SLOPE)
            fmap.append(x)
        x = self.conv_post(x)
        fmap.append(x)
        x = torch.flatten(x, 1, -1)

        return x, fmap


class DiscriminatorS(torch.nn.Module):
    def __init__(self, use_spectral_norm=False):
        super().__init__()
        self.LRELU_SLOPE = 0.1
        norm_f = spectral_norm if use_spectral_norm else weight_norm
        self.convs = nn.ModuleList(
            [
                norm_f(Conv1d(1, 16, 15, 1, padding=7)),
                norm_f(Conv1d(16, 64, 41, 4, groups=4, padding=20)),
                norm_f(Conv1d(64, 256, 41, 4, groups=16, padding=20)),
                norm_f(Conv1d(256, 1024, 41, 4, groups=64, padding=20)),
                norm_f(Conv1d(1024, 1024, 41, 4, groups=256, padding=20)),
                norm_f(Conv1d(1024, 1024, 5, 1, padding=2)),
            ]
        )
        self.conv_post = norm_f(Conv1d(1024, 1, 3, 1, padding=1))

    def forward(self, x):
        fmap = []

        for l in self.convs:  # noqa: E741
            x = l(x)
            x = F.leaky_relu(x, self.LRELU_SLOPE)
            fmap.append(x)
        x = self.conv_post(x)
        fmap.append(x)
        x = torch.flatten(x, 1, -1)

        return x, fmap


class MultiPeriodDiscriminator(torch.nn.Module):
    def __init__(self, use_spectral_norm=False, use_channels_last: bool = False):
        super().__init__()
        periods = [2, 3, 5, 7, 11]

        # DiscriminatorS uses Conv1d only (3D tensors) — channels_last has no 1D
        # variant, so the flag is a no-op there. DiscriminatorP uses Conv2d
        # after a 1D→2D reshape, which is where channels_last pays off.
        self.use_channels_last = use_channels_last
        discs = [DiscriminatorS(use_spectral_norm=use_spectral_norm)]
        discs = discs + [
            DiscriminatorP(
                i,
                use_spectral_norm=use_spectral_norm,
                use_channels_last=use_channels_last,
            )
            for i in periods
        ]
        self.discriminators = nn.ModuleList(discs)
        if use_channels_last:
            # Convert Conv2d weights (DiscriminatorP) to channels_last layout.
            # Conv1d weights (DiscriminatorS) remain in contiguous memory_format
            # because torch.channels_last is only defined for 4D tensors —
            # PyTorch silently keeps 1D/3D params in the default layout.
            self.to(memory_format=torch.channels_last)

    def forward(self, y, y_hat):
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        # Batch-concat optimization: y と y_hat を batch dim で結合 → 各 sub-discriminator
        # を 1 度だけ forward → split。 Conv1d/Conv2d + LeakyReLU + spectral/weight_norm +
        # reflect pad + view/flatten はいずれも batch dim を跨がないため完全等価。
        # kernel launch 数を 12 → 6 に削減し、 GPU の launch overhead / stream serialization
        # を軽減する (Ada 6000 / A100 で D backward の wall-time を短縮)。
        b = y.shape[0]
        x = torch.cat([y, y_hat], dim=0)
        for d in self.discriminators:
            y_d, fmap = d(x)
            y_d_rs.append(y_d[:b])
            y_d_gs.append(y_d[b:])
            fmap_rs.append([f[:b] for f in fmap])
            fmap_gs.append([f[b:] for f in fmap])

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class DiscriminatorR(torch.nn.Module):
    """Single-resolution linear-frequency spectrogram discriminator.

    One branch of the UnivNet-style MRD. Operates on the magnitude STFT
    ([B, 1, F, T]) at native sample rate, so it supervises the FULL band
    up to Nyquist — unlike mel-based losses (coarse high-frequency bins)
    and the 16 kHz WavLM discriminator (blind above 8 kHz). See
    docs/design/zero-shot-noise-root-cause-pqmf.md §3 (副次要因 1).
    """

    def __init__(self, resolution: tuple, use_spectral_norm: bool = False):
        super().__init__()
        self.resolution = resolution  # (n_fft, hop_length, win_length)
        # 旧 weight_norm API に合わせる (DiscriminatorP/S と同じ流儀 —
        # remap_weight_norm_keys が旧形式キーを前提とするため混在させない)
        norm_f = weight_norm if not use_spectral_norm else spectral_norm
        self.convs = nn.ModuleList(
            [
                norm_f(nn.Conv2d(1, 32, (3, 9), padding=(1, 4))),
                norm_f(nn.Conv2d(32, 32, (3, 9), stride=(1, 2), padding=(1, 4))),
                norm_f(nn.Conv2d(32, 32, (3, 9), stride=(1, 2), padding=(1, 4))),
                norm_f(nn.Conv2d(32, 32, (3, 9), stride=(1, 2), padding=(1, 4))),
                norm_f(nn.Conv2d(32, 32, (3, 3), padding=(1, 1))),
            ]
        )
        self.conv_post = norm_f(nn.Conv2d(32, 1, (3, 3), padding=(1, 1)))
        self.register_buffer("window", torch.hann_window(resolution[2]))
        self.LRELU_SLOPE = 0.1

    def spectrogram(self, x: torch.Tensor) -> torch.Tensor:
        """Waveform [B, 1, T] -> magnitude STFT [B, F, frames].

        Computed in fp32 regardless of autocast: bf16 cuFFT is both
        numerically poor and was implicated in a real training incident
        (bf16 cuFFT bug, commit 3dcabd57). The conv stack that follows
        still honours the ambient autocast context.
        """
        n_fft, hop, win = self.resolution
        with autocast(x.device.type, enabled=False):
            x = x.float().squeeze(1)
            pad = (n_fft - hop) // 2
            x = F.pad(x.unsqueeze(1), (pad, pad), mode="reflect").squeeze(1)
            spec = torch.stft(
                x,
                n_fft=n_fft,
                hop_length=hop,
                win_length=win,
                window=self.window.float(),
                center=False,
                return_complex=True,
            )
            return spec.abs()

    def forward(self, x: torch.Tensor):
        fmap = []
        x = self.spectrogram(x).unsqueeze(1)  # [B, 1, F, T]
        for conv in self.convs:
            x = F.leaky_relu(conv(x), self.LRELU_SLOPE)
            fmap.append(x)
        x = self.conv_post(x)
        fmap.append(x)
        return torch.flatten(x, 1, -1), fmap


class MultiResolutionSpectrogramDiscriminator(torch.nn.Module):
    """UnivNet-style multi-resolution spectrogram discriminator (MRD).

    Adversarial supervision of the full linear-frequency band at native
    sample rate. Added for zero-shot v9: MPD/MSD operate on raw waveforms
    and the WavLM discriminator resamples to 16 kHz, leaving 5-11 kHz
    spectral fine structure without any adversarial gradient — the band
    where multi-speaker over-smoothing noise (がびがび) lives.

    Interface matches MultiPeriodDiscriminator:
    ``forward(y, y_hat) -> (y_d_rs, y_d_gs, fmap_rs, fmap_gs)``.
    """

    def __init__(
        self,
        resolutions: tuple = ((1024, 120, 600), (2048, 240, 1200), (512, 50, 240)),
        use_spectral_norm: bool = False,
    ):
        super().__init__()
        self.discriminators = nn.ModuleList(
            [DiscriminatorR(r, use_spectral_norm) for r in resolutions]
        )

    def forward(self, y, y_hat):
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = [], [], [], []
        # Batch-concat: same equivalence argument as MultiPeriodDiscriminator
        # (stft/conv/leaky_relu/pad are all batch-independent).
        b = y.shape[0]
        x = torch.cat([y, y_hat], dim=0)
        for d in self.discriminators:
            y_d, fmap = d(x)
            y_d_rs.append(y_d[:b])
            y_d_gs.append(y_d[b:])
            fmap_rs.append([f[:b] for f in fmap])
            fmap_gs.append([f[b:] for f in fmap])
        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class WavLMDiscriminator(torch.nn.Module):
    """
    WavLM-based perceptual discriminator for improved audio quality.

    Uses pre-trained WavLM model to extract speech representations and
    discriminate between real and generated audio based on perceptual features.

    Parameters
    ----------
    model_name : str
        HuggingFace model name for WavLM. Default: "microsoft/wavlm-base-plus"
    use_layers : list[int]
        Which hidden layers to extract features from. Default: [6, 9, 12]
    freeze_feature_extractor : bool
        Whether to freeze the CNN feature extractor. Default: True
    target_sample_rate : int
        WavLM expected sample rate. Default: 16000
    source_sample_rate : int
        Input audio sample rate (Piper uses 22050). Default: 22050
    """

    def __init__(
        self,
        model_name: str = "microsoft/wavlm-base-plus",
        use_layers: list[int] | None = None,
        freeze_feature_extractor: bool = True,
        target_sample_rate: int = 16000,
        source_sample_rate: int = 22050,
    ):
        super().__init__()
        import torchaudio  # noqa: PLC0415 - lazy import

        try:
            from transformers import WavLMModel  # noqa: PLC0415, I001
        except ImportError as exc:
            raise ImportError(
                "The 'transformers' package is required to use WavLMDiscriminator. "
                "Install it with: pip install transformers"
            ) from exc

        self.use_layers = use_layers if use_layers is not None else [6, 9, 12]
        self.target_sample_rate = target_sample_rate
        self.source_sample_rate = source_sample_rate
        self.hidden_size = 768  # WavLM base hidden size

        # Let transformers pick whichever weight file the configured model ships
        # (microsoft/wavlm-base-plus has only pytorch_model.bin; custom models may
        # ship safetensors). Previously hard-coded use_safetensors=True broke the
        # default model.
        self.wavlm = WavLMModel.from_pretrained(model_name)

        # Enable gradient checkpointing for memory efficiency
        self.wavlm.gradient_checkpointing_enable()

        # Freeze feature extractor (CNN layers)
        if freeze_feature_extractor:
            for param in self.wavlm.feature_extractor.parameters():
                param.requires_grad = False

        # Initialize resampler with sinc interpolation for high-quality audio resampling
        # This avoids aliasing artifacts that occur with linear interpolation
        self.resampler = None
        if source_sample_rate != target_sample_rate:
            self.resampler = torchaudio.transforms.Resample(
                orig_freq=source_sample_rate,
                new_freq=target_sample_rate,
                resampling_method="sinc_interp_hann",
                lowpass_filter_width=64,
                dtype=torch.float32,
            )

        # Classification head: concatenated features -> discrimination score
        feature_dim = self.hidden_size * len(self.use_layers)
        self.classifier = nn.Sequential(
            nn.Linear(feature_dim, 256),
            nn.LeakyReLU(0.1),
            nn.Linear(256, 1),
        )

    def _resample(self, audio: torch.Tensor) -> torch.Tensor:
        """Resample audio from source to target sample rate using sinc interpolation.

        Uses torchaudio.transforms.Resample with sinc_interp_hann method for
        high-quality resampling that avoids aliasing artifacts.
        """
        if self.resampler is None:
            # No resampling needed (same sample rate)
            return audio.squeeze(1)

        # audio shape: (batch, 1, time) -> (batch, time) for resampling
        audio_2d = audio.squeeze(1)

        # Convert to float32 for resampling (resampler expects float32)
        audio_float = audio_2d.float()

        # Apply sinc interpolation resampling
        resampled = self.resampler(audio_float)

        return resampled  # (batch, time)

    def _extract_features(
        self, audio: torch.Tensor
    ) -> tuple[torch.Tensor, list[torch.Tensor]]:
        """
        Extract features from WavLM for given audio.

        Parameters
        ----------
        audio : torch.Tensor
            Audio tensor of shape (batch, 1, time) at source_sample_rate

        Returns
        -------
        output : torch.Tensor
            Discrimination score of shape (batch, 1)
        fmap : list[torch.Tensor]
            Feature maps from selected layers, each with shape (batch, hidden_size, seq_len)
            This format is compatible with feature_loss() which expects (batch, channels, time)
        """
        # Resample to 16kHz for WavLM
        audio_16k = self._resample(audio)

        # WavLM requires float32 input (doesn't support FP16)
        # Convert from FP16 to FP32 for mixed precision training compatibility
        audio_16k = audio_16k.float()

        # WavLM forward pass with hidden states
        outputs = self.wavlm(
            audio_16k,
            output_hidden_states=True,
            return_dict=True,
        )

        # Extract features from specified layers
        # hidden_states is tuple of (embedding + num_layers) tensors
        # Each tensor shape: (batch, seq_len, hidden_size)
        hidden_states = outputs.hidden_states

        # Format feature maps for compatibility with feature_loss()
        # Transform from (batch, seq_len, hidden_size) to (batch, hidden_size, seq_len)
        # This matches the format used by MultiPeriodDiscriminator: (batch, channels, time)
        fmap = []
        for i in self.use_layers:
            # Transpose to (batch, hidden_size, seq_len) for feature_loss compatibility
            fmap.append(hidden_states[i].transpose(1, 2))

        # For classification, concatenate and pool
        # Use original format for concatenation: (batch, seq_len, hidden_size * num_layers)
        concat_features = torch.cat([hidden_states[i] for i in self.use_layers], dim=-1)

        # Global average pooling over time for classification
        # Shape: (batch, hidden_size * num_layers)
        pooled = concat_features.mean(dim=1)

        # Classification
        output = self.classifier(pooled)

        return output, fmap

    def forward(
        self, y: torch.Tensor, y_hat: torch.Tensor
    ) -> tuple[
        list[torch.Tensor],
        list[torch.Tensor],
        list[list[torch.Tensor]],
        list[list[torch.Tensor]],
    ]:
        """
        Forward pass for discriminator.

        Parameters
        ----------
        y : torch.Tensor
            Real audio of shape (batch, 1, time)
        y_hat : torch.Tensor
            Generated audio of shape (batch, 1, time)

        Returns
        -------
        y_d_rs : list[torch.Tensor]
            Discrimination scores for real audio
        y_d_gs : list[torch.Tensor]
            Discrimination scores for generated audio
        fmap_rs : list[list[torch.Tensor]]
            Feature maps for real audio
        fmap_gs : list[list[torch.Tensor]]
            Feature maps for generated audio
        """
        y_d_r, fmap_r = self._extract_features(y)
        y_d_g, fmap_g = self._extract_features(y_hat)

        # Return in same format as MultiPeriodDiscriminator
        # Wrap in lists to match expected interface
        return [y_d_r], [y_d_g], [fmap_r], [fmap_g]


class SynthesizerOutput(NamedTuple):
    waveform: torch.Tensor
    duration_loss: torch.Tensor
    attention: torch.Tensor
    ids_slice: torch.Tensor
    x_mask: torch.Tensor
    y_mask: torch.Tensor
    latents: tuple
    decoder_subbands: "torch.Tensor | None"
    # v10 M1 (SNAC flow): flow forward の per-sample logdet [b]。
    # snac off の forward では None。末尾 default None なので既存の
    # positional 構築 (8 引数) を壊さない。
    flow_logdet: "torch.Tensor | None" = None


class SynthesizerTrn(nn.Module):
    """
    Synthesizer for Training

    Parameters
    ----------
    prosody_dim : int, optional
        Dimension for prosody feature projection. If > 0, enables prosody-aware
        duration prediction using A1/A2/A3 values from OpenJTalk labels.
        Default is 16 (prosody-aware enabled; pass 0 to disable for legacy
        backward compatibility).
    """

    def __init__(
        self,
        n_vocab: int,
        spec_channels: int,
        segment_size: int,
        inter_channels: int,
        hidden_channels: int,
        filter_channels: int,
        n_heads: int,
        n_layers: int,
        kernel_size: int,
        p_dropout: float,
        resblock: str,
        resblock_kernel_sizes: tuple[int, ...],
        resblock_dilation_sizes: tuple[tuple[int, ...], ...],
        upsample_rates: tuple[int, ...],
        upsample_initial_channel: int,
        upsample_kernel_sizes: tuple[int, ...],
        n_speakers: int = 1,
        n_languages: int = 1,
        gin_channels: int = 0,
        use_sdp: bool = True,
        prosody_dim: int = 16,
        prosody_language_ids: "set[int] | None" = None,
        # Accepted for backward compat but unused (spk_proj is always used for n_speakers > 1)
        use_zero_shot: bool = True,
        spk_embed_dim: int = 192,
        # T3: TextEncoder self-attention → F.scaled_dot_product_attention.
        # Opt-in perf switch (default False = manual path, regression zero).
        attn_drop_rel_v: bool = False,
        # T1 拡張: MBiSTFTGenerator にも channels_last plumbing を通す (opt-in、
        # default OFF)。 現 Generator は Conv1d のみなので実質 no-op だが、
        # (a) VitsModel の同一 hparam を D と G の両方に propagate する対称性、
        # (b) 将来 Conv2d を Generator に導入した時の future-proofing、 の 2 目的。
        use_channels_last: bool = False,
        # --- v10 構造介入 (default は全て v9 と bit 互換。design doc §4) ---
        # M2: enc_p の話者注入位置 (0 = 後段一括加算、N>=1 = 第 N 層入口)
        speaker_cond_layer: int = 0,
        # M3: DP へ spk_proj_dp 残差ヘッド経由で duration 勾配を通す
        dp_spk_head: bool = False,
        # M1+E2: flow coupling の SNAC 化 (SN/SDN は話者成分のみ、
        # WN の gin 条件付けは lang 成分のみ)
        use_snac_flow: bool = False,
        # E1: dec FiLM (cond_layers) の zero-init を N(0, std) に置換
        # (0.0 = 従来の zero-init)
        film_init_std: float = 0.0,
    ):
        super().__init__()
        self.n_vocab = n_vocab
        self.spec_channels = spec_channels
        self.inter_channels = inter_channels
        self.hidden_channels = hidden_channels
        self.filter_channels = filter_channels
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.resblock = resblock
        self.resblock_kernel_sizes = resblock_kernel_sizes
        self.resblock_dilation_sizes = resblock_dilation_sizes
        self.upsample_rates = upsample_rates
        self.upsample_initial_channel = upsample_initial_channel
        self.upsample_kernel_sizes = upsample_kernel_sizes
        self.segment_size = segment_size
        self.n_speakers = n_speakers
        self.n_languages = n_languages
        self.gin_channels = gin_channels
        self.prosody_dim = prosody_dim
        # Language IDs with real prosody features (others are zeroed).
        # Default: {0} (JA only). Configurable via prosody_language_ids param.
        self.prosody_language_ids: set[int] = (
            prosody_language_ids if prosody_language_ids is not None else {0}
        )

        self.use_sdp = use_sdp
        self.onnx_export_mode = False
        self.use_snac_flow = use_snac_flow

        self.enc_p = TextEncoder(
            n_vocab,
            inter_channels,
            hidden_channels,
            filter_channels,
            n_heads,
            n_layers,
            kernel_size,
            p_dropout,
            gin_channels=gin_channels,
            attn_drop_rel_v=attn_drop_rel_v,
            speaker_cond_layer=speaker_cond_layer,
        )
        self.dec = MBiSTFTGenerator(
            initial_channel=inter_channels,
            resblock=resblock,
            resblock_kernel_sizes=resblock_kernel_sizes,
            resblock_dilation_sizes=resblock_dilation_sizes,
            upsample_rates=upsample_rates,
            upsample_initial_channel=upsample_initial_channel,
            upsample_kernel_sizes=upsample_kernel_sizes,
            gin_channels=gin_channels,
            use_channels_last=use_channels_last,
            film_init_std=film_init_std,
        )
        self.enc_q = PosteriorEncoder(
            spec_channels,
            inter_channels,
            hidden_channels,
            5,
            1,
            16,
            gin_channels=gin_channels,
        )
        self.flow = ResidualCouplingBlock(
            inter_channels,
            hidden_channels,
            5,
            2,
            4,
            gin_channels=gin_channels,
            use_snac=use_snac_flow,
        )

        # Prosody feature projection (A1/A2/A3 → prosody_dim)
        if prosody_dim > 0:
            self.prosody_proj = nn.Linear(3, prosody_dim)
            dp_in_channels = hidden_channels + prosody_dim
        else:
            self.prosody_proj = None
            dp_in_channels = hidden_channels

        if use_sdp:
            self.dp = StochasticDurationPredictor(
                dp_in_channels,
                192,
                3,
                0.5,
                4,
                gin_channels=gin_channels,
                detach_g=not dp_spk_head,
            )
        else:
            self.dp = DurationPredictor(
                dp_in_channels,
                256,
                3,
                0.5,
                gin_channels=gin_channels,
                detach_g=not dp_spk_head,
            )

        # v10 M3 (--dp-spk-head): duration 勾配の受け皿となる軽量残差ヘッド。
        # DP へは g_dp = g.detach() + spk_proj_dp(g.detach()) を渡す
        # (_get_dp_conditioning) — spk_proj 本体 / enc_p は duration 勾配から
        # 保護され、圧力は本ヘッドに集約される (F4 + StyleTTS 2)。
        # default off では作らない (v9 ckpt strict load 互換)。
        if dp_spk_head:
            if gin_channels == 0:
                raise ValueError("dp_spk_head=True requires gin_channels > 0")
            self.spk_proj_dp = nn.Sequential(
                nn.Linear(gin_channels, gin_channels // 4),
                nn.GELU(),
                nn.Linear(gin_channels // 4, gin_channels),
            )
            for module in self.spk_proj_dp:
                if isinstance(module, nn.Linear):
                    # 新設ヘッドは --film-init-std と無関係に無条件 N(0, 1e-3)
                    nn.init.normal_(module.weight, 0.0, 1e-3)
                    nn.init.zeros_(module.bias)

        # Speaker projection MLP for zero-shot speaker conditioning.
        # Replaces emb_g (nn.Embedding) -- all speaker conditioning now goes
        # through spk_proj, eliminating the dual-mode mismatch between
        # emb_g (used for speaker-ID training) and spk_proj (used at inference).
        if n_speakers > 1:
            self.spk_proj = nn.Sequential(
                nn.Linear(192, gin_channels),
                nn.LayerNorm(gin_channels),
                nn.GELU(),
                nn.Linear(gin_channels, gin_channels),
            )

        if n_languages > 1:
            self.emb_lang = nn.Embedding(n_languages, gin_channels)

    def _get_speaker_condition(self, speaker_embeddings=None):
        """Project speaker embeddings through spk_proj MLP.

        Parameters
        ----------
        speaker_embeddings : torch.Tensor or None
            Raw speaker embeddings from CAM++ [batch, 192]

        Returns
        -------
        torch.Tensor or None
            Projected speaker conditioning [batch, gin_channels, 1]
        """
        if speaker_embeddings is None:
            return None
        if not hasattr(self, "spk_proj"):
            return None
        # spk_proj: Linear(192, gin_channels) -> LayerNorm -> GELU -> Linear(gin_channels, gin_channels)
        g = self.spk_proj(speaker_embeddings)  # [b, gin_channels]
        return g.unsqueeze(-1)  # [b, gin_channels, 1]

    def _get_global_conditioning(
        self, sid=None, lid=None, speaker_embeddings=None, return_components=False
    ):
        """Compute global conditioning vector from speaker and language embeddings.

        For multi-speaker models, speaker conditioning is always provided via
        speaker_embeddings (192-dim CAM++ vectors) projected through spk_proj.
        The sid argument is accepted for ONNX signature compatibility but is
        not used internally.

        Parameters
        ----------
        sid : torch.LongTensor or None
            Speaker IDs [batch]. Accepted for API/ONNX compatibility but
            not used -- all speaker conditioning goes through spk_proj.
        lid : torch.LongTensor or None
            Language IDs [batch]
        speaker_embeddings : torch.Tensor or None
            Raw speaker embeddings from CAM++ [batch, 192].
            Required for multi-speaker models.
        return_components : bool
            v10 E2: True で ``(g_combined, g_spk, g_lang)`` の 3-tuple を返す。
            g_spk は話者成分のみ (spk_proj 由来、lid 不感応)、g_lang は言語
            成分のみ (emb_lang 由来、emb 不感応。``n_languages == 1`` または
            lid 未指定なら None)。SNAC flow の SN/SDN 統計 (話者のみ) と WN
            条件付け (lang のみ) の分離に使う。default False は従来どおり
            単一 tensor (既存呼び出しの互換維持)。

        Returns
        -------
        torch.Tensor or None
            Global conditioning [batch, gin_channels, 1]
            (return_components=True 時は上記 3-tuple)
        """
        g_spk = self._get_speaker_condition(speaker_embeddings)
        g_lang = None
        if self.n_languages > 1 and lid is not None:
            # Defend against the lid=-1 mixed-language sentinel used in
            # lightning.py:358-401. Direct model.forward() callers that
            # bypass that normalization would otherwise crash inside
            # nn.Embedding with IndexError. Clamp negative ids to 0 so
            # the embedding lookup succeeds; downstream callers that need
            # true "no language" conditioning should pass lid=None.
            safe_lid = torch.where(lid < 0, torch.zeros_like(lid), lid)
            g_lang = self.emb_lang(safe_lid).unsqueeze(-1)  # [b, h, 1]
        if g_lang is not None:
            g = (g_spk + g_lang) if g_spk is not None else g_lang
        else:
            g = g_spk
        if return_components:
            return g, g_spk, g_lang
        return g

    def _get_dp_conditioning(self, g):
        """v10 M3: DP へ渡す条件付けを作る。

        dp_spk_head 無効時は g をそのまま返す (DP 側の detach_g=True が従来
        どおり勾配を遮断 = v9 bit 互換)。有効時は g を detach した上で
        spk_proj_dp 残差を加算する — duration loss の勾配は spk_proj_dp のみ
        に流れ、spk_proj 本体 / enc_p は保護される。
        """
        if g is None or not hasattr(self, "spk_proj_dp"):
            return g
        g_det = g.detach()  # spk_proj 本体を duration 勾配から保護
        # [b, gin, 1] -> [b, 1, gin] -> MLP -> [b, 1, gin] -> [b, gin, 1]
        delta = self.spk_proj_dp(g_det.transpose(1, 2)).transpose(1, 2)
        return g_det + delta

    def _prepare_prosody_input(self, x, x_mask, prosody_features, lid=None):
        """Prepare encoder output with prosody features for duration predictor.

        Parameters
        ----------
        x : torch.Tensor
            Encoder output [batch, hidden_channels, time]
        x_mask : torch.Tensor
            Mask [batch, 1, time]
        prosody_features : torch.Tensor or None
            Prosody features [batch, time, 3] containing A1/A2/A3 values
        lid : torch.LongTensor or None
            Language IDs [batch]. EN (lid=1) prosody is zeroed out since
            EN prosody_features are all dummy values (a1=0).

        Returns
        -------
        torch.Tensor
            Input for duration predictor, with prosody features concatenated
            if prosody_dim > 0.
        """
        if self.prosody_dim > 0:
            if prosody_features is not None:
                # prosody_features: [batch, time, 3] → [batch, prosody_dim, time]
                prosody_f = prosody_features.float()
                # Zero prosody features for languages without prosody data.
                # Only languages in prosody_language_ids have real prosody values;
                # others (e.g., EN, ES, FR) use dummy values that should be zeroed.
                if lid is not None and self.n_languages > 1:
                    # prosody_language_ids: set of language IDs with real prosody
                    # Default: {0} (JA only) — same as previous `lid == 1` check
                    prosody_langs = getattr(self, "prosody_language_ids", {0})
                    # Build mask: 1.0 for languages WITH prosody, 0.0 for others
                    has_prosody = (
                        sum((lid == lang_id).float() for lang_id in prosody_langs)
                        .clamp(max=1.0)
                        .view(-1, 1, 1)
                    )
                    prosody_f = prosody_f * has_prosody
                prosody_proj = self.prosody_proj(prosody_f)
                prosody_proj = prosody_proj.transpose(1, 2)
            else:
                # No prosody features provided - use zeros for backward compat
                prosody_proj = torch.zeros(
                    x.size(0),
                    self.prosody_dim,
                    x.size(2),
                    device=x.device,
                    dtype=x.dtype,
                )
            # Concatenate with encoder output
            x_dp = torch.cat([x, prosody_proj * x_mask], dim=1)
        else:
            x_dp = x
        return x_dp

    def forward(
        self,
        x,
        x_lengths,
        y,
        y_lengths,
        sid=None,
        lid=None,
        prosody_features=None,
        speaker_embeddings=None,
    ):
        g, g_spk, g_lang = self._get_global_conditioning(
            sid, lid, speaker_embeddings=speaker_embeddings, return_components=True
        )
        x, m_p, logs_p, x_mask = self.enc_p(x, x_lengths, g=g)
        # Safety clamp on log-variance to prevent exp() overflow.
        # logs_p is fed into `exp(-2 * logs_p)` for both MAS (below) and the
        # KL loss (losses.kl_loss). At scratch init the TextEncoder projection
        # can produce logs_p ~ -30, making exp(60) ~ 1e26 and downstream
        # `((z_p - m_p) ** 2) * exp(-2*logs_p)` overflow to inf — resulting in
        # 100% NaN skip through the whole warm-up (observed 2026-07-09 on the
        # v8 A100 SXM4 scratch run). VITS practice: |logs_p| < 5 after
        # convergence; clamp at [-15, 15] gives 5+ orders of magnitude margin
        # in fp32 (exp(30) = 1.07e13 vs fp32 max 3.4e38). Applied at source
        # so MAS / KL / inference paths all see the clamped value. No effect
        # once the model converges into the normal range.
        logs_p = logs_p.clamp(min=-8.0, max=8.0)

        z, m_q, logs_q, y_mask = self.enc_q(y, y_lengths, g=g)
        logs_q = logs_q.clamp(min=-8.0, max=8.0)
        if self.use_snac_flow:
            # v10 M1+E2: SN/SDN 統計は話者成分のみ、WN 条件付けは lang 成分
            # のみ (n_languages == 1 なら None)。logdet は KL 配線用に返す。
            z_p, flow_logdet = self.flow(z, y_mask, g=g_lang, g_spk=g_spk)
        else:
            z_p = self.flow(z, y_mask, g=g)
            flow_logdet = None

        with torch.no_grad():
            # negative cross-entropy
            s_p_sq_r = torch.exp(-2 * logs_p)  # [b, d, t]
            neg_cent1 = torch.sum(
                -0.5 * math.log(2 * math.pi) - logs_p, [1], keepdim=True
            )  # [b, 1, t_s]
            neg_cent2 = torch.matmul(
                -0.5 * (z_p**2).transpose(1, 2), s_p_sq_r
            )  # [b, t_t, d] x [b, d, t_s] = [b, t_t, t_s]
            neg_cent3 = torch.matmul(
                z_p.transpose(1, 2), (m_p * s_p_sq_r)
            )  # [b, t_t, d] x [b, d, t_s] = [b, t_t, t_s]
            neg_cent4 = torch.sum(
                -0.5 * (m_p**2) * s_p_sq_r, [1], keepdim=True
            )  # [b, 1, t_s]
            neg_cent = neg_cent1 + neg_cent2 + neg_cent3 + neg_cent4

            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = (
                monotonic_align.maximum_path(neg_cent, attn_mask.squeeze(1))
                .unsqueeze(1)
                .detach()
            )

        # Prepare input for duration predictor with prosody features
        x_dp = self._prepare_prosody_input(x, x_mask, prosody_features, lid=lid)

        w = attn.sum(2)
        # v10 M3: dp_spk_head 有効時のみ g_dp = g.detach() + spk_proj_dp(...)
        # (無効時は g のまま = v9 bit 互換)
        g_dp = self._get_dp_conditioning(g)
        if self.use_sdp:
            l_length = self.dp(x_dp, x_mask, w, g=g_dp)
            l_length = l_length / torch.sum(x_mask)
        else:
            logw_ = torch.log(w + 1e-6) * x_mask
            logw = self.dp(x_dp, x_mask, g=g_dp)
            l_length = torch.sum((logw - logw_) ** 2, [1, 2]) / torch.sum(
                x_mask
            )  # for averaging

        # expand prior
        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)
        # Re-clamp after MAS expansion: at scratch init the random-init neg_cent
        # fed to `monotonic_align.maximum_path` can produce an attn whose rows
        # are effectively soft (multi-hot after Super-MAS dispatch or when
        # MAS ties break in favour of stacking several 1s per row). The
        # matmul then amplifies logs_p ~ ±15 → ±500, and
        # ((z_p - m_p) ** 2) * exp(-2*logs_p) blows up in fp32. Re-clamping
        # is safe because in a converged model attn is essentially one-hot
        # and the post-expansion range already lies inside the pre-expansion
        # range. Also re-clamp m_p to prevent (z_p - m_p)**2 from overflowing.
        logs_p = logs_p.clamp(min=-8.0, max=8.0)
        m_p = m_p.clamp(min=-100.0, max=100.0)

        z_slice, ids_slice = commons.rand_slice_segments(
            z, y_lengths, self.segment_size
        )
        o, o_mb = self.dec(z_slice, g=g)
        return SynthesizerOutput(
            waveform=o,
            duration_loss=l_length,
            attention=attn,
            ids_slice=ids_slice,
            x_mask=x_mask,
            y_mask=y_mask,
            latents=(z, z_p, m_p, logs_p, m_q, logs_q),
            decoder_subbands=o_mb,
            flow_logdet=flow_logdet,
        )

    def scl_waveform_detached_z(
        self, z, ids_slice, speaker_embeddings=None, sid=None, lid=None
    ):
        """SCL 専用の decoder re-forward (v10 roadmap B-3)。

        posterior z を detach してから decoder を通すため、この波形で計算した
        SCL の勾配は g (spk_proj / emb_lang) と decoder のみに流れ、enc_q
        (posterior) には流れない — 「decoder が GT 由来の z から音色を読んで
        SCL を満たす」posterior leak 経路を遮断する。forward と同じ ids_slice
        を渡すことで主経路の y_hat と同一区間の波形を返す。

        Parameters
        ----------
        z : torch.Tensor
            posterior latent [B, inter_channels, T_frames]
            (``forward`` の ``latents[0]``)
        ids_slice : torch.Tensor
            ``forward`` が返した slice 開始 index (frame 単位)
        speaker_embeddings / sid / lid
            ``forward`` に渡したものと同じ条件付け入力

        Returns
        -------
        torch.Tensor
            waveform [B, 1, segment_samples] (``forward`` の waveform と同形状)
        """
        z_slice = commons.slice_segments(z, ids_slice, self.segment_size).detach()
        g = self._get_global_conditioning(
            sid, lid, speaker_embeddings=speaker_embeddings
        )
        o, _ = self.dec(z_slice, g=g)
        return o

    def swap_scl_waveform(
        self, z_p, y_mask, ids_slice, speaker_embeddings=None, sid=None, lid=None
    ):
        """swap-SCL 用の flow 逆走 + decoder forward (v10 S1、ASCL 型)。

        forward が返した z_p (話者 s の統計で非依存化済み latent) を別話者 q の
        条件付け g_q で flow⁻¹ に通し、decoder で波形化する::

            z_swap = flow⁻¹(z_p.detach(), g_q)
            y_swap = dec(slice(z_swap), g_q)

        z_p は **method 内部で detach** する (ASCL の stop-gradient 契約 —
        呼び出し側の detach に依存させない)。勾配は flow (reverse 経路の
        パラメータ) / decoder FiLM / spk_proj (g_q) に届き、enc_q (posterior) /
        enc_p には届かない。z の中身は話者 s 由来なので decoder は z から
        目標話者 q の音色を読めず、same-utt Goodhart が経路的に不可能
        (design doc §3.1 / F2)。

        Parameters
        ----------
        z_p : torch.Tensor
            flow forward 出力 [B, inter_channels, T_frames]
            (``forward`` の ``latents[1]``)
        y_mask : torch.Tensor
            frame mask [B, 1, T_frames] (``forward`` の ``y_mask``)
        ids_slice : torch.Tensor
            ``forward`` が返した slice 開始 index (frame 単位)
        speaker_embeddings / sid / lid
            swap 先話者 q の条件付け入力 (lid はテキストの言語のまま —
            変えるのは話者のみ)

        Returns
        -------
        torch.Tensor
            waveform [B, 1, segment_samples] (``forward`` の waveform と同形状)
        """
        z_p = z_p.detach()  # ASCL stop-gradient: enc_q / enc_p / 順方向 flow を遮断
        g, g_spk, g_lang = self._get_global_conditioning(
            sid, lid, speaker_embeddings=speaker_embeddings, return_components=True
        )
        if self.use_snac_flow:
            # v10 M1+E2: reverse でも SN/SDN 統計は話者成分のみ、WN は lang のみ
            z_swap = self.flow(z_p, y_mask, g=g_lang, g_spk=g_spk, reverse=True)
        else:
            z_swap = self.flow(z_p, y_mask, g=g, reverse=True)
        z_slice = commons.slice_segments(z_swap * y_mask, ids_slice, self.segment_size)
        o, _ = self.dec(z_slice, g=g)
        return o

    def infer(
        self,
        x,
        x_lengths,
        sid=None,
        lid=None,
        noise_scale=0.4,
        length_scale=1,
        noise_scale_w=0.5,
        max_len=None,
        prosody_features=None,
        speaker_embeddings=None,
    ) -> "InferOutput":
        """Run inference to synthesize audio from phoneme IDs.

        Returns:
            InferOutput: a 5-element NamedTuple of
                (audio, attn, y_mask, latents, durations) where *latents*
                is itself a tuple ``(z, z_p, m_p, logs_p)``.

        .. versionchanged:: 2026.03
            Return value changed from a plain 4-tuple to a 5-element
            ``InferOutput`` NamedTuple (added *durations*).  Existing
            callers using ``audio, *_ =`` or ``[0]`` indexing are
            unaffected.
        """
        if self.n_speakers > 1:
            assert speaker_embeddings is not None, (
                "Missing speaker_embeddings. "
                "Provide 192-dim CAM++ embeddings for multi-speaker inference."
            )
        if speaker_embeddings is not None and speaker_embeddings.shape[-1] != 192:
            raise ValueError(
                f"speaker_embeddings dim must be 192, got {speaker_embeddings.shape[-1]}"
            )
        g, g_spk, g_lang = self._get_global_conditioning(
            sid, lid, speaker_embeddings=speaker_embeddings, return_components=True
        )
        x, m_p, logs_p, x_mask = self.enc_p(x, x_lengths, g=g)
        # Match the training-time clamp for consistency between train and
        # inference. See models.py training forward for the rationale.
        logs_p = logs_p.clamp(min=-8.0, max=8.0)

        # Prepare input for duration predictor with prosody features
        x_dp = self._prepare_prosody_input(x, x_mask, prosody_features, lid=lid)

        # v10 M3: 学習と同じ DP 条件付け (dp_spk_head 有効時のみ残差ヘッド加算)
        g_dp = self._get_dp_conditioning(g)
        if self.use_sdp:
            logw = self.dp(
                x_dp, x_mask, g=g_dp, reverse=True, noise_scale=noise_scale_w
            )
        else:
            logw = self.dp(x_dp, x_mask, g=g_dp)
        w = torch.exp(logw) * x_mask * length_scale
        durations = w.squeeze(1)

        w_ceil = torch.ceil(w)
        y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
        y_mask = torch.unsqueeze(
            commons.sequence_mask(y_lengths, y_lengths.max()), 1
        ).type_as(x_mask)
        attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
        attn = commons.generate_path(w_ceil, attn_mask)

        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(
            1, 2
        )  # [b, t', t], [b, t, d] -> [b, d, t']
        logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(
            1, 2
        )  # [b, t', t], [b, t, d] -> [b, d, t']
        # Match the training-time post-MAS clamp (see forward()) so ONNX
        # inference produces the same numerical range as training. In
        # inference w_ceil is always integer and attn is truly one-hot so
        # this is a no-op after convergence.
        logs_p = logs_p.clamp(min=-8.0, max=8.0)
        m_p = m_p.clamp(min=-100.0, max=100.0)

        # Use mean only for deterministic ONNX export
        if getattr(self, "onnx_export_mode", False):
            z_p = m_p
        else:
            z_p = m_p + torch.randn_like(m_p) * torch.exp(logs_p) * noise_scale
        if self.use_snac_flow:
            # v10 M1+E2: reverse でも学習と同じ分離 (SDN=話者、WN=lang)
            z = self.flow(z_p, y_mask, g=g_lang, g_spk=g_spk, reverse=True)
        else:
            z = self.flow(z_p, y_mask, g=g, reverse=True)
        dec_out = self.dec((z * y_mask)[:, :, :max_len], g=g)
        # Decoder returns (fullband, subbands) in training mode but only
        # fullband in onnx_export_mode. Extract fullband in both cases.
        o = dec_out[0] if isinstance(dec_out, tuple) else dec_out

        return InferOutput(o, attn, y_mask, (z, z_p, m_p, logs_p), durations)

    def voice_conversion(
        self,
        y,
        y_lengths,
        sid_src=None,
        sid_tgt=None,
        lid=None,
        speaker_embeddings_src=None,
        speaker_embeddings_tgt=None,
    ):
        assert self.n_speakers > 1, "n_speakers have to be larger than 1."
        g_src, g_spk_src, g_lang = self._get_global_conditioning(
            sid_src,
            lid,
            speaker_embeddings=speaker_embeddings_src,
            return_components=True,
        )
        g_tgt, g_spk_tgt, _ = self._get_global_conditioning(
            sid_tgt,
            lid,
            speaker_embeddings=speaker_embeddings_tgt,
            return_components=True,
        )
        z, _m_q, _logs_q, y_mask = self.enc_q(y, y_lengths, g=g_src)
        if self.use_snac_flow:
            # v10 M1+E2: SN で src 話者統計を除去 → SDN で tgt 話者統計を注入
            z_p, _logdet = self.flow(z, y_mask, g=g_lang, g_spk=g_spk_src)
            z_hat = self.flow(z_p, y_mask, g=g_lang, g_spk=g_spk_tgt, reverse=True)
        else:
            z_p = self.flow(z, y_mask, g=g_src)
            z_hat = self.flow(z_p, y_mask, g=g_tgt, reverse=True)
        o_hat, _ = self.dec(z_hat * y_mask, g=g_tgt)
        return o_hat, y_mask, (z, z_p, z_hat)
