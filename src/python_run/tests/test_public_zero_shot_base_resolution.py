"""The public base must use its versioned TTS graph and matching vocabulary."""

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from piper_plus.api._model_resolver import resolve_model
from piper_plus.download import PIPER_PLUS_VOICES, download_model


REVISION = "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1"
REPO = "ayousanz/piper-plus-base"
RELEASE = "releases/zs-v1"


@pytest.mark.parametrize("name", ["base", "zero-shot-base-zs-v1", REPO])
def test_api_base_uses_pinned_release_pair(name, tmp_path):
    calls = []

    def download(repo, filename, **kwargs):
        calls.append((repo, filename, kwargs.get("revision")))
        target = Path(kwargs["local_dir"]) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model" if filename.endswith(".onnx") else b"{}")
        return str(target)

    with (
        patch("huggingface_hub.hf_hub_download", side_effect=download),
        patch("huggingface_hub.list_repo_files") as listing,
    ):
        model, config = resolve_model(name, cache_dir=tmp_path)
    assert calls == [
        (REPO, f"{RELEASE}/base.onnx", REVISION),
        (REPO, f"{RELEASE}/base.onnx.json", REVISION),
    ]
    assert model.read_bytes() == b"model" and config.read_bytes() == b"{}"
    assert model.parent == config.parent
    listing.assert_not_called()


def test_api_base_cached_pair_is_usable_offline(tmp_path):
    directory = tmp_path / "ayousanz--piper-plus-base" / REVISION / RELEASE
    directory.mkdir(parents=True)
    (directory / "base.onnx").write_bytes(b"model")
    (directory / "base.onnx.json").write_bytes(b"{}")
    with patch("huggingface_hub.hf_hub_download") as download:
        model, config = resolve_model("base", cache_dir=tmp_path, download=False)
    assert model == directory / "base.onnx"
    assert config == directory / "base.onnx.json"
    download.assert_not_called()


def test_cli_download_preserves_remote_subdirectory_and_local_pair(tmp_path):
    calls = []
    with patch(
        "piper_plus.download.urlopen",
        side_effect=lambda url: calls.append(url) or io.BytesIO(b"test"),
    ):
        model, config = download_model("base", tmp_path)
    prefix = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{RELEASE}/"
    assert set(calls) == {prefix + "base.onnx", prefix + "base.onnx.json"}
    assert model == tmp_path / "base.onnx"
    assert config == tmp_path / "base.onnx.json"
    assert model.is_file() and config.is_file()
    info = PIPER_PLUS_VOICES["multilingual-zero-shot-base-zs-v1"]
    assert info["num_speakers"] == 571
    assert info["quality"] == "experimental"


def test_api_base_does_not_reuse_legacy_cache(tmp_path):
    from piper_plus.api._model_resolver import ModelNotFoundError

    legacy = tmp_path / "ayousanz--piper-plus-base"
    legacy.mkdir()
    (legacy / "base.onnx").write_bytes(b"old graph")
    (legacy / "config.json").write_text("{}")
    with pytest.raises(ModelNotFoundError, match="download=False"):
        resolve_model("base", cache_dir=tmp_path, download=False)


def test_api_repairs_incomplete_pinned_cache(tmp_path):
    directory = tmp_path / "ayousanz--piper-plus-base" / REVISION / RELEASE
    directory.mkdir(parents=True)
    (directory / "base.onnx").write_bytes(b"incomplete old download")

    def download(repo, filename, **kwargs):
        target = Path(kwargs["local_dir"]) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new" if filename.endswith(".onnx") else b"{}")
        return str(target)

    with patch("huggingface_hub.hf_hub_download", side_effect=download):
        model, config = resolve_model("base", cache_dir=tmp_path)
    assert model.read_bytes() == b"new"
    assert config.read_bytes() == b"{}"
