"""Regression tests for piper_train._compat cross-platform shims.

Issues guarded:

- PosixPath instantiation error on Windows when loading Linux-saved
  Lightning checkpoints (`torch.load` would raise
  `UnsupportedOperation: cannot instantiate 'PosixPath' on your system`).
- PyTorch 2.6+ weights_only=True requires pathlib classes to be
  registered as safe globals.

If any test here fails, do NOT skip — the breakage means
`torch.load(checkpoint, ...)` will fail on Windows for downstream
users. Fix `piper_train/_compat.py` instead.
"""

from __future__ import annotations

import pathlib
import platform

import pytest


def test_compat_module_imports_without_error() -> None:
    """`piper_train._compat` must import cleanly on every platform."""
    from piper_train import _compat  # noqa: F401


def test_piper_train_import_triggers_compat() -> None:
    """`import piper_train` must eagerly load the compat shim.

    Otherwise CLI entry points that only do `from piper_train import X`
    (not `from piper_train._compat ...`) will miss the PosixPath patch.

    Skipped when torch isn't installed (some CI matrices import
    piper_train for utility tests only — see _compat.py docstring).
    """
    import piper_train  # noqa: F401

    # _compat side-effect: pathlib classes registered as torch safe globals
    ts = pytest.importorskip("torch.serialization")

    # torch >= 2.11 exposes `get_safe_globals` as a stable public API;
    # earlier releases used the underscore-prefixed `_get_safe_globals`.
    # Accept either so this regression test stays robust across the
    # supported torch range.
    getter = getattr(ts, "get_safe_globals", None) or getattr(
        ts, "_get_safe_globals", None
    )
    assert getter is not None, (
        "torch.serialization exposes neither `get_safe_globals` nor "
        "`_get_safe_globals`; torch internals have changed and this "
        "regression test must be updated to match."
    )
    safe_globals = getter()
    safe_names = {getattr(cls, "__name__", repr(cls)) for cls in safe_globals}
    assert "PosixPath" in safe_names, (
        "pathlib.PosixPath must be in torch safe globals after `import piper_train`. "
        "Did piper_train/__init__.py stop importing _compat?"
    )
    assert "WindowsPath" in safe_names, (
        "pathlib.WindowsPath must be in torch safe globals after `import piper_train`."
    )


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="PosixPath → WindowsPath patch only applies on Windows",
)
def test_posixpath_routed_to_windowspath_on_windows() -> None:
    """On Windows, `pathlib.PosixPath` must resolve to `WindowsPath`.

    This makes pickled `PosixPath` instances inside Linux-produced
    Lightning checkpoints deserialise as `WindowsPath` instead of
    raising `UnsupportedOperation`.
    """
    import piper_train  # noqa: F401

    assert pathlib.PosixPath is pathlib.WindowsPath, (
        "piper_train._compat must alias pathlib.PosixPath to "
        "pathlib.WindowsPath on Windows."
    )


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="non-Windows must keep PosixPath untouched",
)
def test_posixpath_unchanged_on_non_windows() -> None:
    """On Linux / macOS, the compat shim must be a no-op for PosixPath."""
    import piper_train  # noqa: F401

    # PosixPath should still be PosixPath (not WindowsPath) on POSIX systems.
    assert pathlib.PosixPath is not pathlib.WindowsPath
    # And it should be instantiable as usual.
    p = pathlib.PosixPath("/tmp/example")
    assert str(p) == "/tmp/example"
