import logging
import math
import re

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


# ---------------------------------------------------------------------------
# Checkpoint compatibility: pre-FiLM MB-iSTFT decoders
# ---------------------------------------------------------------------------
#
# PR #579 (Zero-Shot TTS) replaced the decoder's additive speaker conditioning
# with Multi-scale FiLM. `MBiSTFTGenerator.cond` went from
#
#     nn.Conv1d(gin_channels, upsample_initial_channel, 1)      # x = x + cond(g)
#
# to
#
#     nn.Conv1d(gin_channels, upsample_initial_channel * 2, 1)  # FiLM scale+shift
#
# and gained per-upsample-stage `cond_layers`. Every checkpoint published or
# trained before that change therefore fails to load with
#
#     size mismatch for model_g.dec.cond.weight: copying a param with shape
#     torch.Size([256, 512, 1]) ... the shape in current model is
#     torch.Size([512, 512, 1])
#
# (`strict=False` does not relax size mismatches — it only tolerates missing
# and unexpected keys.) See issue #616.
#
# The conversion is exact rather than approximate. `_apply_film` splits the
# conditioning into `scale_raw` (first half) and `shift` (second half) and
# computes `x * (sigmoid(scale_raw) + 0.5) + shift`. With `scale_raw == 0` the
# gain is `sigmoid(0) + 0.5 == 1.0`, so stacking zeros on top of the old
# weights reproduces `x + cond(g)` bit-for-bit. The new `cond_layers` are
# zero-initialised for the same reason, so back-filling them with zeros leaves
# the decoder's output unchanged.

_DEC_COND_RE = re.compile(r"(?:^|\.)dec\.cond\.(weight|bias)$")
_EMA_COND_RE = re.compile(r"^cond\.(weight|bias)$")

_LEGACY_HIFIGAN_MESSAGE = (
    "Checkpoint {path!r} appears to be from v1.11.0 or earlier (HiFi-GAN Generator). "
    "v1.12.0 unified the decoder to MB-iSTFT-VITS2, so HiFi-GAN ckpt files cannot be "
    "resumed for training. Fine-tune from the new MB-iSTFT base model instead:\n"
    "    https://huggingface.co/ayousanz/piper-plus-base/resolve/main/model.ckpt\n"
    "See docs/migration/v1.11-to-v1.12.md for the full migration guide."
)


def is_legacy_hifigan_checkpoint(state_dict: dict) -> bool:
    """Detect a v1.11.0-or-earlier HiFi-GAN checkpoint.

    v1.12.0 unified the decoder to MB-iSTFT-VITS2. An MB-iSTFT decoder always
    carries ``model_g.dec.subband_conv_post.*`` or ``model_g.dec.pqmf.*``; a
    HiFi-GAN decoder never does. Decoder keys without those markers therefore
    mean HiFi-GAN.

    This must be checked *before* the pre-FiLM migration below, because the two
    are indistinguishable by shape alone: HiFi-GAN's ``Generator.cond`` was also
    ``nn.Conv1d(gin_channels, upsample_initial_channel, 1)``, which at the
    ``medium`` default (``upsample_initial_channel=256``) produces exactly the
    same ``(256, 512, 1)`` tensor as a pre-FiLM MB-iSTFT decoder. Only the
    marker keys tell them apart.
    """
    has_decoder_keys = any(k.startswith("model_g.dec.") for k in state_dict)
    has_mbistft_marker = any(
        k.startswith("model_g.dec.subband_conv_post")
        or k.startswith("model_g.dec.pqmf")
        for k in state_dict
    )
    return has_decoder_keys and not has_mbistft_marker


def strip_orig_mod(state_dict: dict) -> tuple[dict, int]:
    """Remove ``._orig_mod.`` inserted by ``torch.compile`` from state_dict keys.

    When a checkpoint is saved while ``torch.compile`` is active, parameter keys
    gain an ``_orig_mod`` segment (e.g. ``model_g.dec._orig_mod.conv_pre.weight``).
    ``load_state_dict(strict=False)`` silently ignores these mismatched keys,
    leaving the weights uninitialised.

    Returns ``(cleaned_dict, n_stripped)``. The input is not mutated.
    """
    cleaned: dict = {}
    n_stripped = 0
    for key, value in state_dict.items():
        new_key = key.replace("._orig_mod.", ".")
        if new_key != key:
            n_stripped += 1
        cleaned[new_key] = value
    if n_stripped > 0:
        _LOGGER.info("Stripped '_orig_mod' from %d checkpoint key(s).", n_stripped)
    return cleaned, n_stripped


