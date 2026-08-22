"""Regression tests for the pathlib pickle-name registration in `_compat`.

Guards the bug where `torch.load` rejected a perfectly valid checkpoint
with::

    _pickle.UnpicklingError: Weights only load failed.
        WeightsUnpickler error: Unsupported global:
        GLOBAL pathlib.PosixPath was not an allowed global by default.

even though `piper_train._compat` had "already registered" pathlib as a
safe global.

The cause is that `add_safe_globals([cls])` derives its registry key from
`cls.__module__` in the *reading* interpreter, while the unpickler looks
up the string recorded by the *writing* one. CPython 3.13 moved the
concrete path classes to `pathlib._local` (3.14 moved them back), so the
two names disagree across Python versions and neither side is "wrong".

These tests therefore synthesise checkpoints that pickle each spelling
explicitly, instead of trusting whatever the running interpreter happens
to emit. On any single Python version a native-spelling-only test would
pass while the cross-version case stays broken.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import pickletools
import subprocess
import sys
import types
import zipfile

import pytest


# Import order matters: `_get_user_allowed_globals()` resolves bare-form
# entries lazily, so `piper_train` must be imported while `pathlib` is
# still pristine. Importing it after a spelling patch would let the proxy
# class leak into the process-wide registry and poison the whole session.
torch = pytest.importorskip("torch", reason="torch required for checkpoint I/O")

import piper_train  # noqa: E402, F401  (side-effect: loads _compat)
from piper_train import _compat  # noqa: E402


#: Every module spelling a checkpoint's pickle may use for path classes.
PICKLE_SPELLINGS = ("pathlib", "pathlib._local")


@contextlib.contextmanager
def _pickled_as(module_name: str):
    """Yield a `PosixPath` subclass that pickles as ``<module_name>.PosixPath``.

    `pickle` refuses to serialise a class whose qualified name does not
    resolve back to that same object, so the proxy has to be installed in
    the target module for the duration of the dump.

    The proxy subclasses the *real* `pathlib.PosixPath` rather than
    `PurePosixPath` on purpose: while the patch is in place,
    `pathlib.Path()` still reads the module-level `PosixPath` to pick its
    concrete class, and a pure-path proxy would break unrelated code that
    happens to construct a path inside the window.
    """

    class _Proxy(pathlib.PosixPath):
        pass

    _Proxy.__module__ = module_name
    _Proxy.__qualname__ = "PosixPath"
    _Proxy.__name__ = "PosixPath"
    assert issubclass(_Proxy, pathlib.Path), (
        "proxy must subclass the concrete Path so pathlib.Path() keeps working"
    )

    module = sys.modules.get(module_name)
    created = module is None
    if created:
        # `pathlib._local` does not exist before CPython 3.13; a stub is
        # enough for pickle, which only needs the attribute lookup.
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    previous = getattr(module, "PosixPath", None)
    module.PosixPath = _Proxy
    try:
        yield _Proxy
    finally:
        if created:
            sys.modules.pop(module_name, None)
        elif previous is not None:
            module.PosixPath = previous


def _write_checkpoint(tmp_path, spelling: str):
    """Write a Lightning-shaped checkpoint pickling *spelling*'s PosixPath."""
    target = tmp_path / f"ckpt-{spelling.replace('.', '_')}.ckpt"
    with _pickled_as(spelling) as proxy:
        torch.save(
            {
                "epoch": 74,
                "global_step": 500034,
                "hyper_parameters": {"dataset": [proxy("/data/piper/dataset.jsonl")]},
                "state_dict": {"weight": torch.zeros(2, 2)},
            },
            target,
        )
    return target


def _pickle_globals(path) -> list[str]:
    """Return the GLOBAL operands recorded in the checkpoint's data.pkl."""
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("data.pkl"))
        payload = archive.read(name)
    return [
        arg
        for opcode, arg, _pos in pickletools.genops(payload)
        if opcode.name in ("GLOBAL", "STACK_GLOBAL") and arg
    ]


