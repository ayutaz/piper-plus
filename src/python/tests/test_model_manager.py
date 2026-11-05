"""Tests for piper_train.model_manager."""

import os
from unittest.mock import MagicMock, patch

import pytest

from piper_train.model_manager import (
    download_model,
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
        with patch.dict(os.environ, {"PIPER_PLUS_MODEL_DIR": "/custom/path"}):
            assert get_default_model_dir() == "/custom/path"

    def test_contains_piper(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PIPER_PLUS_MODEL_DIR", None)
            result = get_default_model_dir()
            assert "piper-plus" in result.lower()


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


class TestDownloadModel:
    def test_unknown_model_returns_false(self, capsys):
        assert download_model("nonexistent-model-xyz") is False
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_skips_existing_file_with_matching_size(self, tmp_path, capsys):
        voice = find_voice("tsukuyomi")
        assert voice is not None

        # Create files with matching sizes (sparse files to avoid ~39MB allocation)
        for filename, file_info in voice["files"].items():
            f = tmp_path / filename
            f.touch()
            os.truncate(f, file_info["size_bytes"])

        mock_dl = MagicMock()
        with patch.dict(
            "sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_dl)}
        ):
            result = download_model("tsukuyomi", str(tmp_path))

        assert result is True
        mock_dl.assert_not_called()
        captured = capsys.readouterr()
        assert "already exists" in captured.err

    def test_downloads_missing_files(self, tmp_path, capsys):
        mock_dl = MagicMock()
        mock_hf = MagicMock(hf_hub_download=mock_dl)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            result = download_model("tsukuyomi", str(tmp_path))

        assert result is True
        voice = find_voice("tsukuyomi")
        assert mock_dl.call_count == len(voice["files"])
        for call_args in mock_dl.call_args_list:
            assert call_args.kwargs["repo_id"] == voice["repo_id"]
            assert call_args.kwargs["local_dir"] == str(tmp_path)

    def test_downloads_file_with_wrong_size(self, tmp_path):
        voice = find_voice("tsukuyomi")
        # Create files with wrong sizes
        for filename in voice["files"]:
            (tmp_path / filename).write_bytes(b"\x00" * 100)

        mock_dl = MagicMock()
        mock_hf = MagicMock(hf_hub_download=mock_dl)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            result = download_model("tsukuyomi", str(tmp_path))

        assert result is True
        assert mock_dl.call_count == len(voice["files"])

    def test_returns_false_on_download_error(self, tmp_path, capsys):
        mock_dl = MagicMock(side_effect=Exception("network error"))
        mock_hf = MagicMock(hf_hub_download=mock_dl)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            result = download_model("tsukuyomi", str(tmp_path))

        assert result is False
        captured = capsys.readouterr()
        assert "Failed" in captured.err

    def test_uses_default_model_dir_when_none(self, tmp_path):
        mock_dl = MagicMock()
        mock_hf = MagicMock(hf_hub_download=mock_dl)
        default_model_dir = str(tmp_path)

        with (
            patch.dict("sys.modules", {"huggingface_hub": mock_hf}),
            patch(
                "piper_train.model_manager.get_default_model_dir",
                return_value=default_model_dir,
            ),
        ):
            download_model("tsukuyomi")

        for call_args in mock_dl.call_args_list:
            assert call_args.kwargs["local_dir"] == default_model_dir

    def test_creates_model_dir(self, tmp_path):
        target = tmp_path / "sub" / "dir"
        assert not target.exists()

        mock_dl = MagicMock()
        mock_hf = MagicMock(hf_hub_download=mock_dl)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            download_model("tsukuyomi", str(target))

        assert target.exists()


class TestModelNotice:
    """Usage notice for models with terms (docs/reference/model-resolution.md §9)."""

    @pytest.fixture(autouse=True)
    def _fresh_state(self, monkeypatch):
        import piper_train.model_manager as mm

        monkeypatch.setattr(mm, "_shown_model_notices", set())
        monkeypatch.delenv("PIPER_PLUS_DISABLE_MODEL_NOTICE", raising=False)

    def _canonical(self):
        import json
        from pathlib import Path

        vectors = (
            Path(__file__).resolve().parents[3]
            / "test"
            / "model_resolution_vectors.json"
        )
        data = json.loads(vectors.read_text(encoding="utf-8"))
        return data["voice_catalog"]["ja_JP-tsukuyomi-chan-medium"]

    def test_notice_matches_canonical(self):
        from piper_train.model_manager import get_model_notice

        assert get_model_notice("tsukuyomi") == self._canonical()["notice"]

    @pytest.mark.parametrize(
        "value",
        [
            "ja_JP-tsukuyomi-chan-medium",
            "tsukuyomi-chan",
            "ja-tsukuyomi",
            "ayousanz/piper-plus-tsukuyomi-chan",
            "/models/tsukuyomi-chan-6lang-fp16.onnx",
            r"C:\models\tsukuyomi.onnx",
        ],
    )
    def test_tsukuyomi_inputs(self, value):
        from piper_train.model_manager import get_model_notice

        assert get_model_notice(value) == self._canonical()["notice"]

    @pytest.mark.parametrize("value", ["css10", "/models/css10-ja-6lang-fp16.onnx", ""])
    def test_other_inputs(self, value):
        from piper_train.model_manager import get_model_notice

        assert get_model_notice(value) is None

    def test_download_prints_notice_once_to_stderr(self, tmp_path, capsys):
        mock_hf = MagicMock(hf_hub_download=MagicMock())
        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            download_model("tsukuyomi", str(tmp_path))
            download_model("tsukuyomi", str(tmp_path))
        captured = capsys.readouterr()
        first_line = self._canonical()["notice"][0]
        assert captured.out == ""
        assert captured.err.count(first_line) == 1

    def test_env_var_disables(self, tmp_path, capsys, monkeypatch):
        from piper_train.model_manager import print_model_notice

        monkeypatch.setenv("PIPER_PLUS_DISABLE_MODEL_NOTICE", " Yes ")
        assert print_model_notice("tsukuyomi") is False
        assert capsys.readouterr().err == ""
