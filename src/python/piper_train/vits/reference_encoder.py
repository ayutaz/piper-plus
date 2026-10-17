"""参照スペクトログラム encoder (F-mel) と容量対照 (Ccap)。

docs/design/zero-shot-reference-fusion-plan-2026-10-17.md §8.2:

* :class:`ReferenceSpecEncoder` — 参照発話の線形振幅スペクトログラム
  (``spectrogram_torch`` 出力、``[B, filter_length // 2 + 1, T]``) を読み、
  ``[B, gin, 1]`` の話者条件の加算項を作る (GPT-SoVITS MelStyleEncoder 型)。
* :class:`CapacityControl` — 192 次元 CAM++ 埋め込みの MLP。参照 spec を
  読まずに同じ追加パラメータ数を与える対照。

どちらも最終 Linear を weight・bias とも zero-init にするので、
``SynthesizerTrn`` に組み込んだ初期状態の出力は旧モデルと bit 一致する。
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from ..reference_frontend import masked_time_mean_fp32


# 線形振幅の log 圧縮の下限 (``log(clamp(x, 1e-5))``、HiFi-GAN 系の慣例)
_LOG_FLOOR = 1e-5


def _zero_linear(in_features: int, out_features: int) -> nn.Linear:
    layer = nn.Linear(in_features, out_features)
    nn.init.zeros_(layer.weight)
    nn.init.zeros_(layer.bias)
    return layer


class _Conv1dGLU(nn.Module):
    """mask 付き残差 Conv1d + GLU (MelStyleEncoder の temporal block)。

    畳み込みの前に padding frame を 0 にするので、有効 frame の出力は
    padding の長さ・中身に依存しない (Conv の zero padding と同じ扱い)。
    """

    def __init__(self, channels: int, kernel_size: int):
        super().__init__()
        self.conv = nn.Conv1d(
            channels, 2 * channels, kernel_size, padding=kernel_size // 2
        )

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = F.glu(self.conv(x * mask), dim=1)
        return (x + h) * mask


class _MaskedSelfAttention(nn.Module):
    """key padding mask 付き multi-head self-attention (残差)。"""

    def __init__(self, channels: int, n_heads: int):
        super().__init__()
        self.n_heads = n_heads
        self.qkv = nn.Linear(channels, 3 * channels)
        self.proj = nn.Linear(channels, channels)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        # x: [B, C, T]、mask: [B, 1, T]
        b, c, t = x.shape
        h = x.transpose(1, 2)  # [B, T, C]
        q, k, v = self.qkv(h).chunk(3, dim=-1)

        def heads(z: torch.Tensor) -> torch.Tensor:
            return z.view(b, t, self.n_heads, c // self.n_heads).transpose(1, 2)

        # True = attend。padding key を除外する ([B, 1, 1, T] で全 query に共通)
        key_mask = mask.bool().unsqueeze(1)
        out = F.scaled_dot_product_attention(
            heads(q), heads(k), heads(v), attn_mask=key_mask
        )
        out = self.proj(out.transpose(1, 2).reshape(b, t, c))
        return (x + out.transpose(1, 2)) * mask


class ReferenceSpecEncoder(nn.Module):
    """参照発話の線形振幅 spec → 話者条件の加算項 ``[B, gin, 1]``。

    log 圧縮 → spectral Linear×2 (Mish) → Conv1dGLU×2 (mask 付き) →
    self-attention (key padding mask) → fp32 masked 時間平均 → zero-init
    Linear。dropout は持たない (出力を決定的にし、mask の検証を厳密にする)。

    Raises (forward):
        TypeError: spec が浮動小数点でない、lengths が int64 でない。
        ValueError: 形状違い、長さが 0 以下または ``T`` 超、非有限値、
            負値 (線形振幅でない = log spec の取り違え)。
    """

    def __init__(
        self,
        spec_channels: int,
        gin_channels: int,
        hidden_channels: int = 128,
        kernel_size: int = 5,
        n_heads: int = 2,
    ):
        super().__init__()
        if spec_channels <= 0:
            raise ValueError(f"spec_channels must be positive, got {spec_channels}")
        if gin_channels <= 0:
            raise ValueError(f"gin_channels must be positive, got {gin_channels}")
        if kernel_size % 2 != 1:
            raise ValueError(
                f"kernel_size must be odd to keep frames aligned, got {kernel_size}"
            )
        if n_heads <= 0 or hidden_channels % n_heads != 0:
            raise ValueError(
                f"hidden_channels ({hidden_channels}) must be divisible by "
                f"n_heads ({n_heads})"
            )
        self.spec_channels = spec_channels
        self.gin_channels = gin_channels
        self.hidden_channels = hidden_channels

        self.spectral = nn.Sequential(
            nn.Linear(spec_channels, hidden_channels),
            nn.Mish(),
            nn.Linear(hidden_channels, hidden_channels),
            nn.Mish(),
        )
        self.temporal = nn.ModuleList(
            [_Conv1dGLU(hidden_channels, kernel_size) for _ in range(2)]
        )
        self.attention = _MaskedSelfAttention(hidden_channels, n_heads)
        self.out = _zero_linear(hidden_channels, gin_channels)

    def _validate(self, spec: torch.Tensor, spec_lengths: torch.Tensor) -> None:
        if not torch.is_floating_point(spec):
            raise TypeError(f"spec must be a floating tensor, got {spec.dtype}")
        if spec.dim() != 3:
            raise ValueError(f"spec must be 3-D [B, F, T], got {tuple(spec.shape)}")
        if spec.shape[1] != self.spec_channels:
            raise ValueError(
                f"spec has {spec.shape[1]} channels, expected {self.spec_channels} "
                "(filter_length // 2 + 1 linear-magnitude bins)"
            )
        if (
            not isinstance(spec_lengths, torch.Tensor)
            or spec_lengths.dtype != torch.long
        ):
            raise TypeError(
                "spec_lengths must be an int64 tensor, got "
                f"{getattr(spec_lengths, 'dtype', type(spec_lengths))}"
            )
        if spec_lengths.dim() != 1 or spec_lengths.shape[0] != spec.shape[0]:
            raise ValueError(
                f"spec_lengths must be 1-D [B={spec.shape[0]}], got "
                f"{tuple(spec_lengths.shape)}"
            )
        if bool((spec_lengths <= 0).any()):
            raise ValueError(
                f"reference length must be >= 1, got {spec_lengths.tolist()}"
            )
        if bool((spec_lengths > spec.shape[-1]).any()):
            raise ValueError(
                f"reference length exceeds spec frames ({spec.shape[-1]}): "
                f"{spec_lengths.tolist()}"
            )
        if not bool(torch.isfinite(spec).all()):
            raise ValueError("spec must be finite (NaN/Inf found)")
        if bool((spec < 0).any()):
            raise ValueError(
                "spec must be a non-negative linear magnitude spectrogram "
                "(negative values found; was a log spectrogram passed?)"
            )

    def forward(self, spec: torch.Tensor, spec_lengths: torch.Tensor) -> torch.Tensor:
        """``spec [B, F, T]`` (線形振幅) と ``spec_lengths [B]`` → ``[B, gin, 1]``。"""
        self._validate(spec, spec_lengths)
        param_dtype = self.out.weight.dtype
        t = spec.shape[-1]
        lengths = spec_lengths.to(spec.device)
        mask = (
            torch.arange(t, device=spec.device)[None, :] < lengths[:, None]
        ).unsqueeze(1)  # [B, 1, T] bool

        # log 圧縮は入力 dtype によらず fp32 で行う (fp16 の 1e-5 は subnormal)
        x = torch.log(torch.clamp(spec.float(), min=_LOG_FLOOR)).to(param_dtype)
        x = self.spectral(x.transpose(1, 2)).transpose(1, 2)  # [B, H, T]
        mask_x = mask.to(x.dtype)
        x = x * mask_x
        for block in self.temporal:
            x = block(x, mask_x)
        x = self.attention(x, mask_x)
        pooled = masked_time_mean_fp32(x, mask)  # [B, H] fp32
        return self.out(pooled.to(param_dtype)).unsqueeze(-1)


def reference_spec_encoder_param_count(
    spec_channels: int, gin_channels: int, **encoder_kwargs
) -> int:
    """同じ設定の :class:`ReferenceSpecEncoder` のパラメータ数 (meta device で数える)。"""
    with torch.device("meta"):
        encoder = ReferenceSpecEncoder(spec_channels, gin_channels, **encoder_kwargs)
    return sum(p.numel() for p in encoder.parameters())


class CapacityControl(nn.Module):
    """容量対照 (Ccap): ``Linear → PReLU → Linear(zero-init)`` を埋め込みに掛ける。

    hidden 幅は追加パラメータ数が ``target_params`` (同じ gin の
    :class:`ReferenceSpecEncoder`) に最も近くなるよう解析的に決める。
    ±5% に入らない (target が小さすぎる) 場合は ``ValueError``。
    """

    def __init__(self, in_dim: int, gin_channels: int, target_params: int):
        super().__init__()
        if in_dim <= 0 or gin_channels <= 0:
            raise ValueError(
                f"in_dim and gin_channels must be positive, got {in_dim}, {gin_channels}"
            )
        # params(h) = in_dim*h + h (Linear1) + 1 (PReLU) + h*gin + gin (Linear2)
        per_hidden = in_dim + 1 + gin_channels
        fixed = 1 + gin_channels
        hidden = max(1, round((target_params - fixed) / per_hidden))
        n_params = per_hidden * hidden + fixed
        if target_params <= 0 or abs(n_params - target_params) > 0.05 * target_params:
            raise ValueError(
                f"target_params={target_params} cannot be matched within 5% "
                f"(closest: hidden={hidden} -> {n_params} params)"
            )
        self.in_dim = in_dim
        self.gin_channels = gin_channels
        self.hidden_channels = hidden
        self.inp = nn.Linear(in_dim, hidden)
        self.act = nn.PReLU()
        self.out = _zero_linear(hidden, gin_channels)

    def forward(self, e: torch.Tensor) -> torch.Tensor:
        """``e [B, in_dim]`` → ``[B, gin, 1]``。"""
        if not torch.is_floating_point(e):
            raise TypeError(f"embedding must be a floating tensor, got {e.dtype}")
        if e.dim() != 2:
            raise ValueError(f"embedding must be 2-D [B, D], got {tuple(e.shape)}")
        if e.shape[1] != self.in_dim:
            raise ValueError(f"embedding dim must be {self.in_dim}, got {e.shape[1]}")
        if not bool(torch.isfinite(e).all()):
            raise ValueError("embedding must be finite (NaN/Inf found)")
        return self.out(self.act(self.inp(e))).unsqueeze(-1)
