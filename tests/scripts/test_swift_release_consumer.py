"""Exercise the public SwiftPM consumer preparation without requiring macOS."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_swift_release_consumer.py"


def prepare(tmp_path, version):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            version,
            "--destination",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_consumer_pins_public_version_and_requires_nonempty_phonemes(tmp_path):
    result = prepare(tmp_path, "2.0.0")
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "Package.swift").read_text(encoding="utf-8")
    assert (
        '.package(url: "https://github.com/ayutaz/piper-plus", exact: "2.0.0")'
        in manifest
    )
    assert '.product(name: "PiperPlusG2P", package: "piper-plus")' in manifest
    assert "path:" not in manifest
    source = (tmp_path / "Sources/ReleaseConsumer/main.swift").read_text(
        encoding="utf-8"
    )
    for language in [".japanese", ".english", ".chinese"]:
        assert language in source
    assert "result.tokens.isEmpty" in source
    assert "fatalError" in source


@pytest.mark.parametrize("version", ["dev", "v2.0.0", "2.0", '2.0.0")', "2.0.0\n"])
def test_invalid_version_does_not_write_consumer(tmp_path, version):
    result = prepare(tmp_path, version)
    assert result.returncode != 0
    assert "Invalid release version" in result.stderr
    assert not (tmp_path / "Package.swift").exists()


def test_public_swift_consumer_workflow_runs_actual_release_manifest():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-swift-consumer.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = workflow["jobs"]["verify"]["steps"]
    checkout = next(
        s for s in steps if s.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "v${{ inputs.version }}"
    commands = "\n".join(s.get("run", "") for s in steps)
    assert "check_swift_release_consumer.py" in commands
    assert "swift package resolve" in commands
    assert "swift build" in commands
    assert "swift run --skip-build ReleaseConsumer" in commands
    assert "Package.ci.swift" not in commands
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "tests/scripts/test_swift_release_consumer.py" in ci
