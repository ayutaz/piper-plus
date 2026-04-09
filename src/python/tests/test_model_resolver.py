"""Tests for piper_plus._model_resolver -- model resolution and download logic.

Verifies direct path resolution, alias lookup, config auto-detection,
cache directory handling, and error conditions.
Follows t-wada TDD principles: behaviour-driven naming, Arrange-Act-Assert,
and triangulation with multiple resolution paths.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_has_huggingface_hub = importlib.util.find_spec("huggingface_hub") is not None

from piper_plus._model_resolver import (
    DEFAULT_CACHE_DIR,
    MODEL_ALIASES,
    ModelNotFoundError,
    _find_config,
    resolve_model,
)


# ===================================================================
# Direct file path resolution (Case 1)
# ===================================================================


@pytest.mark.unit
class TestResolveModelDirectPath:
    """resolve_model returns paths when model points to an existing ONNX file."""

    def test_resolves_existing_onnx_with_sibling_config(self, tmp_path):
        # Arrange
        onnx = tmp_path / "model.onnx"
        config = tmp_path / "config.json"
        onnx.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        # Act
        resolved_onnx, resolved_config = resolve_model(str(onnx))

        # Assert
        assert resolved_onnx == onnx
        assert resolved_config == config

    def test_resolves_existing_onnx_with_explicit_config(self, tmp_path):
        onnx = tmp_path / "model.onnx"
        config = tmp_path / "custom_config.json"
        onnx.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        resolved_onnx, resolved_config = resolve_model(
            str(onnx), config=str(config)
        )

        assert resolved_onnx == onnx
        assert resolved_config == config

    def test_resolves_onnx_with_suffix_json_pattern(self, tmp_path):
        """config.json at model.onnx.json is found."""
        onnx = tmp_path / "model.onnx"
        config = tmp_path / "model.onnx.json"
        onnx.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        _, resolved_config = resolve_model(str(onnx))

        assert resolved_config == config

    def test_raises_when_config_not_found_for_direct_path(self, tmp_path):
        onnx = tmp_path / "model.onnx"
        onnx.write_bytes(b"fake-onnx")
        # No config.json anywhere

        with pytest.raises(ModelNotFoundError, match="Config file not found"):
            resolve_model(str(onnx))


# ===================================================================
# _find_config
# ===================================================================


@pytest.mark.unit
class TestFindConfig:
    """_find_config locates config.json using several patterns."""

    def test_returns_explicit_config_when_provided(self, tmp_path):
        onnx = tmp_path / "model.onnx"
        config = tmp_path / "my_config.json"
        config.write_text("{}", encoding="utf-8")

        result = _find_config(onnx, str(config))

        assert result == config

    def test_raises_when_explicit_config_missing(self, tmp_path):
        onnx = tmp_path / "model.onnx"

        with pytest.raises(ModelNotFoundError, match="Config file not found"):
            _find_config(onnx, str(tmp_path / "nonexistent.json"))

    def test_finds_config_json_in_parent_dir(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        onnx = subdir / "model.onnx"
        config = subdir / "config.json"
        config.write_text("{}", encoding="utf-8")

        result = _find_config(onnx, None)

        assert result == config

    def test_raises_when_no_config_pattern_matches(self, tmp_path):
        onnx = tmp_path / "model.onnx"

        with pytest.raises(ModelNotFoundError, match="Config file not found"):
            _find_config(onnx, None)


# ===================================================================
# Alias resolution (Case 2)
# ===================================================================


@pytest.mark.unit
class TestResolveModelAlias:
    """resolve_model uses MODEL_ALIASES for known alias names."""

    def test_known_aliases_exist(self):
        assert "tsukuyomi" in MODEL_ALIASES
        assert "base" in MODEL_ALIASES

    def test_alias_has_required_keys(self):
        for alias_name, alias in MODEL_ALIASES.items():
            assert "repo_id" in alias, f"{alias_name} missing repo_id"
            assert "onnx_file" in alias, f"{alias_name} missing onnx_file"
            assert "config_file" in alias, f"{alias_name} missing config_file"

    @patch("piper_plus._model_resolver._download_from_hf")
    def test_alias_triggers_hf_download(self, mock_download, tmp_path):
        mock_onnx = tmp_path / "model.onnx"
        mock_config = tmp_path / "config.json"
        mock_onnx.write_bytes(b"fake")
        mock_config.write_text("{}", encoding="utf-8")
        mock_download.return_value = (mock_onnx, mock_config)

        result = resolve_model("tsukuyomi", cache_dir=tmp_path)

        assert result == (mock_onnx, mock_config)
        mock_download.assert_called_once()

    @patch("piper_plus._model_resolver._download_from_hf")
    def test_alias_passes_correct_repo_id(self, mock_download, tmp_path):
        mock_download.return_value = (tmp_path / "m.onnx", tmp_path / "c.json")

        resolve_model("tsukuyomi", cache_dir=tmp_path)

        call_args = mock_download.call_args[0]
        assert call_args[0] == "ayousanz/piper-plus-tsukuyomi-chan"


# ===================================================================
# HuggingFace repo ID resolution (Case 3)
# ===================================================================


@pytest.mark.unit
class TestResolveModelHuggingFaceRepoId:
    """resolve_model detects HuggingFace repo IDs (strings with '/')."""

    @patch("piper_plus._model_resolver._download_from_hf")
    def test_repo_id_with_slash_triggers_download(self, mock_download, tmp_path):
        mock_download.return_value = (tmp_path / "m.onnx", tmp_path / "c.json")

        resolve_model("user/my-model", cache_dir=tmp_path)

        mock_download.assert_called_once()
        assert mock_download.call_args[0][0] == "user/my-model"


# ===================================================================
# Cache directory lookup (Case 4)
# ===================================================================


@pytest.mark.unit
class TestResolveModelCacheDir:
    """resolve_model checks the cache directory for previously downloaded models."""

    def test_finds_model_in_cache_dir(self, tmp_path):
        cache_dir = tmp_path / "cache"
        model_dir = cache_dir / "mymodel"
        model_dir.mkdir(parents=True)
        onnx = model_dir / "model.onnx"
        config = model_dir / "config.json"
        onnx.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        resolved_onnx, resolved_config = resolve_model(
            "mymodel", cache_dir=cache_dir
        )

        assert resolved_onnx == onnx
        assert resolved_config == config


# ===================================================================
# Model not found
# ===================================================================


@pytest.mark.unit
class TestResolveModelNotFound:
    """resolve_model raises ModelNotFoundError for unresolvable names."""

    def test_raises_for_nonexistent_name(self, tmp_path):
        with pytest.raises(ModelNotFoundError, match="not found"):
            resolve_model("does_not_exist_at_all", cache_dir=tmp_path)

    def test_error_message_lists_available_aliases(self, tmp_path):
        with pytest.raises(ModelNotFoundError, match="tsukuyomi"):
            resolve_model("unknown_model", cache_dir=tmp_path)

    def test_download_false_raises_for_alias(self):
        """download=False prevents HuggingFace download even for known aliases."""
        with pytest.raises(ModelNotFoundError, match="download=False"):
            resolve_model("tsukuyomi", download=False, cache_dir=Path("/tmp/empty"))


# ===================================================================
# _download_from_hf
# ===================================================================


@pytest.mark.unit
class TestDownloadFromHf:
    """_download_from_hf handles download, caching, and race conditions."""

    @pytest.mark.skipif(
        not _has_huggingface_hub, reason="huggingface-hub not installed"
    )
    def test_returns_cached_files_without_redownload(self, tmp_path):
        """If files already exist in model_dir, no download is attempted."""
        from piper_plus._model_resolver import _download_from_hf

        model_dir = tmp_path / "user--repo"
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"cached-onnx")
        (model_dir / "config.json").write_text("{}", encoding="utf-8")

        onnx, config = _download_from_hf(
            "user/repo", "model.onnx", "config.json", tmp_path, download=True
        )

        assert onnx == model_dir / "model.onnx"
        assert config == model_dir / "config.json"

    def test_raises_when_download_disabled(self, tmp_path):
        from piper_plus._model_resolver import _download_from_hf

        with pytest.raises(ModelNotFoundError, match="download=False"):
            _download_from_hf(
                "user/repo", "model.onnx", "config.json", tmp_path, download=False
            )

    def test_raises_import_error_when_hf_hub_missing(self, tmp_path):
        from piper_plus._model_resolver import _download_from_hf

        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with pytest.raises(ImportError, match="huggingface-hub"):
                _download_from_hf(
                    "user/repo", "model.onnx", "config.json", tmp_path, download=True
                )


# ===================================================================
# DEFAULT_CACHE_DIR
# ===================================================================


@pytest.mark.unit
class TestDefaultCacheDir:
    """DEFAULT_CACHE_DIR is under ~/.cache/piper-plus/models."""

    def test_default_cache_dir_is_under_home(self):
        assert DEFAULT_CACHE_DIR == Path.home() / ".cache" / "piper-plus" / "models"


# ===================================================================
# ModelNotFoundError
# ===================================================================


@pytest.mark.unit
class TestModelNotFoundError:
    """ModelNotFoundError is a proper exception."""

    def test_is_an_exception(self):
        assert issubclass(ModelNotFoundError, Exception)

    def test_stores_message(self):
        err = ModelNotFoundError("test message")
        assert str(err) == "test message"
