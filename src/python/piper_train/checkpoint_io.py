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
