import math

import torch
from torch import nn
from torch.nn import Conv1d, functional as F
from torch.nn.utils import remove_weight_norm, weight_norm

from .commons import fused_add_tanh_sigmoid_multiply, get_padding, init_weights
from .transforms import piecewise_rational_quadratic_transform


class LayerNorm(nn.Module):
    def __init__(self, channels: int, eps: float = 1e-5):
        super().__init__()
        self.channels = channels
        self.eps = eps

        self.gamma = nn.Parameter(torch.ones(channels))
        self.beta = nn.Parameter(torch.zeros(channels))

    def forward(self, x):
        x = x.transpose(1, -1)
        x = F.layer_norm(x, (self.channels,), self.gamma, self.beta, self.eps)
        return x.transpose(1, -1)


class ConvReluNorm(nn.Module):
    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        out_channels: int,
        kernel_size: int,
        n_layers: int,
        p_dropout: float,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.hidden_channels = hidden_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.p_dropout = p_dropout
        assert n_layers > 1, "Number of layers should be larger than 0."

        self.conv_layers = nn.ModuleList()
        self.norm_layers = nn.ModuleList()
        self.conv_layers.append(
            nn.Conv1d(
                in_channels, hidden_channels, kernel_size, padding=kernel_size // 2
            )
        )
        self.norm_layers.append(LayerNorm(hidden_channels))
        self.relu_drop = nn.Sequential(nn.ReLU(), nn.Dropout(p_dropout))
        for _ in range(n_layers - 1):
            self.conv_layers.append(
                nn.Conv1d(
                    hidden_channels,
                    hidden_channels,
                    kernel_size,
                    padding=kernel_size // 2,
                )
            )
            self.norm_layers.append(LayerNorm(hidden_channels))
        self.proj = nn.Conv1d(hidden_channels, out_channels, 1)
        self.proj.weight.data.zero_()
        self.proj.bias.data.zero_()

    def forward(self, x, x_mask):
        x_org = x
        for i in range(self.n_layers):
            x = self.conv_layers[i](x * x_mask)
            x = self.norm_layers[i](x)
            x = self.relu_drop(x)
        x = x_org + self.proj(x)
        return x * x_mask


class DDSConv(nn.Module):
    """
    Dialted and Depth-Separable Convolution
    """

    def __init__(
        self, channels: int, kernel_size: int, n_layers: int, p_dropout: float = 0.0
    ):
        super().__init__()
        self.channels = channels
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.p_dropout = p_dropout

        self.drop = nn.Dropout(p_dropout)
        self.convs_sep = nn.ModuleList()
        self.convs_1x1 = nn.ModuleList()
        self.norms_1 = nn.ModuleList()
        self.norms_2 = nn.ModuleList()
        for i in range(n_layers):
            dilation = kernel_size**i
            padding = (kernel_size * dilation - dilation) // 2
            self.convs_sep.append(
                nn.Conv1d(
                    channels,
                    channels,
                    kernel_size,
                    groups=channels,
                    dilation=dilation,
                    padding=padding,
                )
            )
            self.convs_1x1.append(nn.Conv1d(channels, channels, 1))
            self.norms_1.append(LayerNorm(channels))
            self.norms_2.append(LayerNorm(channels))

    def forward(self, x, x_mask, g=None):
        if g is not None:
            x = x + g
        for i in range(self.n_layers):
            y = self.convs_sep[i](x * x_mask)
            y = self.norms_1[i](y)
            y = F.gelu(y)
            y = self.convs_1x1[i](y)
            y = self.norms_2[i](y)
            y = F.gelu(y)
            y = self.drop(y)
            x = x + y
        return x * x_mask


