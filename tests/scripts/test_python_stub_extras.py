"""The piper-tts-plus stub relays the extras of piper-plus.

Since piper-plus 2.0.2 the base dependencies carry no ONNX Runtime: the
provider is chosen with the ``cpu`` or ``gpu`` extra, because both wheels
supply the same ``onnxruntime`` module. The stub (``src/python_stub``) relayed
only ``gpu`` and ``http``, so ``piper-tts-plus`` could not install a CPU
runtime at all.
"""

import tomllib
from pathlib import Path

import yaml
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
STUB = ROOT / "src" / "python_stub"
RUNTIME = ROOT / "src" / "python_run"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi-stub.yml"

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
    # onnxruntime-gpu for piper-tts-plus[gpu]. The floor is the first
    # piper-plus that has the cpu / gpu extras the stub relays.
    assert _project(STUB)["dependencies"] == ["piper-plus>=2.0.2"]


def test_stub_version_is_newer_than_the_last_redirect_without_cpu():
    # pyproject reads the version from this file; without it the stub does not
    # build. 1.12.0 is the last published stub, which has no cpu extra.
    version = (STUB / "VERSION").read_text(encoding="utf-8").strip()
    assert Version(version) > Version("1.12.0")


def test_publish_runs_only_by_hand_after_the_install_check():
    jobs = yaml.load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"), yaml.BaseLoader)[
        "jobs"
    ]
    publish = jobs["publish"]

    assert publish["needs"] == "verify"
    assert jobs["verify"]["needs"] == "build"
    assert "github.event_name == 'workflow_dispatch'" in publish["if"]
    # The environment name is part of the PyPI Trusted Publisher entry.
    assert publish["environment"]["name"] == "pypi-stub"
    install = "\n".join(step.get("run", "") for step in jobs["verify"]["steps"])
    assert '"${wheel}[cpu]"' in install
    assert '"${wheel}[gpu]"' in install


def test_stub_readme_names_a_provider_extra():
    readme = (STUB / "README.md").read_text(encoding="utf-8")
    assert 'pip install "piper-plus[cpu]"' in readme
    assert 'pip install "piper-plus[gpu]"' in readme
    assert 'pip install "piper-tts-plus[cpu]"' in readme
