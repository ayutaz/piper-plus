import logging

import torch
from librosa.filters import mel as librosa_mel_fn
from torch.nn import functional as F


_LOGGER = logging.getLogger(__name__)


def feature_loss(fmap_r, fmap_g):
    loss = 0
    for dr, dg in zip(fmap_r, fmap_g, strict=False):
        for rl, gl in zip(dr, dg, strict=False):
            rl = rl.float().detach()
            gl = gl.float()
            loss += torch.mean(torch.abs(rl - gl))

    return loss * 2


def discriminator_loss(disc_real_outputs, disc_generated_outputs):
    loss = 0
    r_losses = []
    g_losses = []
    for dr, dg in zip(disc_real_outputs, disc_generated_outputs, strict=False):
        dr = dr.float()
        dg = dg.float()
        r_loss = torch.mean((1 - dr) ** 2)
        g_loss = torch.mean(dg**2)
        loss += r_loss + g_loss
        r_losses.append(r_loss.item())
        g_losses.append(g_loss.item())

    return loss, r_losses, g_losses


def generator_loss(disc_outputs):
    loss = 0
    gen_losses = []
    for dg in disc_outputs:
        dg = dg.float()
        l_dg = torch.mean((1 - dg) ** 2)
        gen_losses.append(l_dg)
        loss += l_dg

    return loss, gen_losses


def kl_loss(z_p, logs_q, m_p, logs_p, z_mask):
    """
    z_p, logs_q: [b, h, t_t]
    m_p, logs_p: [b, h, t_t]
    """
    z_p = z_p.float()
    logs_q = logs_q.float()
    m_p = m_p.float()
    logs_p = logs_p.float()
    z_mask = z_mask.float()

    kl = logs_p - logs_q - 0.5
    kl += 0.5 * ((z_p - m_p) ** 2) * torch.exp(-2.0 * logs_p)
    kl = torch.sum(kl * z_mask)
    l_kl = kl / torch.sum(z_mask)
    return l_kl


def speaker_consistency_loss(gen_embedding, ref_embedding):
    """Speaker Consistency Loss (SCL) — コサイン類似度ベースの話者一貫性損失

    Parameters
    ----------
    gen_embedding : torch.Tensor
        生成音声から抽出した話者埋め込み [B, D]
    ref_embedding : torch.Tensor
        参照音声の話者埋め込み [B, D]

    Returns
    -------
    torch.Tensor
        スカラー損失値 (範囲: 0-2, 0が完全一致)
    """
    # NaN/Infチェック: CAM++ ONNX出力が異常な場合は0を返す
    if torch.isnan(gen_embedding).any() or torch.isnan(ref_embedding).any():
        return torch.tensor(0.0, device=gen_embedding.device)
    return 1.0 - F.cosine_similarity(gen_embedding, ref_embedding, dim=-1).mean()


def dino_loss(student_emb, teacher_emb, center, tau_s=0.1, tau_t=0.07):
    """DINO自己蒸留損失 — 話者埋め込み空間の正則化

    Parameters
    ----------
    student_emb : torch.Tensor
        学生ネットワーク出力 [B, D]
    teacher_emb : torch.Tensor
        教師ネットワーク出力 [B, D] (通常は detach 済み)
    center : torch.Tensor
        EMA センター [D]
    tau_s : float
        学生温度パラメータ (default: 0.1)
    tau_t : float
        教師温度パラメータ (default: 0.07)

    Returns
    -------
    torch.Tensor
        スカラー損失値 (正の値、NaN/Inf 時は 0)
    """
    # NaN/Inf を入力段階で検出し、後段でロガーが原因を切り分けられるようにする。
    # PyTorch の clamp は NaN を素通しするため、上流から NaN が伝播してきた場合は
    # log_softmax → NaN → loss=0 マスクで「DINO が黙って機能停止する」状態に陥る。
    # 既知の現象 (multi-6lang スクラッチで step ~1249 から発生)。
    if not torch.isfinite(student_emb).all():
        _LOGGER.warning(
            "dino_loss: student_emb has non-finite values "
            "(NaN=%d, Inf=%d, total=%d). Returning 0.",
            int(torch.isnan(student_emb).sum().item()),
            int(torch.isinf(student_emb).sum().item()),
            student_emb.numel(),
        )
        return torch.tensor(0.0, device=student_emb.device)
    if not torch.isfinite(teacher_emb).all():
        _LOGGER.warning(
            "dino_loss: teacher_emb has non-finite values "
            "(NaN=%d, Inf=%d). Returning 0.",
            int(torch.isnan(teacher_emb).sum().item()),
            int(torch.isinf(teacher_emb).sum().item()),
        )
        return torch.tensor(0.0, device=student_emb.device)
    if not torch.isfinite(center).all():
        _LOGGER.warning("dino_loss: dino_center has non-finite values. Returning 0.")
        return torch.tensor(0.0, device=student_emb.device)

    # Clamp softmax inputs to prevent exp overflow (NaN fix #8)
    student_logits = (student_emb / tau_s).clamp(min=-50.0, max=50.0)
    teacher_logits = ((teacher_emb - center.to(teacher_emb.dtype)) / tau_t).clamp(
        min=-50.0, max=50.0
    )
    student_out = F.log_softmax(student_logits, dim=-1)
    teacher_out = F.softmax(teacher_logits, dim=-1)
    loss = -(teacher_out * student_out).sum(dim=-1).mean()
    # NaN防止: 損失が異常な場合は0を返す (上流チェックで漏れた数値発散の最終ガード)
    if torch.isnan(loss) or torch.isinf(loss):
        _LOGGER.warning(
            "dino_loss: post-softmax loss is non-finite "
            "(student_emb stats: min=%.3f max=%.3f, teacher_emb: min=%.3f max=%.3f). "
            "Returning 0.",
            float(student_emb.min()),
            float(student_emb.max()),
            float(teacher_emb.min()),
            float(teacher_emb.max()),
        )
        return torch.tensor(0.0, device=student_emb.device)
    return loss