class WN(torch.nn.Module):
    def __init__(
        self,
        hidden_channels: int,
        kernel_size: int,
        dilation_rate: int,
        n_layers: int,
        gin_channels: int = 0,
        p_dropout: float = 0,
    ):
        super().__init__()
        assert kernel_size % 2 == 1
        self.hidden_channels = hidden_channels
        self.kernel_size = (kernel_size,)
        self.dilation_rate = dilation_rate
        self.n_layers = n_layers
        self.gin_channels = gin_channels
        self.p_dropout = p_dropout

        self.in_layers = torch.nn.ModuleList()
        self.res_skip_layers = torch.nn.ModuleList()
        self.drop = nn.Dropout(p_dropout)

        if gin_channels != 0:
            cond_layer = torch.nn.Conv1d(
                gin_channels, 2 * hidden_channels * n_layers, 1
            )
            self.cond_layer = torch.nn.utils.weight_norm(cond_layer, name="weight")

        for i in range(n_layers):
            dilation = dilation_rate**i
            padding = int((kernel_size * dilation - dilation) / 2)
            in_layer = torch.nn.Conv1d(
                hidden_channels,
                2 * hidden_channels,
                kernel_size,
                dilation=dilation,
                padding=padding,
            )
            in_layer = torch.nn.utils.weight_norm(in_layer, name="weight")
            self.in_layers.append(in_layer)

            # last one is not necessary
            if i < n_layers - 1:
                res_skip_channels = 2 * hidden_channels
            else:
                res_skip_channels = hidden_channels

            res_skip_layer = torch.nn.Conv1d(hidden_channels, res_skip_channels, 1)
            res_skip_layer = torch.nn.utils.weight_norm(res_skip_layer, name="weight")
            self.res_skip_layers.append(res_skip_layer)

    def forward(self, x, x_mask, g=None, **kwargs):
        output = torch.zeros_like(x)
        n_channels_tensor = torch.IntTensor([self.hidden_channels])

        if g is not None:
            g = self.cond_layer(g)

        for i in range(self.n_layers):
            x_in = self.in_layers[i](x)
            if g is not None:
                cond_offset = i * 2 * self.hidden_channels
                g_l = g[:, cond_offset : cond_offset + 2 * self.hidden_channels, :]
            else:
                g_l = torch.zeros_like(x_in)

            acts = fused_add_tanh_sigmoid_multiply(x_in, g_l, n_channels_tensor)
            acts = self.drop(acts)

            res_skip_acts = self.res_skip_layers[i](acts)
            if i < self.n_layers - 1:
                res_acts = res_skip_acts[:, : self.hidden_channels, :]
                x = (x + res_acts) * x_mask
                output = output + res_skip_acts[:, self.hidden_channels :, :]
            else:
                output = output + res_skip_acts
        return output * x_mask

    def remove_weight_norm(self):
        if self.gin_channels != 0:
            torch.nn.utils.remove_weight_norm(self.cond_layer)
        for l in self.in_layers:  # noqa: E741
            torch.nn.utils.remove_weight_norm(l)
        for l in self.res_skip_layers:  # noqa: E741
            torch.nn.utils.remove_weight_norm(l)


class ResBlock1(torch.nn.Module):
    def __init__(
        self,
        channels: int,
        kernel_size: int = 3,
        dilation: tuple[int] = (1, 3, 5),
    ):
        super().__init__()
        self.LRELU_SLOPE = 0.1
        self.convs1 = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[0],
                        padding=get_padding(kernel_size, dilation[0]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[1],
                        padding=get_padding(kernel_size, dilation[1]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[2],
                        padding=get_padding(kernel_size, dilation[2]),
                    )
                ),
            ]
        )
        self.convs1.apply(init_weights)

        self.convs2 = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
            ]
        )
        self.convs2.apply(init_weights)

    def forward(self, x, x_mask=None):
        for c1, c2 in zip(self.convs1, self.convs2, strict=False):
            xt = F.leaky_relu(x, self.LRELU_SLOPE)
            if x_mask is not None:
                xt = xt * x_mask
            xt = c1(xt)
            xt = F.leaky_relu(xt, self.LRELU_SLOPE)
            if x_mask is not None:
                xt = xt * x_mask
            xt = c2(xt)
            x = xt + x
        if x_mask is not None:
            x = x * x_mask
        return x

    def remove_weight_norm(self):
        for l in self.convs1:  # noqa: E741
            remove_weight_norm(l)
        for l in self.convs2:  # noqa: E741
            remove_weight_norm(l)


