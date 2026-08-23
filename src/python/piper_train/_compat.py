"""Cross-platform compatibility shims.

Loaded eagerly when :mod:`piper_train` is imported so all entry points
(`export_onnx`, `infer`, `export_torchscript`, etc.) transparently
handle checkpoints produced by other platforms and Python versions.

Issues addressed:

- **PyTorch 2.6+ ``weights_only=True`` restriction**: ``pathlib`` classes
  must be registered as safe globals, because Lightning pickles
  ``PosixPath`` instances into ``hyper_parameters`` / callback state.
- **PosixPath instantiation on Windows**: without the module aliases
  below, ``torch.load(..., weights_only=False)`` on Windows raises
  ``UnsupportedOperation: cannot instantiate 'PosixPath' on your system``.

Why both module spellings are registered
----------------------------------------
``add_safe_globals([cls])`` (bare form) does **not** store the string the
pickle will contain. torch derives the registry key lazily, at lookup
time, from ``f"{cls.__module__}.{cls.__qualname__}"``
(``torch/_weights_only_unpickler.py``), while the unpickler looks the
pickled ``GLOBAL`` string up in that registry verbatim. So the key
depends on whatever ``pathlib.PosixPath.__module__`` happens to be in the
*reading* interpreter, not on what the *writing* one recorded.

CPython moved the concrete path classes into a private submodule in 3.13
and moved them back in 3.14. Measured ``pathlib.PosixPath.__module__``:

    3.11  -> "pathlib"          (``pathlib._local`` does not exist)
    3.12  -> "pathlib"
    3.13  -> "pathlib._local"   <- only this release
    3.14  -> "pathlib"          (``pathlib._local`` still importable,
                                 and is the very same class object)

A checkpoint written under 3.12 therefore pickles ``pathlib PosixPath``,
but a 3.13 reader registers only ``pathlib._local.PosixPath`` — the names
never match and the load fails with ``UnpicklingError`` even though the
shim "ran". The mirror case (3.13-written checkpoint read under 3.12)
fails the same way. Registering every spelling explicitly, via the
``(callable, name)`` tuple form, is what makes both directions work.

This module has no public API beyond
:func:`apply_windows_pathlib_aliases`; importing it for the side-effects
is the contract.

torch is imported lazily inside a ``try``/``except ImportError`` because
:mod:`piper_train` is also imported by lightweight CI jobs that don't
install torch (e.g. dataset / utility tests). The pathlib aliases
themselves only need :mod:`pathlib` + :mod:`platform`, so they always run.
"""

from __future__ import annotations

import pathlib
import platform
import sys


try:
    import torch as _torch
except ImportError:  # pragma: no cover — torch-less CI matrices
    _torch = None

_IS_WINDOWS = platform.system() == "Windows"

# Every module spelling a pickled `GLOBAL` may carry. The running
# interpreter's own spelling is unioned in so that a future stdlib move
# keeps "save and reload with the same interpreter" working unassisted.
_PICKLE_MODULES: tuple[str, ...] = tuple(
    dict.fromkeys(("pathlib", "pathlib._local", pathlib.PosixPath.__module__))
)


def build_safe_global_targets(is_windows: bool) -> dict[str, type]:
    """Map every pickled ``pathlib`` name to the class to unpickle it as.

    ``PosixPath.__new__`` raises ``UnsupportedOperation`` when
    ``os.name == "nt"``, so on Windows the ``PosixPath`` keys must resolve
    to ``WindowsPath`` — that is the whole point of the shim. On POSIX the
    classes stay as they are.

    Kept as a pure function of *is_windows* so the Windows mapping can be
    asserted from a POSIX test run without reloading this module (a reload
    would re-apply the aliases below to the live interpreter).
    """
    posix_target: type = pathlib.WindowsPath if is_windows else pathlib.PosixPath
    windows_target: type = pathlib.WindowsPath
    return {
        f"{module}.{name}": target
        for module in _PICKLE_MODULES
        for name, target in (
            ("PosixPath", posix_target),
            ("WindowsPath", windows_target),
        )
    }


#: Mapping of fully-qualified pickle name -> class the unpickler should use.
SAFE_GLOBAL_TARGETS: dict[str, type] = build_safe_global_targets(_IS_WINDOWS)


def _supports_named_safe_globals() -> bool:
    """Whether ``add_safe_globals`` accepts ``(callable, name)`` tuples.

    Added in torch 2.6. ``piper-train``'s own distribution metadata
    (``src/python/pyproject.toml``) does not pin torch — the ``train``
    extra only requires ``pytorch-lightning>=2.4.0`` — so an install can
    legitimately resolve an older torch. Those releases default
    ``weights_only`` to ``False`` anyway, which makes the bare
    registration below harmless rather than merely best-effort.
    """
    if _torch is None:  # pragma: no cover — guarded by caller
        return False
    try:
        from torch.torch_version import TorchVersion  # noqa: PLC0415

        return TorchVersion(_torch.__version__) >= "2.6"
    except Exception:  # pragma: no cover — unexpected torch internals
        return False


if _torch is not None:
    if _supports_named_safe_globals():
        _torch.serialization.add_safe_globals(
            [(cls, name) for name, cls in SAFE_GLOBAL_TARGETS.items()]
        )
    else:  # pragma: no cover — legacy torch, weights_only defaults to False
        _torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])


def apply_windows_pathlib_aliases() -> None:
    """Route ``PosixPath`` to ``WindowsPath`` on Windows. No-op elsewhere.

    This covers the ``weights_only=False`` load paths, which use the
    stock :mod:`pickle` unpickler and therefore ignore torch's safe-global
    registry entirely: they ``getattr`` the class off the module named in
    the pickle.

    Rebinding ``pathlib.PosixPath`` alone is not enough. A checkpoint
    written under CPython 3.13 spells its ``GLOBAL`` as
    ``pathlib._local PosixPath``, so the unpickler reads
    ``sys.modules["pathlib._local"].PosixPath`` and sails straight past
    the alias on the public module. Both have to be rebound.

    Rebinding is safe for ordinary path construction: ``Path.__new__``
    selects ``WindowsPath`` when ``os.name == "nt"`` regardless, so on
    Windows this changes nothing about ``Path()`` dispatch.
    """
    if not _IS_WINDOWS:
        return
    pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[misc, assignment]
    _local = sys.modules.get("pathlib._local")
    if _local is not None:
        _local.PosixPath = pathlib.WindowsPath  # type: ignore[attr-defined]


apply_windows_pathlib_aliases()
