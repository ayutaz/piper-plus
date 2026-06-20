import logging
import math

import torch
from torch.nn import functional as F


_LOGGER = logging.getLogger("vits.commons")


def remap_weight_norm_keys(saved_sd: dict, model_sd: dict) -> dict:
    """Remap weight_norm keys between old and new PyTorch formats.

    DDP (multi-GPU) training may convert weight_norm to the parametrized format,
    while single-GPU training retains the legacy format.  This causes key
    mismatches when loading checkpoints across configurations.

    Old format (legacy ``torch.nn.utils.weight_norm``):
        ``module.weight_g``, ``module.weight_v``

    New format (``torch.nn.utils.parametrizations.weight_norm``):
        ``module.parametrizations.weight.original0``,
        ``module.parametrizations.weight.original1``

    The tensor contents are compatible (g ↔ original0, v ↔ original1).
    """
    remapped: dict = {}
    n_remapped = 0

    for key, value in saved_sd.items():
        new_key = key

        # Old → New
        if ".weight_g" in key:
            candidate = key.replace(".weight_g", ".parametrizations.weight.original0")
            if candidate in model_sd and key not in model_sd:
                new_key = candidate
        elif ".weight_v" in key:
            candidate = key.replace(".weight_v", ".parametrizations.weight.original1")
            if candidate in model_sd and key not in model_sd:
                new_key = candidate

        # New → Old
        elif ".parametrizations.weight.original0" in key:
            candidate = key.replace(".parametrizations.weight.original0", ".weight_g")
            if candidate in model_sd and key not in model_sd:
                new_key = candidate
        elif ".parametrizations.weight.original1" in key:
            candidate = key.replace(".parametrizations.weight.original1", ".weight_v")
            if candidate in model_sd and key not in model_sd:
                new_key = candidate

        if new_key != key:
            n_remapped += 1

        remapped[new_key] = value

    if n_remapped > 0:
        _LOGGER.info(
            "Remapped %d weight_norm key(s) for checkpoint compatibility.", n_remapped
        )

    return remapped


def init_weights(m, mean=0.0, std=0.01):
    classname = m.__class__.__name__
    if classname.find("Conv") != -1:
        m.weight.data.normal_(mean, std)


def get_padding(kernel_size, dilation=1):
    return int((kernel_size * dilation - dilation) / 2)


def intersperse(lst, item):
    result = [item] * (len(lst) * 2 + 1)
    result[1::2] = lst
    return result


def kl_divergence(m_p, logs_p, m_q, logs_q):
    """KL(P||Q)"""
    kl = (logs_q - logs_p) - 0.5
    kl += (
        0.5 * (torch.exp(2.0 * logs_p) + ((m_p - m_q) ** 2)) * torch.exp(-2.0 * logs_q)
    )
    return kl


def rand_gumbel(shape):
    """Sample from the Gumbel distribution, protect from overflows."""
    uniform_samples = torch.rand(shape) * 0.99998 + 0.00001
    return -torch.log(-torch.log(uniform_samples))


def rand_gumbel_like(x):
    g = rand_gumbel(x.size()).to(dtype=x.dtype, device=x.device)
    return g


def slice_segments(x, ids_str, segment_size=4):
    ret = torch.zeros_like(x[:, :, :segment_size])
    for i in range(x.size(0)):
        idx_str = max(0, ids_str[i])
        idx_end = idx_str + segment_size
        seg = x[i, :, idx_str:idx_end]
        seg_len = seg.size(-1)
        if seg_len < segment_size:
            ret[i, :, :seg_len] = seg
        else:
            ret[i] = seg
    return ret


def rand_slice_segments(x, x_lengths=None, segment_size=4):
    b, _d, t = x.size()
    if x_lengths is None:
        x_lengths = t
    ids_str_max = x_lengths - segment_size + 1
    ids_str_max = torch.clamp(ids_str_max, min=1)
    ids_str = (torch.rand([b]).to(device=x.device) * ids_str_max).to(dtype=torch.long)
    ret = slice_segments(x, ids_str, segment_size)
    return ret, ids_str


def get_timing_signal_1d(length, channels, min_timescale=1.0, max_timescale=1.0e4):
    position = torch.arange(length, dtype=torch.float)
    num_timescales = channels // 2
    log_timescale_increment = math.log(float(max_timescale) / float(min_timescale)) / (
        num_timescales - 1
    )
    inv_timescales = min_timescale * torch.exp(
        torch.arange(num_timescales, dtype=torch.float) * -log_timescale_increment
    )
    scaled_time = position.unsqueeze(0) * inv_timescales.unsqueeze(1)
    signal = torch.cat([torch.sin(scaled_time), torch.cos(scaled_time)], 0)
    signal = F.pad(signal, [0, 0, 0, channels % 2])
    signal = signal.view(1, channels, length)
    return signal


def add_timing_signal_1d(x, min_timescale=1.0, max_timescale=1.0e4):
    _b, channels, length = x.size()
    signal = get_timing_signal_1d(length, channels, min_timescale, max_timescale)
    return x + signal.to(dtype=x.dtype, device=x.device)


def cat_timing_signal_1d(x, min_timescale=1.0, max_timescale=1.0e4, axis=1):
    _b, channels, length = x.size()
    signal = get_timing_signal_1d(length, channels, min_timescale, max_timescale)
    return torch.cat([x, signal.to(dtype=x.dtype, device=x.device)], axis)


def subsequent_mask(length: int):
    mask = torch.tril(torch.ones(length, length)).unsqueeze(0).unsqueeze(0)
    return mask


@torch.jit.script
def fused_add_tanh_sigmoid_multiply(input_a, input_b, n_channels):
    n_channels_int = n_channels[0]
    in_act = input_a + input_b
    t_act = torch.tanh(in_act[:, :n_channels_int, :])
    s_act = torch.sigmoid(in_act[:, n_channels_int:, :])
    acts = t_act * s_act
    return acts


def sequence_mask(length, max_length: int | None = None):
    if max_length is None:
        max_length = length.max()
    x = torch.arange(max_length, dtype=length.dtype, device=length.device)
    return x.unsqueeze(0) < length.unsqueeze(1)


def generate_path(duration, mask):
    """
    duration: [b, 1, t_x]
    mask: [b, 1, t_y, t_x]
    """
    b, _, t_y, t_x = mask.shape
    cum_duration = torch.cumsum(duration, -1)

    cum_duration_flat = cum_duration.view(b * t_x)
    path = sequence_mask(cum_duration_flat, t_y).type_as(mask)
    path = path.view(b, t_x, t_y)
    path = path - F.pad(path, (0, 0, 1, 0, 0, 0))[:, :-1]
    path = path.unsqueeze(1).transpose(2, 3) * mask
    return path


def clip_grad_value_(parameters, clip_value, norm_type=2):
    if isinstance(parameters, torch.Tensor):
        parameters = [parameters]
    parameters = list(filter(lambda p: p.grad is not None, parameters))
    norm_type = float(norm_type)
    if clip_value is not None:
        clip_value = float(clip_value)

    total_norm = 0
    for p in parameters:
        param_norm = p.grad.data.norm(norm_type)
        total_norm += param_norm.item() ** norm_type
        if clip_value is not None:
            p.grad.data.clamp_(min=-clip_value, max=clip_value)
    total_norm = total_norm ** (1.0 / norm_type)
    return total_norm
