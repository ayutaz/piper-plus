"""The piper-tts-plus stub relays the extras of piper-plus.

Since piper-plus 2.0.2 the base dependencies carry no ONNX Runtime: the
provider is chosen with the ``cpu`` or ``gpu`` extra, because both wheels
supply the same ``onnxruntime`` module. The stub (``src/python_stub``) relayed
only ``gpu`` and ``http``, so ``piper-tts-plus`` could not install a CPU
runtime at all.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUB = ROOT / "src" / "python_stub"
RUNTIME = ROOT / "src" / "python_run"

# Extras of piper-plus that are for its own test suite, not for users.
NOT_RELAYED = {"test"}


def _project(directory: Path) -> dict:
    with (directory / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]


def test_stub_relays_every_user_extra_of_piper_plus():
    runtime_extras = set(_project(RUNTIME)["optional-dependencies"]) - NOT_RELAYED
    stub_extras = _project(STUB)["optional-dependencies"]

    assert {"cpu", "gpu"} <= runtime_extras
    assert set(stub_extras) == runtime_extras
    for name in runtime_extras:
        assert stub_extras[name] == [f"piper-plus[{name}]"], name


def test_stub_base_dependency_selects_no_provider():
    # A provider in the base dependencies would install the CPU wheel next to
    # onnxruntime-gpu for piper-tts-plus[gpu].
    assert _project(STUB)["dependencies"] == ["piper-plus"]


def test_stub_readme_names_a_provider_extra():
    readme = (STUB / "README.md").read_text(encoding="utf-8")
    assert 'pip install "piper-plus[cpu]"' in readme
    assert 'pip install "piper-plus[gpu]"' in readme
    assert 'pip install "piper-tts-plus[cpu]"' in readme