class ResBlock2(torch.nn.Module):
    def __init__(
        self, channels: int, kernel_size: int = 3, dilation: tuple[int] = (1, 3)
    ):
        super().__init__()
        self.LRELU_SLOPE = 0.1
        self.convs = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[0],
                        padding=get_padding(kernel_size, dilation[0]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[1],
                        padding=get_padding(kernel_size, dilation[1]),
                    )
                ),
            ]
        )
        self.convs.apply(init_weights)

    def forward(self, x, x_mask=None):
        for c in self.convs:
            xt = F.leaky_relu(x, self.LRELU_SLOPE)
            if x_mask is not None:
                xt = xt * x_mask
            xt = c(xt)
            x = xt + x
        if x_mask is not None:
            x = x * x_mask
        return x

    def remove_weight_norm(self):
        for l in self.convs:  # noqa: E741
            remove_weight_norm(l)


class Log(nn.Module):
    def forward(
        self, x: torch.Tensor, x_mask: torch.Tensor, reverse: bool = False, **kwargs
    ):
        if not reverse:
            y = torch.log(torch.clamp_min(x, 1e-5)) * x_mask
            logdet = torch.sum(-y, [1, 2])
            return y, logdet
        else:
            x = torch.exp(x) * x_mask
            return x


class Flip(nn.Module):
    def forward(self, x: torch.Tensor, *args, reverse: bool = False, **kwargs):
        x = torch.flip(x, [1])
        if not reverse:
            logdet = torch.zeros(x.size(0)).type_as(x)
            return x, logdet
        else:
            return x


class ElementwiseAffine(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.channels = channels
        self.m = nn.Parameter(torch.zeros(channels, 1))
        self.logs = nn.Parameter(torch.zeros(channels, 1))

    def forward(self, x, x_mask, reverse=False, **kwargs):
        if not reverse:
            y = self.m + torch.exp(self.logs) * x
            y = y * x_mask
            logdet = torch.sum(self.logs * x_mask, [1, 2])
            return y, logdet
        else:
            x = (x - self.m) * torch.exp(-self.logs) * x_mask
            return x


class ResidualCouplingLayer(nn.Module):
    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        dilation_rate: int,
        n_layers: int,
        p_dropout: float = 0,
        gin_channels: int = 0,
        mean_only: bool = False,
        # v10 M1 (SNAC, arXiv:2211.16866): 話者正規化 affine coupling。
        # forward 入口で SN(x1; g_spk) = (x1 - m) * exp(-v)、reverse 出口で
        # SDN(x1; g_spk) = x1 * exp(v) + m を適用する。m, v は
        # sn_linear(g_spk) を chunk (m が先)。E2: 統計は話者成分 g_spk のみ
        # から予測し、WN の g 条件付け (lang 成分) とは分離する。
        # default False は既存経路と bit 互換 (新規パラメータなし = v9 ckpt 互換)。
        use_snac: bool = False,
        # v11 P5 (--no-snac-stats → snac_stats=False): SN/SDN の統計注入のみを
        # 恒等化する。Phase 0 D-3/D-4 で SNAC 統計は LOO −0.017 (無害) かつ
        # isolation で chance = 死荷重と実測されたため、除去で −394k param
        # (conditioning 設計 doc §10.5 P5)。sn_linear を構築しない (= use_snac
        # かつ snac_stats=False のパラメータ集合は plain coupling と同一で v9
        # ckpt が strict load 可能)。flow 構造 (可逆性・logdet の KL 配線) は
        # 不変 — logdet は Σ logs のまま返り続ける。default True = v10b 互換。
        snac_stats: bool = True,
    ):
        assert channels % 2 == 0, "channels should be divisible by 2"
        super().__init__()
        self.channels = channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate
        self.n_layers = n_layers
        self.half_channels = channels // 2
        self.mean_only = mean_only
        self.use_snac = use_snac
        self.snac_stats = snac_stats

        self.pre = nn.Conv1d(self.half_channels, hidden_channels, 1)
        self.enc = WN(
            hidden_channels,
            kernel_size,
            dilation_rate,
            n_layers,
            p_dropout=p_dropout,
            gin_channels=gin_channels,
        )
        self.post = nn.Conv1d(hidden_channels, self.half_channels * (2 - mean_only), 1)
        self.post.weight.data.zero_()
        self.post.bias.data.zero_()

        if use_snac and snac_stats:
            if gin_channels == 0:
                raise ValueError("use_snac=True requires gin_channels > 0")
            self.sn_linear = nn.Conv1d(gin_channels, 2 * self.half_channels, 1)
            # 新設ヘッドは --film-init-std と無関係に無条件で small-Gaussian
            # N(0, 1e-3) init (AdaLN-Zero 分析、v10 design §4 E1)。bias=0 で
            # 学習開始時の SN はほぼ identity。
            nn.init.normal_(self.sn_linear.weight, 0.0, 1e-3)
            nn.init.zeros_(self.sn_linear.bias)

    def forward(self, x, x_mask, g=None, reverse=False, g_spk=None):
        x0, x1 = torch.split(x, [self.half_channels] * 2, 1)
        sn_m = sn_v = None
        # v11 P5: snac_stats=False では sn_linear が存在しない → sn_m/sn_v は
        # None のままで SN/SDN・logdet 補正の全てが自動的に恒等になる
        if self.use_snac and self.snac_stats and g_spk is not None:
            # chunk 順は m が先 (tests/test_v10_structure.py で固定)。
            # v は bf16 の exp overflow 対策で clamp [-4, 4] (v10 design §4 M1)。
            sn_m, sn_v = torch.chunk(self.sn_linear(g_spk), 2, dim=1)
            sn_v = sn_v.clamp(min=-4.0, max=4.0)
        if not reverse and sn_m is not None:
            # SN: 入口で話者統計を除去 (x1 のみ — x0 は coupling の条件側)
            x1 = (x1 - sn_m) * torch.exp(-sn_v) * x_mask
        h = self.pre(x0) * x_mask
        h = self.enc(h, x_mask, g=g)
        stats = self.post(h) * x_mask
        if not self.mean_only:
            m, logs = torch.split(stats, [self.half_channels] * 2, 1)
        else:
            m = stats
            logs = torch.zeros_like(m)

        if not reverse:
            x1 = m + x1 * torch.exp(logs) * x_mask
            x = torch.cat([x0, x1], 1)
            logdet = torch.sum(logs, [1, 2])
            if sn_v is not None:
                # SN の対数行列式: dx1'/dx1 = exp(-v) → logdet -= Σ v (mask 内)
                logdet = logdet - torch.sum(sn_v * x_mask, [1, 2])
            return x, logdet
        else:
            x1 = (x1 - m) * torch.exp(-logs) * x_mask
            if sn_m is not None:
                # SDN: reverse 出口で話者統計を再注入
                x1 = (x1 * torch.exp(sn_v) + sn_m) * x_mask
            x = torch.cat([x0, x1], 1)
            return x


