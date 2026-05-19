"""Unit tests for scripts/check_model_sha256_manifest.py (M2 T-005)."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_model_sha256_manifest.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_model_sha256_manifest",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _well_formed_manifest_toml() -> str:
    """Return a minimal TOML that satisfies every gate in check_manifest.

    Mirrors the real manifest's required surfaces but with placeholder
    hashes only. Tests start from this body and mutate it to introduce
    drift on purpose.
    """
    body = """
        [meta]
        spec_version = "1.0"
        canonical_source = "docs/spec/model-sha256-manifest.toml"
        hash_algorithm = "SHA-256"
        hash_encoding = "lowercase hex, 64 chars"
        update_policy = "n/a in test"
        forward_compat_policy = "strict"
    """
    for name in [
        "multilingual-6lang-base",
        "multilingual-6lang-mb-istft",
        "tsukuyomi-6lang-v2",
        "tsukuyomi-mb-istft",
        "css10-ja-6lang",
        "speaker-encoder-ecapa-tdnn",
    ]:
        body += textwrap.dedent(f"""
            [[models]]
            name = "{name}"
            description = "test entry"

            [[models.artifacts]]
            filename = "{name}.onnx"
            sha256 = "<computed-on-publish>"
        """)
    return textwrap.dedent(body)


def test_real_manifest_passes(mod, capsys: pytest.CaptureFixture):
    """The committed manifest must pass the structural gate.

    A drift here means CLAUDE.md and the manifest disagree about which
    models exist — exactly what this gate is meant to surface.
    """
    rc = mod.main([])
    captured = capsys.readouterr()
    assert rc == 0, f"Committed manifest unexpectedly failed:\n{captured.err}"
    assert "Collected manifest entries" in captured.err


def test_well_formed_fixture_passes(mod, tmp_path: Path, capsys):
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_well_formed_manifest_toml())
    rc = mod.main(["--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert rc == 0, f"Well-formed fixture failed:\n{captured.err}"


def test_missing_manifest_returns_2(mod, tmp_path: Path, capsys):
    rc = mod.main(["--manifest", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert "manifest missing" in capsys.readouterr().err


def test_malformed_toml_returns_2(mod, tmp_path: Path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[meta\nthis is not toml")
    assert mod.main(["--manifest", str(bad)]) == 2


def test_missing_meta_key_returns_1(mod, tmp_path: Path, capsys):
    body = _well_formed_manifest_toml().replace(
        'forward_compat_policy = "strict"\n', ""
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    assert rc == 1
    assert "forward_compat_policy" in capsys.readouterr().err


def test_unexpected_model_entry_returns_1(mod, tmp_path: Path, capsys):
    """Adding a model only to the manifest (not CLAUDE.md) is drift."""
    body = _well_formed_manifest_toml() + textwrap.dedent("""
        [[models]]
        name = "rogue-model"
        description = "should fail"

        [[models.artifacts]]
        filename = "rogue.onnx"
        sha256 = "<computed-on-publish>"
    """)
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "unexpected entries" in captured.err
    assert "rogue-model" in captured.err


def test_missing_expected_model_returns_1(mod, tmp_path: Path, capsys):
    body = _well_formed_manifest_toml()
    # Drop the css10 block (3 consecutive non-blank lines + leading newline).
    lines = body.splitlines(keepends=True)
    out: list[str] = []
    skip = 0
    for line in lines:
        if "css10-ja-6lang" in line:
            # Skip this and the next 5 lines (model + artifact stanza).
            skip = 5
            continue
        if skip > 0:
            skip -= 1
            continue
        out.append(line)
    manifest = tmp_path / "m.toml"
    manifest.write_text("".join(out))
    rc = mod.main(["--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "missing expected entries" in captured.err
    assert "css10-ja-6lang" in captured.err


def test_real_sha256_value_accepted(mod, tmp_path: Path):
    """A computed 64-char lowercase hex MUST be accepted (post-publish path)."""
    real = "a" * 64
    body = _well_formed_manifest_toml().replace(
        'sha256 = "<computed-on-publish>"',
        f'sha256 = "{real}"',
        1,
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    assert mod.main(["--manifest", str(manifest)]) == 0


def test_uppercase_sha256_rejected(mod, tmp_path: Path, capsys):
    """spec [meta].hash_encoding pins lowercase hex; uppercase MUST fail."""
    upper = "A" * 64
    body = _well_formed_manifest_toml().replace(
        'sha256 = "<computed-on-publish>"',
        f'sha256 = "{upper}"',
        1,
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    assert rc == 1
    assert "64-char lowercase hex" in capsys.readouterr().err


def test_wrong_length_sha256_rejected(mod, tmp_path: Path, capsys):
    body = _well_formed_manifest_toml().replace(
        'sha256 = "<computed-on-publish>"',
        'sha256 = "abc123"',
        1,
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    assert rc == 1
    assert "64-char lowercase hex" in capsys.readouterr().err


def test_forward_compat_within_known_schema(mod, tmp_path: Path):
    """schema_version <= MAX_KNOWN_SCHEMA_VERSION must pass."""
    assert mod.MAX_KNOWN_SCHEMA_VERSION >= 2
    body = _well_formed_manifest_toml().replace(
        'spec_version = "1.0"', f'spec_version = "{mod.MAX_KNOWN_SCHEMA_VERSION}.0"'
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    assert mod.main(["--manifest", str(manifest)]) == 0


def test_forward_compat_beyond_known_schema_fails(mod, tmp_path: Path, capsys):
    """Bumping schema_version past MAX_KNOWN MUST fail with a guidance message.

    This is a reverse-direction safety: the gate cannot auto-trust a
    future schema (which may add new required keys); it forces the script
    to be bumped in the same PR.
    """
    body = _well_formed_manifest_toml().replace(
        'spec_version = "1.0"',
        f'spec_version = "{mod.MAX_KNOWN_SCHEMA_VERSION + 1}.0"',
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "MAX_KNOWN_SCHEMA_VERSION" in err


def test_silent_zero_warning_when_models_empty(mod, tmp_path: Path, capsys):
    body = textwrap.dedent("""
        [meta]
        spec_version = "1.0"
        canonical_source = "docs/spec/model-sha256-manifest.toml"
        hash_algorithm = "SHA-256"
        hash_encoding = "lowercase hex, 64 chars"
        update_policy = "n/a"
        forward_compat_policy = "strict"
    """)
    manifest = tmp_path / "m.toml"
    manifest.write_text(body)
    rc = mod.main(["--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert rc == 1  # missing every expected model
    assert "Collected manifest entries (models=0" in captured.err
    assert "::warning::" in captured.err
