"""Tests for Python CLI model management features."""

import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the parent directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.download import (
    PIPER_PLUS_VOICES,
    get_voices,
    list_voices,
    VoiceNotFoundError,
)


class TestPiperPlusVoiceCatalog:
    """Test piper-plus voice catalog integration."""

    def test_piper_plus_voices_not_empty(self):
        assert len(PIPER_PLUS_VOICES) > 0

    def test_tsukuyomi_in_catalog(self):
        assert "ja_JP-tsukuyomi-chan-medium" in PIPER_PLUS_VOICES
        voice = PIPER_PLUS_VOICES["ja_JP-tsukuyomi-chan-medium"]
        assert voice["name"] == "tsukuyomi-chan"
        assert voice["language"]["code"] == "ja_JP"
        assert voice["source"] == "piper-plus"
        assert voice["num_speakers"] == 1

    def test_moe_speech_in_catalog(self):
        assert "ja_JP-moe-speech-20speakers-medium" in PIPER_PLUS_VOICES
        voice = PIPER_PLUS_VOICES["ja_JP-moe-speech-20speakers-medium"]
        assert voice["num_speakers"] == 20
        assert voice["source"] == "piper-plus"

    def test_piper_plus_voices_have_files(self):
        for key, voice in PIPER_PLUS_VOICES.items():
            assert "files" in voice, f"{key} missing files"
            has_onnx = any(f.endswith(".onnx") for f in voice["files"])
            assert has_onnx, f"{key} missing ONNX file"

    def test_piper_plus_voices_have_aliases(self):
        voice = PIPER_PLUS_VOICES["ja_JP-tsukuyomi-chan-medium"]
        assert "tsukuyomi" in voice["aliases"]
        assert "tsukuyomi-chan" in voice["aliases"]

    def test_piper_plus_voices_have_repo(self):
        for key, voice in PIPER_PLUS_VOICES.items():
            assert "repo" in voice, f"{key} missing repo"
            assert voice["repo"].startswith("ayousanz/"), f"{key} unexpected repo"


class TestGetVoices:
    """Test get_voices() includes piper-plus models."""

    def test_includes_piper_plus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            assert "ja_JP-tsukuyomi-chan-medium" in voices
            assert "ja_JP-moe-speech-20speakers-medium" in voices

    def test_includes_upstream(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            # Should include at least some upstream voices
            assert len(voices) > 2  # More than just piper-plus


class TestListVoices:
    """Test list_voices() output."""

    def test_list_all(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_voices(tmpdir)
        captured = capsys.readouterr()
        assert "tsukuyomi" in captured.err.lower() or "tsukuyomi" in captured.out.lower()

    def test_list_japanese(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_voices(tmpdir, language_filter="ja")
        captured = capsys.readouterr()
        output = captured.err + captured.out
        assert "Japanese" in output or "日本語" in output

    def test_list_nonexistent_language(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_voices(tmpdir, language_filter="zz")
        captured = capsys.readouterr()
        output = captured.err + captured.out
        assert "No voice" in output or "not found" in output.lower()


class TestAliasResolution:
    """Test alias resolution in get_voices."""

    def test_alias_tsukuyomi(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            # Build alias map
            aliases = {}
            for key, info in voices.items():
                for alias in info.get("aliases", []):
                    aliases[alias] = info

            assert "tsukuyomi" in aliases
            assert aliases["tsukuyomi"]["key"] == "ja_JP-tsukuyomi-chan-medium"

    def test_alias_moe_speech(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            aliases = {}
            for key, info in voices.items():
                for alias in info.get("aliases", []):
                    aliases[alias] = info

            assert "moe-speech" in aliases
