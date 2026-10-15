"""Exercise actual artifact schema, mismatch failures and atomic updates."""

import hashlib
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bundle(tmp_path):
    artifact = tmp_path / "voice.onnx"
    artifact.write_bytes(b"official artifact")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        '[[models]]\nname = "voice"\ndescription = "fixture"\n'
        '[[models.artifacts]]\nfilename = "voice.onnx"\n'
        f'sha256 = "{hashlib.sha256(artifact.read_bytes()).hexdigest()}"\nbytes = {artifact.stat().st_size}\n'
        '[[models.artifacts]]\nfilename = "voice.onnx.json"\nrole = "config"\n'
        'sha256 = "<computed-on-publish>"\nbytes = 0\n'
        '[[models]]\nname = "other"\ndescription = "untouched"\n'
        '[[models.artifacts]]\nfilename = "other.onnx"\n'
        'sha256 = "<computed-on-publish>"\nbytes = 0\n',
        encoding="utf-8",
    )
    return artifact, manifest


def test_checksum_detects_corruption(bundle, monkeypatch):
    artifact, manifest = bundle
    mod = load("verify_model_checksums")
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    assert mod.main(["--model", str(artifact), "--name", "voice"]) == 0
    artifact.write_bytes(b"corrupted bytes")
    assert mod.main(["--model", str(artifact), "--name", "voice"]) == 1


def test_unknown_requires_explicit_opt_in(bundle, monkeypatch):
    artifact, manifest = bundle
    mod = load("verify_model_checksums")
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    unknown = artifact.with_name("custom.onnx")
    unknown.write_bytes(b"custom")
    assert mod.main(["--model", str(unknown)]) == 1
    assert mod.main(["--model", str(unknown), "--allow-custom"]) == 0


def test_nested_manifest_print(bundle, monkeypatch, capsys):
    _, manifest = bundle
    mod = load("verify_model_checksums")
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    assert mod.main(["--print-manifest"]) == 0
    assert "voice/voice.onnx:" in capsys.readouterr().out


def test_update_nested_artifacts_without_changing_other_models(bundle, monkeypatch):
    artifact, manifest = bundle
    mod = load("auto_update_model_manifest")
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    artifact.write_bytes(b"updated")
    config = artifact.with_suffix(".onnx.json")
    config.write_bytes(b"{}")
    assert (
        mod.main(
            [
                "--name",
                "voice",
                "--onnx",
                str(artifact),
                "--config",
                str(config),
                "--force",
            ]
        )
        == 0
    )
    models = tomllib.loads(manifest.read_text())["models"]
    assert models[0]["artifacts"][0]["sha256"] == hashlib.sha256(b"updated").hexdigest()
    assert models[0]["artifacts"][1]["bytes"] == 2
    assert models[1]["artifacts"][0]["sha256"] == "<computed-on-publish>"


def test_missing_artifact_update_fails_without_partial_write(bundle, monkeypatch):
    artifact, manifest = bundle
    mod = load("auto_update_model_manifest")
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    original = manifest.read_bytes()
    missing = artifact.with_name("wrong.json")
    missing.write_bytes(b"{}")
    assert (
        mod.main(
            [
                "--name",
                "voice",
                "--onnx",
                str(artifact),
                "--config",
                str(missing),
                "--force",
            ]
        )
        == 1
    )
    assert manifest.read_bytes() == original


@pytest.mark.parametrize(
    "mutation", ["empty", "placeholder", "negative", "missing", "bool"]
)
def test_published_requires_real_hash_and_positive_size(mutation):
    mod = load("check_model_sha256_manifest")
    data = tomllib.loads(
        (ROOT / "docs/spec/model-sha256-manifest.toml").read_text(encoding="utf-8")
    )
    model = next(m for m in data["models"] if m.get("publish_status") == "published")
    artifact = model["artifacts"][0]
    if mutation == "empty":
        artifact["sha256"] = ""
    elif mutation == "placeholder":
        artifact["sha256"] = "<computed-on-publish>"
    elif mutation == "negative":
        artifact["bytes"] = -1
    elif mutation == "bool":
        artifact["bytes"] = True
    else:
        artifact.pop("bytes")
    assert mod.check_manifest(data)
