"""Linux training metadata must load on Windows CPU without patching pathlib."""

import pathlib

import pytest


torch = pytest.importorskip(
    "torch",
    reason="Checkpoint preparation needs the train extra; lightweight Windows CI omits it.",
)


class SavedPosixPath:
    def __reduce__(self):
        return pathlib.PosixPath, ("/training/dataset",)


class SavedWindowsPath:
    def __reduce__(self):
        return pathlib.WindowsPath, ("C:/training/dataset",)


@pytest.mark.parametrize("metadata_path", [SavedPosixPath(), SavedWindowsPath()])
def test_loads_foreign_paths_without_global_pathlib_changes(tmp_path, metadata_path):
    from piper_train.checkpoint_io import load_checkpoint

    original_posix = pathlib.PosixPath
    original_windows = pathlib.WindowsPath
    checkpoint = tmp_path / "model.ckpt"
    torch.save(
        {
            "hyper_parameters": {"dataset": metadata_path},
            "state_dict": {"x": torch.ones(2)},
        },
        checkpoint,
    )
    loaded = load_checkpoint(checkpoint)
    assert isinstance(loaded["hyper_parameters"]["dataset"], pathlib.Path)
    assert torch.equal(loaded["state_dict"]["x"], torch.ones(2))
    assert pathlib.PosixPath is original_posix
    assert pathlib.WindowsPath is original_windows
