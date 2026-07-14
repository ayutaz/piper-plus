"""WaveNeXt v1 decoder (ConvNeXt backbone + trainable linear head, no iSTFT).

Stage 1 of the WaveNeXt decoder ablation
(docs/design/wavenext-decoder-ablation/03-ablation-plan.md).

Attribution:
  (1) Okamoto et al., "WaveNeXt: ConvNeXt-Based Fast Neural Vocoder Without
      ISTFT Layer", IEEE ASRU 2023, DOI 10.1109/ASRU57964.2023.10389765
      (paper reference kept for a future re-sync PR if an official
      implementation is released).
  (2) Vocos, Copyright (c) 2023 Charactr Inc., MIT License
      (ConvNeXt backbone structure).
  (3) wetdog/wavenext_pytorch@d45d544, MIT License
      (WaveNextHead and the clip(-1, 1) output stage are wetdog additions).

BSC-LT/wavenext-mel weights (``--wavenext-init``) are Apache-2.0; keep the
upstream NOTICE when redistributing warm-started checkpoints.
"""

import torch
from torch import nn


# phoneme-timing contract と 4 runtime (WASM/Rust/Go/C#) が hop=256 を
# ハードコードするため pin する。hop≠256 (24kHz / WaveNeXt2) は Stage 3 スコープ。
WAVENEXT_HOP_LENGTH = 256


class ConvNeXtBlock(nn.Module):
    """ConvNeXt block adapted for 1D audio signal (Vocos-style).

    depthwise Conv1d(k=7) → LayerNorm → Linear → GELU → Linear
    → LayerScale (gamma) → residual.
    """

    def __init__(
        self,
        dim: int,
        intermediate_dim: int,
        layer_scale_init_value: float,
        adanorm_num_embeddings: "int | None" = None,
    ):
        super().__init__()
        if adanorm_num_embeddings is not None:
            # wetdog シグネチャ互換の予約引数 (AdaLayerNorm conditioning)
            raise NotImplementedError(
                "adanorm_num_embeddings is reserved for Stage 2 (S2-A) "
                "AdaLayerNorm conditioning"
            )
        self.dwconv = nn.Conv1d(dim, dim, kernel_size=7, padding=3, groups=dim)
        self.norm = nn.LayerNorm(dim, eps=1e-6)
        self.pwconv1 = nn.Linear(dim, intermediate_dim)
        self.act = nn.GELU()
        self.pwconv2 = nn.Linear(intermediate_dim, dim)
        self.gamma = (
            nn.Parameter(layer_scale_init_value * torch.ones(dim))
            if layer_scale_init_value > 0
            else None
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """[B, dim, T] → [B, dim, T]"""
        residual = x
        x = self.dwconv(x)
        x = x.transpose(1, 2)  # (B, T, C)
        x = self.norm(x)
        x = self.pwconv2(self.act(self.pwconv1(x)))
        if self.gamma is not None:
            x = self.gamma * x
        x = x.transpose(1, 2)  # (B, C, T)
        return residual + x


class WaveNextHead(nn.Module):
    """Trainable linear head replacing the iSTFT stage (wetdog fork).

    Linear(dim, n_fft + 2) → Linear(n_fft + 2, hop_length, bias=False)
    → reshape to waveform → clip(-1, 1).

    NOTE: clip(-1, 1) は wetdog 独自 (paper 外)。
    """

    def __init__(self, dim: int, n_fft: int, hop_length: int):
        super().__init__()
        self.linear_1 = nn.Linear(dim, n_fft + 2)
        self.linear_2 = nn.Linear(n_fft + 2, hop_length, bias=False)
        nn.init.trunc_normal_(self.linear_1.weight, std=0.02)
        nn.init.trunc_normal_(self.linear_2.weight, std=0.02)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """[B, T_frames, dim] → [B, 1, T_frames * hop_length]"""
        x = self.linear_2(self.linear_1(x))  # (B, T, hop) frame-major
        audio = x.reshape(x.shape[0], 1, -1)  # (B, 1, hop*T)
        return torch.clip(audio, min=-1.0, max=1.0)


class WaveNeXtGenerator(nn.Module):
    """WaveNeXt v1 decoder: ConvNeXt backbone + linear head, 256x in one shot.

    Input:  latent ``[B, in_channels=192, T_frames]``
    Output: waveform ``[B, 1, T_frames * hop_length]``

    モジュール命名は wetdog/BSC-LT 準拠に pin (04 doc §3-8):
    ``embed`` / ``norm`` / ``convnext`` / ``final_layer_norm`` / ``head``。
    state_dict キーが ``__main__._WAVENEXT_MARKERS``
    (``model_g.dec.convnext.`` / ``model_g.dec.head.``) と一致することが
    tri-state 分類器の正当性要件。
    """

    def __init__(
        self,
        in_channels: int,
        dim: int = 512,
        intermediate_dim: int = 1536,
        num_blocks: int = 8,
        n_fft: int = 1024,
        hop_length: int = WAVENEXT_HOP_LENGTH,
        gin_channels: int = 0,
    ):
        super().__init__()
        self.gin_channels = gin_channels
        self.hop_length = hop_length
        self.onnx_export_mode = False
        # k=7 は wetdog/BSC-LT 準拠の意図的選択 (k=1 ではない)。
        # "conv_pre" 命名は HiFi-GAN / MB-iSTFT / WaveNeXt の 3 アーキ衝突で禁止。
        self.embed = nn.Conv1d(in_channels, dim, kernel_size=7, padding=3)
        self.norm = nn.LayerNorm(dim, eps=1e-6)
        # wetdog default = 1/num_layers = 0.125 (1e-6 ではない、04 doc 正誤表)
        layer_scale_init_value = 1.0 / num_blocks
        self.convnext = nn.ModuleList(
            [
                ConvNeXtBlock(dim, intermediate_dim, layer_scale_init_value)
                for _ in range(num_blocks)
            ]
        )
        self.final_layer_norm = nn.LayerNorm(dim, eps=1e-6)
        # backbone init のみ — head は apply() 後に生成 (PoC 実証順序)
        self.apply(self._init_weights)
        self.head = WaveNextHead(dim, n_fft, hop_length)
        if gin_channels != 0:
            # 入力段 additive speaker conditioning (Stage 1 最小実装)。
            # Zero-init → 学習開始時 identity、徐々に speaker 条件付けを獲得
            # (mb_istft の FiLM zero-init と同思想)。AdaLayerNorm 多サイト注入は
            # Stage 2 (S2-A) の ablation スコープ。
            self.cond = nn.Conv1d(gin_channels, dim, 1)
            nn.init.zeros_(self.cond.weight)
            nn.init.zeros_(self.cond.bias)

    @staticmethod
    def _init_weights(m: nn.Module) -> None:
        if isinstance(m, (nn.Conv1d, nn.Linear)):
            nn.init.trunc_normal_(m.weight, std=0.02)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)

    def forward(
        self, x: torch.Tensor, g: "torch.Tensor | None" = None
    ) -> "torch.Tensor | tuple[torch.Tensor, None]":
        """Generate waveform from latent representation.

        Args:
            x: Latent ``[B, in_channels, T_frames]``.
            g: Speaker embedding ``[B, gin_channels, 1]`` (optional).

        Returns:
            If ``onnx_export_mode`` is False (training):
                ``(fullband, None)`` — fullband は ``[B, 1, T_frames*256]``。
                WaveNeXt はサブバンド出力を持たないため 2 番目は常に None。
                models.py の ``o, o_mb = self.dec(...)`` ハード unpack と
                lightning.py の ``if o_mb is not None:`` guard が無変更で成立する。
            If ``onnx_export_mode`` is True:
                fullband tensor のみ (export_onnx.py の dec 呼び出し契約)。
        """
        x = self.embed(x)
        if g is not None and self.gin_channels != 0:
            x = x + self.cond(g)
        x = self.norm(x.transpose(1, 2)).transpose(1, 2)
        for block in self.convnext:
            x = block(x)
        x = self.final_layer_norm(x.transpose(1, 2))  # (B, T, dim)
        fullband = self.head(x)  # (B, 1, hop*T)
        if self.onnx_export_mode:
            return fullband
        return fullband, None

    def remove_weight_norm(self) -> None:
        """No-op: WaveNeXt は weight_norm を使用しない。

        export_onnx.py が ``model_g.dec.remove_weight_norm()`` を無条件に
        呼ぶため、no-op 実装が必須。
        """