def _is_prefilm_cond(saved: "torch.Tensor", target: "torch.Tensor") -> bool:
    """Whether *saved* is the pre-FiLM half-width counterpart of *target*."""
    if not (torch.is_tensor(saved) and torch.is_tensor(target)):
        return False
    if saved.dim() != target.dim() or saved.dim() == 0:
        return False
    return saved.shape[0] * 2 == target.shape[0] and tuple(saved.shape[1:]) == tuple(
        target.shape[1:]
    )


def _widen_to_film(value: "torch.Tensor") -> "torch.Tensor":
    """Stack zeros on top of *value* so FiLM's scale half is the identity."""
    return torch.cat([torch.zeros_like(value), value], dim=0)


def migrate_prefilm_decoder_cond(saved_sd: dict, model_sd: dict) -> tuple[dict, int]:
    """Widen pre-FiLM ``dec.cond`` weights and back-fill ``cond_layers``.

    Handles both namespaces:

    * full model state dicts, where the key is ``model_g.dec.cond.weight``
    * decoder-relative EMA shadow params, where it is plain ``cond.weight``

    A key is migrated only when it matches one of those patterns, exists in
    *model_sd*, and is exactly half the target's first dimension with every
    other dimension equal. Anything else is passed through untouched, which
    makes the function idempotent: a second pass finds the shapes already equal
    and migrates nothing.

    Returns ``(migrated_dict, n_migrated)``. The input is not mutated.
    """
    out = dict(saved_sd)
    migrated = 0
    prefixes: set[str] = set()

    for key, value in saved_sd.items():
        if not (_DEC_COND_RE.search(key) or _EMA_COND_RE.match(key)):
            continue
        target = model_sd.get(key)
        if target is None or not _is_prefilm_cond(value, target):
            continue
        out[key] = _widen_to_film(value)
        migrated += 1
        prefixes.add(key[: key.rindex("cond.")])

    if migrated == 0:
        return out, 0

    # Back-fill the per-stage FiLM layers. They are zero-initialised in the
    # model too, so this is not merely "something to fill the hole" — zeros are
    # the values that keep the decoder's output identical to the pre-FiLM one.
    # Without them, strict=True load paths fail on missing keys.
    backfilled = 0
    for prefix in prefixes:
        layer_prefix = f"{prefix}cond_layers."
        for key, target in model_sd.items():
            if key.startswith(layer_prefix) and key not in out:
                out[key] = torch.zeros_like(target)
                backfilled += 1

    _LOGGER.info(
        "Migrated %d pre-FiLM decoder conditioning tensor(s) and back-filled "
        "%d zero-initialised cond_layers entr(y/ies) (issue #616).",
        migrated,
        backfilled,
    )
    return out, migrated


def normalize_checkpoint_state_dict(
    saved_sd: dict,
    model_sd: dict,
    *,
    checkpoint_path: "str | None" = None,
) -> tuple[dict, dict]:
    """Apply every checkpoint compatibility fixup, in the one order that works.

    ``(normalized_state_dict, stats)``.

    The order is not arbitrary:

    1. ``strip_orig_mod`` — key rename (``torch.compile`` artifact). Runs first
       because every later step matches on canonical key names, the HiFi-GAN
       marker check included: a checkpoint saved under ``torch.compile`` spells
       the marker ``model_g.dec._orig_mod.subband_conv_post.weight``, which
       would otherwise read as "no MB-iSTFT marker" and be rejected as HiFi-GAN.
    2. **HiFi-GAN rejection** — before any reshape. Once shapes are rewritten
       there is no way left to tell a v1.11 HiFi-GAN checkpoint from a pre-FiLM
       MB-iSTFT one: their ``dec.cond`` tensors have identical shapes, and only
       the ``subband_conv_post`` / ``pqmf`` marker keys distinguish them.
    3. ``remap_weight_norm_keys`` — key rename (DDP parametrization format).
    4. ``migrate_prefilm_decoder_cond`` — value reshape, and therefore **last**:
       it looks target shapes up in *model_sd* by key, so it silently does
       nothing if the keys have not been canonicalised first (a
       ``model_g.dec._orig_mod.cond.weight`` key matches neither the regex nor
       *model_sd*, and the load then fails with the original size mismatch).

    Raises ``RuntimeError`` with a migration message for HiFi-GAN checkpoints.
    """
    cleaned, n_stripped = strip_orig_mod(saved_sd)

    if is_legacy_hifigan_checkpoint(cleaned):
        raise RuntimeError(_LEGACY_HIFIGAN_MESSAGE.format(path=str(checkpoint_path)))

    cleaned = remap_weight_norm_keys(cleaned, model_sd)
    cleaned, n_migrated = migrate_prefilm_decoder_cond(cleaned, model_sd)

    return cleaned, {"stripped": n_stripped, "cond_migrated": n_migrated}