class ConvFlow(nn.Module):
    def __init__(
        self,
        in_channels: int,
        filter_channels: int,
        kernel_size: int,
        n_layers: int,
        num_bins: int = 10,
        tail_bound: float = 5.0,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.filter_channels = filter_channels
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.num_bins = num_bins
        self.tail_bound = tail_bound
        self.half_channels = in_channels // 2

        self.pre = nn.Conv1d(self.half_channels, filter_channels, 1)
        self.convs = DDSConv(filter_channels, kernel_size, n_layers, p_dropout=0.0)
        self.proj = nn.Conv1d(
            filter_channels, self.half_channels * (num_bins * 3 - 1), 1
        )
        self.proj.weight.data.zero_()
        self.proj.bias.data.zero_()

    def forward(self, x, x_mask, g=None, reverse=False):
        x0, x1 = torch.split(x, [self.half_channels] * 2, 1)
        h = self.pre(x0)
        h = self.convs(h, x_mask, g=g)
        h = self.proj(h) * x_mask

        b, c, t = x0.shape
        h = h.reshape(b, c, -1, t).permute(0, 1, 3, 2)  # [b, cx?, t] -> [b, c, t, ?]

        unnormalized_widths = h[..., : self.num_bins] / math.sqrt(self.filter_channels)
        unnormalized_heights = h[..., self.num_bins : 2 * self.num_bins] / math.sqrt(
            self.filter_channels
        )
        unnormalized_derivatives = h[..., 2 * self.num_bins :]

        x1, logabsdet = piecewise_rational_quadratic_transform(
            x1,
            unnormalized_widths,
            unnormalized_heights,
            unnormalized_derivatives,
            inverse=reverse,
            tails="linear",
            tail_bound=self.tail_bound,
        )

        x = torch.cat([x0, x1], 1) * x_mask

        logdet = torch.sum(logabsdet * x_mask, [1, 2])
        if not reverse:
            return x, logdet
        else:
            return x