@pytest.mark.unit
@pytest.mark.parametrize("spelling", PICKLE_SPELLINGS)
def test_fixture_emits_requested_pickle_spelling(tmp_path, spelling: str) -> None:
    """The fixture must really emit the spelling it claims to.

    Without this, a proxy that silently fell back to the interpreter's
    native spelling would make every other test in this file pass while
    testing nothing.
    """
    checkpoint = _write_checkpoint(tmp_path, spelling)
    path_globals = [g for g in _pickle_globals(checkpoint) if "PosixPath" in g]

    assert path_globals == [f"{spelling} PosixPath"], (
        f"expected the checkpoint to pickle exactly '{spelling} PosixPath', "
        f"got {path_globals!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("spelling", PICKLE_SPELLINGS)
def test_checkpoint_loads_under_torch_weights_only_default(
    tmp_path, spelling: str
) -> None:
    """`torch.load` must accept both spellings at its default weights_only.

    This is the user-visible failure from issue #616's environment: the
    published checkpoint was written under CPython <= 3.12 and could not
    be read at all under 3.13.
    """
    checkpoint = _write_checkpoint(tmp_path, spelling)

    unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint)
    assert unsafe == [], (
        f"pathlib globals spelled '{spelling}' are not registered as safe: {unsafe}. "
        "piper_train._compat must register every spelling, not just the one "
        "the running interpreter happens to use."
    )

    loaded = torch.load(checkpoint, map_location="cpu")
    restored = loaded["hyper_parameters"]["dataset"][0]
    assert isinstance(restored, pathlib.PurePath)
    assert restored.name == "dataset.jsonl"


@pytest.mark.unit
@pytest.mark.parametrize("spelling", PICKLE_SPELLINGS)
def test_checkpoint_loads_via_lightning_pl_load(tmp_path, spelling: str) -> None:
    """The Lightning load path must work too, not just bare `torch.load`.

    `VitsModel.load_from_checkpoint` reaches torch through
    `lightning_fabric.utilities.cloud_io._load`, which passes
    `weights_only` explicitly. Pinning only `torch.load` would leave the
    path that actually broke in `export_onnx.py` unguarded.
    """
    cloud_io = pytest.importorskip(
        "lightning_fabric.utilities.cloud_io",
        reason="pytorch-lightning required for the Lightning load path",
    )
    checkpoint = _write_checkpoint(tmp_path, spelling)

    loaded = cloud_io._load(checkpoint, map_location="cpu", weights_only=None)

    assert loaded["epoch"] == 74
    assert loaded["hyper_parameters"]["dataset"][0].name == "dataset.jsonl"


@pytest.mark.unit
def test_registration_happens_on_piper_train_import() -> None:
    """`import piper_train` alone must register all four names.

    Runs in a subprocess because the safe-globals registry is process
    global: any earlier test (or conftest) that registered pathlib would
    make an in-process assertion pass regardless of what `_compat` does.
    """
    probe = (
        "import json;"
        "import piper_train;"
        "from torch._weights_only_unpickler import _get_user_allowed_globals as g;"
        "print(json.dumps(sorted(k for k in g() if 'Path' in k)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    registered = set(json.loads(result.stdout.strip().splitlines()[-1]))

    expected = {
        f"{module}.{name}"
        for module in PICKLE_SPELLINGS
        for name in ("PosixPath", "WindowsPath")
    }
    assert expected <= registered, (
        f"missing safe-global names after `import piper_train`: "
        f"{sorted(expected - registered)}"
    )


@pytest.mark.unit
def test_windows_alias_table_covers_both_spellings() -> None:
    """On Windows, both PosixPath spellings must resolve to WindowsPath.

    Asserted through the pure builder so this runs on POSIX too: reloading
    `_compat` with a faked platform would rebind `pathlib.PosixPath` in
    the live interpreter and corrupt the rest of the session.
    """
    windows_targets = _compat.build_safe_global_targets(is_windows=True)

    for spelling in PICKLE_SPELLINGS:
        assert windows_targets[f"{spelling}.PosixPath"] is pathlib.WindowsPath, (
            f"'{spelling}.PosixPath' must unpickle as WindowsPath on Windows; "
            "otherwise PosixPath.__new__ raises UnsupportedOperation there."
        )
        assert windows_targets[f"{spelling}.WindowsPath"] is pathlib.WindowsPath


@pytest.mark.unit
def test_posix_targets_are_instantiable_on_posix() -> None:
    """On POSIX the registered classes must stay usable as real paths."""
    posix_targets = _compat.build_safe_global_targets(is_windows=False)

    for spelling in PICKLE_SPELLINGS:
        cls = posix_targets[f"{spelling}.PosixPath"]
        assert cls is pathlib.PosixPath
        assert cls("/tmp/example").name == "example"


@pytest.mark.unit
def test_apply_windows_pathlib_aliases_is_noop_on_posix() -> None:
    """Calling the alias helper on POSIX must not rebind anything."""
    if sys.platform == "win32":  # pragma: no cover — POSIX-only assertion
        pytest.skip("aliases are intentionally applied on Windows")

    before = pathlib.PosixPath
    _compat.apply_windows_pathlib_aliases()

    assert pathlib.PosixPath is before
    assert pathlib.PosixPath is not pathlib.WindowsPath
