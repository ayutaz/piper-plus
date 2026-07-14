"""Training-only discriminator for the WaveNeXt decoder ablation.

Not part of the ONNX inference graph.

DAC band-split 型 MultiResolutionDiscriminator:
descript-audio-codec (MIT, Copyright (c) 2023 Descript) 由来の構成で、
wetdog/wavenext_pytorch@d45d544 が採用しているもの。

GAN loss は piper 既存の LSGAN (losses.py の discriminator_loss /
generator_loss / feature_loss) を再利用するため、本ファイルに loss 関数は
置かない (hinge 不採用は 03 doc の LSGAN 一本化判断)。そのために
:class:`MultiResolutionDiscriminator` の forward 返却契約を
``MultiPeriodDiscriminator`` (models.py) と同形に pin している。
"""

import torch
import torch.nn.functional as F
from torch import nn
from torch.nn.utils import weight_norm


# DAC 準拠の周波数帯分割 (n_bins 比)
BANDS = ((0.0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0))


class DiscriminatorR(nn.Module):
    """Single-resolution band-split spectrogram discriminator (DAC-style)."""

    def __init__(
        self,
        fft_size: int,
        hop_factor: float = 0.25,
        bands: tuple[tuple[float, float], ...] = BANDS,
        channels: int = 32,
    ):
        super().__init__()
        self.fft_size = fft_size
        self.hop_length = int(fft_size * hop_factor)
        n_bins = fft_size // 2 + 1
        self.bands = [(int(lo * n_bins), int(hi * n_bins)) for lo, hi in bands]
        self.register_buffer("window", torch.hann_window(fft_size))

        def _conv_stack() -> nn.ModuleList:
            return nn.ModuleList(
                [
                    weight_norm(nn.Conv2d(2, channels, (3, 9), padding=(1, 4))),
                    weight_norm(
                        nn.Conv2d(
                            channels, channels, (3, 9), stride=(1, 2), padding=(1, 4)
                        )
                    ),
                    weight_norm(
                        nn.Conv2d(
                            channels, channels, (3, 9), stride=(1, 2), padding=(1, 4)
                        )
                    ),
                    weight_norm(
                        nn.Conv2d(
                            channels, channels, (3, 9), stride=(1, 2), padding=(1, 4)
                        )
                    ),
                    weight_norm(nn.Conv2d(channels, channels, (3, 3), padding=(1, 1))),
                ]
            )

        self.band_convs = nn.ModuleList([_conv_stack() for _ in self.bands])
        self.conv_post = weight_norm(nn.Conv2d(channels, 1, (3, 3), padding=(1, 1)))

    def spectrogram(self, x: torch.Tensor) -> list[torch.Tensor]:
        """[B, 1, T] → list of [B, 2, frames, band_bins] (real/imag)."""
        # bf16-mixed 下の torch.stft は half 非対応のため必ず float32 に cast
        # (losses.py の各 loss も .float() 済みで整合)
        x = x.squeeze(1).float()
        stft = torch.stft(
            x,
            self.fft_size,
            hop_length=self.hop_length,
            win_length=self.fft_size,
            window=self.window,
            center=True,
            return_complex=True,
        )
        x = torch.view_as_real(stft)  # [B, F, frames, 2]
        x = x.permute(0, 3, 2, 1)  # [B, 2, frames, F]
        return [x[..., lo:hi] for lo, hi in self.bands]

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, list[torch.Tensor]]:
        fmap = []
        outs = []
        for band, convs in zip(self.spectrogram(x), self.band_convs, strict=True):
            for conv in convs:
                band = F.leaky_relu(conv(band), 0.1)
                fmap.append(band)
            outs.append(band)
        x = torch.cat(outs, dim=-1)  # 周波数軸で band 連結
        x = self.conv_post(x)  # conv_post 後は activation なし
        fmap.append(x)
        return x, fmap


class MultiResolutionDiscriminator(nn.Module):
    """Fullband multi-resolution discriminator (decoder_arch='wavenext' 専用)."""

    def __init__(self, fft_sizes: tuple[int, ...] = (2048, 1024, 512)):
        super().__init__()
        self.discriminators = nn.ModuleList([DiscriminatorR(f) for f in fft_sizes])

    def forward(self, y: torch.Tensor, y_hat: torch.Tensor):
        """MultiPeriodDiscriminator (models.py) と同一の返却契約。

        losses.py の discriminator_loss / generator_loss / feature_loss を
        そのまま適用できるよう (y_d_rs, y_d_gs, fmap_rs, fmap_gs) を返す。
        """
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        for d in self.discriminators:
            y_d_r, fmap_r = d(y)
            y_d_g, fmap_g = d(y_hat)
            y_d_rs.append(y_d_r)
            y_d_gs.append(y_d_g)
            fmap_rs.append(fmap_r)
            fmap_gs.append(fmap_g)

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs
