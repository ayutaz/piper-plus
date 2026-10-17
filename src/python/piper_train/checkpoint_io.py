"""Read trusted training checkpoints across operating systems on CPU.

Training checkpoints contain Python objects. Only load checkpoints from trusted
sources, as with the existing weights_only=False training/evaluation loaders.
"""

import pathlib
import pickle
import sys

import torch


class Unpickler(pickle.Unpickler):
    """Translate concrete pathlib metadata without changing global classes."""

    def find_class(self, module, name):
        if module == "pathlib" and name in {"PosixPath", "WindowsPath"}:
            return pathlib.Path
        return super().find_class(module, name)


def load(source, **kwargs):
    return Unpickler(source, **kwargs).load()


def load_checkpoint(path, *, mmap=True):
    """Load trusted local weights/metadata onto CPU with portable path metadata."""
    return torch.load(
        path,
        map_location="cpu",
        mmap=mmap,
        weights_only=False,
        pickle_module=sys.modules[__name__],
    )


# エラーメッセージに並べる key の上限 (全件は件数で示す)
_MAX_LISTED_KEYS = 20


def key_has_module_prefix(key: str, prefixes) -> bool:
    """``key`` の module 経路が ``prefixes`` のどれかで始まる位置を含むか。

    照合は module 境界 (先頭または ``.`` の直後) でのみ行う。
    ``"model_g.reference_encoder.out.weight"`` や ``torch.compile`` 後の
    ``"model_g._orig_mod.reference_encoder.out.weight"`` は
    ``"reference_encoder."`` に一致し、``"model_g.my_reference_encoder.w"`` は
    一致しない。
    """
    return any(key.startswith(p) or f".{p}" in key for p in prefixes)


def _validate_allowed_prefixes(allowed_prefixes) -> tuple[str, ...]:
    if isinstance(allowed_prefixes, str) or not isinstance(
        allowed_prefixes, (tuple, list)
    ):
        raise TypeError(
            "allowed_prefixes must be a tuple of module prefixes such as "
            f"('reference_encoder.',), got {allowed_prefixes!r}"
        )
    for prefix in allowed_prefixes:
        if not isinstance(prefix, str) or len(prefix) < 2 or not prefix.endswith("."):
            raise ValueError(
                "allowed_prefixes entries must be non-empty module prefixes "
                f"ending with '.', got {prefix!r}"
            )
    return tuple(allowed_prefixes)


def _listed(keys) -> str:
    shown = ", ".join(str(k) for k in keys[:_MAX_LISTED_KEYS])
    rest = len(keys) - _MAX_LISTED_KEYS
    return shown + (f", ... (+{rest} more)" if rest > 0 else "")


def load_state_with_allowed_missing(
    model, state_dict: dict, allowed_prefixes: tuple[str, ...]
) -> dict:
    """``state_dict`` を読み、許可 prefix 配下の key だけ欠落を許す。

    旧 checkpoint を新設モジュール付きのモデルへ移すための厳格な読み込み
    (reference-fusion plan §8 Task 6R)。欠落してよいのは
    ``allowed_prefixes`` に module 境界で一致する key だけで、それらは
    モデル側の初期値 (zero-init) のまま残る。

    次はすべて ``ValueError`` (1 回のエラーにまとめて列挙) で、検査は
    読み込みの前に行うのでモデルは一切変更されない:

    * 許可 prefix 以外の欠落 (persistent buffer も含む)
    * checkpoint 側の余剰 key (許可 prefix 配下でも捨てない)
    * shape 差、tensor でない値

    Returns:
        ``{"missing": [...], "unexpected": [...]}`` — missing はモデルの
        state_dict 順。成功時の unexpected は常に空。
    """
    allowed = _validate_allowed_prefixes(allowed_prefixes)
    model_state = model.state_dict()

    missing = [k for k in model_state if k not in state_dict]
    unexpected = [k for k in state_dict if k not in model_state]
    disallowed_missing = [k for k in missing if not key_has_module_prefix(k, allowed)]
    not_tensor = []
    mismatched = []
    for key, target in model_state.items():
        if key not in state_dict:
            continue
        value = state_dict[key]
        if not isinstance(value, torch.Tensor):
            not_tensor.append(key)
        elif value.shape != target.shape:
            mismatched.append(
                f"{key}: checkpoint {tuple(value.shape)} vs model {tuple(target.shape)}"
            )

    problems = []
    if disallowed_missing:
        problems.append(
            f"missing keys outside {allowed}: {_listed(disallowed_missing)}"
        )
    if unexpected:
        problems.append(f"unexpected keys (not in model): {_listed(unexpected)}")
    if mismatched:
        problems.append(f"shape mismatch: {_listed(mismatched)}")
    if not_tensor:
        problems.append(f"non-tensor values: {_listed(not_tensor)}")
    if problems:
        raise ValueError(
            "checkpoint does not match the model; only keys under "
            f"{allowed} may be missing. " + "; ".join(problems)
        )

    model.load_state_dict(state_dict, strict=False)
    return {"missing": missing, "unexpected": unexpected}
