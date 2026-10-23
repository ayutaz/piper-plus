"""Linux training metadata must load on Windows CPU without patching pathlib."""

import io
import pathlib

import pytest


torch = pytest.importorskip(
    "torch",
    reason="Checkpoint preparation needs the train extra; lightweight Windows CI omits it.",
)

pytestmark = pytest.mark.unit


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


def _pickled_path(module: str, name: str, saved: str) -> bytes:
    """``module.name(saved)`` を復元する protocol 2 の pickle を手で組む。

    pickle が書く module 名は保存した Python の版で決まる (3.13 は
    ``pathlib._local``、それより前は ``pathlib``)。実行中の版に依らず両方を
    検査するため、torch.save を通さずに byte 列を作る。
    """
    arg = saved.encode()
    return (
        b"\x80\x02c"
        + f"{module}\n{name}\n".encode()
        + b"X"
        + len(arg).to_bytes(4, "little")
        + arg
        + b"\x85R."
    )


@pytest.mark.parametrize("module", ["pathlib", "pathlib._local"])
@pytest.mark.parametrize(
    ("name", "saved"),
    [("PosixPath", "/training/dataset"), ("WindowsPath", "C:/training/dataset")],
)
def test_unpickles_paths_saved_by_any_python_version_as_native_path(
    module, name, saved
):
    from piper_train.checkpoint_io import load

    loaded = load(io.BytesIO(_pickled_path(module, name, saved)))
    assert type(loaded) is type(pathlib.Path())


@pytest.mark.parametrize("module", ["pathlib", "pathlib._local"])
@pytest.mark.parametrize("name", ["PosixPath", "WindowsPath"])
def test_concrete_path_classes_resolve_to_path_not_host_class(module, name):
    # 上の復元テストだけでは、host の pathlib が別 OS のクラスを作れる
    # 組み合わせ (例: Windows の 3.13) で変換漏れを見逃す。
    from piper_train.checkpoint_io import Unpickler


def test_training_entrypoints_load_checkpoints_through_checkpoint_io():
    # 別 OS で保存した ckpt の warm start / resume の読み直しは、素の
    # torch.load ではパス型を復元できずに落ちる。2 か所とも checkpoint_io を通す。
    import inspect

    from piper_train import __main__ as entry

    for func in (entry.load_multispeaker_checkpoint, entry.main):
        src = inspect.getsource(func)
        assert "load_checkpoint(" in src, func.__name__
        assert "torch.load(" not in src, func.__name__