# ---------------------------------------------------------------------------
# Pre-computed mel filterbank cache (keyed by (n_fft, n_mels, sr, fmin, fmax))
# ---------------------------------------------------------------------------
_mel_basis_cache: dict[tuple, torch.Tensor] = {}


def _get_mel_basis(
    n_fft: int = 1024,
    n_mels: int = 80,
    sample_rate: int = 22050,
    fmin: float = 0.0,
    fmax: float | None = None,
    device: torch.device | None = None,
    dtype: torch.dtype = torch.float32,
) -> torch.Tensor:
    """Return a mel filterbank matrix, caching across calls."""
    key = (n_fft, n_mels, sample_rate, fmin, fmax)
    if key not in _mel_basis_cache:
        fb = librosa_mel_fn(
            sr=sample_rate, n_fft=n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax
        )
        _mel_basis_cache[key] = torch.from_numpy(fb)
    basis = _mel_basis_cache[key]
    if device is not None:
        basis = basis.to(device=device, dtype=dtype)
    return basis


def mel_speaker_consistency_loss(
    y_hat: torch.Tensor,
    y: torch.Tensor,
    n_fft: int = 1024,
    n_mels: int = 80,
    hop_length: int = 256,
    win_length: int = 1024,
    sample_rate: int = 22050,
    mel_fmin: float = 0.0,
    mel_fmax: float | None = None,
) -> torch.Tensor:
    """Differentiable speaker consistency loss via mel spectrogram statistics.

    Compares per-band mean and standard-deviation of the mel spectrograms of
    generated audio (``y_hat``) and real audio (``y``) from the **same
    speaker**.  This captures speaker-specific spectral characteristics such as
    formant structure and spectral tilt without requiring a separate speaker
    encoder, and -- crucially -- the entire computation is differentiable so
    gradients flow back through the generator.

    Parameters
    ----------
    y_hat : Tensor [B, 1, T]
        Generated waveform (in the computation graph).
    y : Tensor [B, 1, T]
        Ground-truth waveform from the same speaker (detached).

    Returns
    -------
    loss : scalar Tensor
        L1 distance between per-band (mean, std) statistics.
    """
    # Squeeze to [B, T]
    if y_hat.dim() == 3:
        y_hat = y_hat.squeeze(1)
    if y.dim() == 3:
        y = y.squeeze(1)

    window = torch.hann_window(win_length, device=y_hat.device, dtype=y_hat.dtype)

    mel_basis = _get_mel_basis(
        n_fft=n_fft,
        n_mels=n_mels,
        sample_rate=sample_rate,
        fmin=mel_fmin,
        fmax=mel_fmax,
        device=y_hat.device,
        dtype=y_hat.dtype,
    )

    def _to_mel(wav: torch.Tensor) -> torch.Tensor:
        """wav [B, T] -> log-mel [B, n_mels, frames]"""
        pad = (n_fft - hop_length) // 2
        wav = torch.nn.functional.pad(wav, (pad, pad), mode="reflect")
        stft = torch.stft(
            wav,
            n_fft,
            hop_length=hop_length,
            win_length=win_length,
            window=window,
            center=False,
            return_complex=True,
        )
        mag = stft.abs().clamp(min=1e-5)
        mel = torch.matmul(mel_basis.to(mag.dtype), mag)
        log_mel = torch.log(mel.clamp(min=1e-5))
        return log_mel

    mel_hat = _to_mel(y_hat)
    mel_real = _to_mel(y.detach())

    mean_hat = mel_hat.mean(dim=-1)
    std_hat = mel_hat.std(dim=-1) + 1e-6
    mean_real = mel_real.mean(dim=-1)
    std_real = mel_real.std(dim=-1) + 1e-6

    loss = F.l1_loss(mean_hat, mean_real) + F.l1_loss(std_hat, std_real)
    return loss
