"""Tests for piper_train.model_manager."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

from piper_train.model_manager import (
    find_voice,
    get_default_model_dir,
    list_models,
    resolve_model_path,
)

pytestmark = pytest.mark.unit


class TestFindVoice:
    def test_find_by_exact_key(self):
        voice = find_voice("ja_JP-tsukuyomi-chan-medium")
        assert voice is not None
        assert voice["key"] == "ja_JP-tsukuyomi-chan-medium"
        assert voice["name"] == "tsukuyomi-chan"

    def test_find_by_name(self):
        voice = find_voice("tsukuyomi-chan")
        assert voice is not None
        assert voice["key"] == "ja_JP-tsukuyomi-chan-medium"

    def test_find_by_alias(self):
        voice = find_voice("tsukuyomi")
        assert voice is not None
        assert voice["key"] == "ja_JP-tsukuyomi-chan-medium"

    def test_find_by_alias_css10(self):
        voice = find_voice("css10")
        assert voice is not None
        assert voice["key"] == "ja_JP-css10-6lang-medium"

    def test_find_not_found(self):
        assert find_voice("nonexistent-model") is None

    def test_find_empty_string(self):
        assert find_voice("") is None

    def test_find_none(self):
        assert find_voice(None) is None


class TestGetDefaultModelDir:
    def test_returns_nonempty(self):
        result = get_default_model_dir()
        assert result
        assert len(result) > 0

    def test_env_override(self):
        with patch.dict(os.environ, {"PIPER_MODEL_DIR": "/custom/path"}):
            assert get_default_model_dir() == "/custom/path"

    def test_contains_piper(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PIPER_MODEL_DIR", None)
            result = get_default_model_dir()
            assert "piper" in result.lower()


class TestListModels:
    def test_list_all(self, capsys):
        list_models()
        captured = capsys.readouterr()
        assert "tsukuyomi" in captured.err
        assert "css10" in captured.err

    def test_list_japanese(self, capsys):
        list_models("ja")
        captured = capsys.readouterr()
        assert "tsukuyomi" in captured.err
        assert "Japanese" in captured.err

    def test_list_unknown_language(self, capsys):
        list_models("xx")
        captured = capsys.readouterr()
        assert "No voice models found" in captured.err


class TestResolveModelPath:
    def test_direct_file_path(self, tmp_path):
        model_file = tmp_path / "model.onnx"
        model_file.touch()
        assert resolve_model_path(str(model_file)) == str(model_file)

    def test_nonexistent_path_not_alias(self):
        assert resolve_model_path("/nonexistent/model.onnx") is None

    def test_resolve_alias_with_downloaded_model(self, tmp_path):
        # Create a fake downloaded model
        onnx_file = tmp_path / "tsukuyomi-chan-6lang-fp16.onnx"
        onnx_file.touch()

        result = resolve_model_path("tsukuyomi", str(tmp_path))
        assert result is not None
        assert result == str(onnx_file)

    def test_resolve_alias_without_download(self, tmp_path):
        # No model file exists
        result = resolve_model_path("tsukuyomi", str(tmp_path))
        assert result is None