# ---------------------------------------------------------------------------
# BSC-LT/wavenext-mel warm-start loader (--wavenext-init)
# ---------------------------------------------------------------------------

_BSC_LT_DROP_PREFIX = "feature_extractor."
_BSC_LT_BACKBONE_PREFIX = "backbone."
_BSC_LT_EMBED_WEIGHT = "backbone.embed.weight"


def load_bsc_lt_generator_weights(
    generator: WaveNeXtGenerator, state_dict: dict
) -> tuple[int, int, int]:
    """BSC-LT/wavenext-mel の pytorch_model.bin から decoder 重みを転写する。

    仕様 (04 doc §7):
      (a) ``feature_extractor.*`` 2 buffer は **drop** (VITS 統合では
          mel feature extractor を使わない)。
      (b) ``backbone.embed.weight`` (512, 80, 7) は **skip** — 192ch VITS
          latent 用のスクラッチ init を維持。``embed.bias`` (512,) は shape
          互換のため再利用する。
      (c) それ以外は ``backbone.`` prefix strip のみの rename
          (``head.*`` は prefix なしでそのまま通る)。

    実 BSC-LT ckpt は 83 keys で、返り値は (80, 1, 2) になる。
    ``cond.*`` (gin_channels > 0 時) は BSC-LT に存在せず zero-init を維持。

    NOTE: BSC-LT init の standalone sanity check は f_max=8000 / slaney の
    mel 設定が必須 — piper の ``mel_spectrogram_torch`` デフォルト
    (fmax=None → 11025) は filterbank が別物になるため使用禁止 (04 doc §7)。

    Returns:
        (loaded, skipped, dropped) のタプル。
    """
    own = dict(generator.state_dict())
    loaded = skipped = dropped = 0
    with torch.no_grad():
        for key, tensor in state_dict.items():
            if key.startswith(_BSC_LT_DROP_PREFIX):
                dropped += 1
                continue
            if key == _BSC_LT_EMBED_WEIGHT:
                skipped += 1
                continue
            new_key = key.removeprefix(_BSC_LT_BACKBONE_PREFIX)
            if new_key not in own:
                raise KeyError(f"Unexpected BSC-LT key: {key} -> {new_key}")
            if tuple(own[new_key].shape) != tuple(tensor.shape):
                raise ValueError(
                    f"Shape mismatch for BSC-LT key {key} -> {new_key}: "
                    f"checkpoint {tuple(tensor.shape)} vs "
                    f"model {tuple(own[new_key].shape)}"
                )
            own[new_key].copy_(tensor)
            loaded += 1
    return loaded, skipped, dropped