def migrate_prefilm_optimizer_states(
    checkpoint: dict, named_params: "list[tuple[str, torch.Tensor]]"
) -> int:
    """Widen Adam moments for tensors the pre-FiLM migration reshaped.

    ``optimizer.load_state_dict`` performs **no shape validation** — a
    checkpoint whose ``exp_avg`` is ``(256, 512, 1)`` loads cleanly into a
    ``(512, 512, 1)`` parameter and only blows up at the first ``step()``.
    In ``piper_train`` that exception is then swallowed by the resume
    fallback, which rebuilds the Trainer and restarts from **epoch 0**. So
    migrating the weights without migrating the optimizer state turns a loud
    failure into silent loss of training progress.

    Optimizer state is keyed by the parameter's *position* in the list handed
    to the optimizer, and that ordering is not recorded in the checkpoint.
    Rather than trust a reconstructed mapping blindly, this validates it: every
    stored moment must match its mapped parameter's shape, either exactly or by
    the same half-width relation the decoder migration uses. If a single entry
    disagrees, the mapping is considered unreliable and nothing is widened —
    the caller is expected to drop the optimizer state loudly instead of
    corrupting it.

    Args:
        checkpoint: full Lightning checkpoint dict (mutated in place).
        named_params: ``(name, tensor)`` in the exact order the generator
            optimizer received them.

    Returns:
        Number of moment tensors widened. ``0`` means either nothing needed
        migrating or the mapping could not be validated; use
        :func:`optimizer_states_need_migration` to tell those apart.
    """
    optimizer_states = checkpoint.get("optimizer_states")
    if not optimizer_states:
        return 0

    # Only the generator optimizer (index 0) owns decoder parameters.
    state = optimizer_states[0].get("state")
    if not isinstance(state, dict) or not state:
        return 0

    widened = 0
    planned: list[tuple[dict, str]] = []
    for index, moments in state.items():
        if not isinstance(index, int) or index >= len(named_params):
            return 0
        name, param = named_params[index]
        for moment_key in ("exp_avg", "exp_avg_sq"):
            moment = moments.get(moment_key)
            if moment is None or not torch.is_tensor(moment):
                continue
            if tuple(moment.shape) == tuple(param.shape):
                continue
            if _DEC_COND_RE.search(name) and _is_prefilm_cond(moment, param):
                planned.append((moments, moment_key))
                continue
            # A shape we cannot explain — the index mapping is not trustworthy.
            return 0

    for moments, moment_key in planned:
        moments[moment_key] = _widen_to_film(moments[moment_key])
        widened += 1

    if widened:
        _LOGGER.info(
            "Widened %d optimizer moment tensor(s) for the pre-FiLM decoder "
            "migration; optimizer state is preserved across the resume.",
            widened,
        )
    return widened


def optimizer_states_need_migration(checkpoint: dict, model_sd: dict) -> bool:
    """Whether the checkpoint's optimizer state has pre-FiLM decoder shapes.

    Used to decide between preserving and discarding optimizer state, so that
    "we dropped your optimizer state" is always reported rather than surfacing
    later as an unexplained restart from epoch 0.
    """
    optimizer_states = checkpoint.get("optimizer_states")
    if not optimizer_states:
        return False
    state = optimizer_states[0].get("state")
    if not isinstance(state, dict):
        return False
    targets = [v for k, v in model_sd.items() if _DEC_COND_RE.search(k)]
    for moments in state.values():
        for moment_key in ("exp_avg", "exp_avg_sq"):
            moment = moments.get(moment_key)
            if moment is None or not torch.is_tensor(moment):
                continue
            if any(_is_prefilm_cond(moment, target) for target in targets):
                return True
    return False
