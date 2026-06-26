"""Cross-platform compatibility shims.

Loaded eagerly when :mod:`piper_train` is imported so all entry points
(`export_onnx`, `infer`, `export_torchscript`, etc.) transparently
handle Linux-produced checkpoints on Windows.

Issues addressed:

- **PosixPath instantiation on Windows**: Lightning serialises
  `pathlib.PosixPath` instances inside checkpoints. Without the
  monkey-patch below, `torch.load(...)` on Windows raises
  `UnsupportedOperation: cannot instantiate 'PosixPath' on your system`.
- **PyTorch 2.6+ weights_only=True restriction**: `pathlib` classes
  must be registered as safe globals to allow unpickling.

This module has no public API; importing it for the side-effects is the
contract.

torch is imported lazily inside a `try`/`except ImportError` because
:mod:`piper_train` is also imported by lightweight CI jobs that don't
install torch (e.g. dataset / utility tests). The PosixPath alias
itself only needs :mod:`pathlib` + :mod:`platform`, so it always runs.
"""

from __future__ import annotations

import pathlib
import platform


try:
    import torch as _torch
except ImportError:  # pragma: no cover — torch-less CI matrices
    _torch = None

if _torch is not None:
    _torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])

if platform.system() == "Windows":
    pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[misc, assignment]
