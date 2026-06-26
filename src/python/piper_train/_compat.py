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
"""

from __future__ import annotations

import pathlib
import platform

import torch

torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])

if platform.system() == "Windows":
    pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[misc, assignment]
