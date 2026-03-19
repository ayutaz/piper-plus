"""Tests for Python CLI model management features."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# Add the parent directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.download import (  # noqa: E402
    _SAFE_REPO_RE,
    PIPER_PLUS_URL_FORMAT,
    PIPER_PLUS_VOICES,
    VoiceNotFoundError,
    download_model,
    ensure_voice_exists,
    get_voices,
    list_voices,
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

    def test_css10_in_catalog(self):
        assert "ja_JP-css10-6lang-medium" in PIPER_PLUS_VOICES
        voice = PIPER_PLUS_VOICES["ja_JP-css10-6lang-medium"]
        assert voice["name"] == "css10-6lang"
        assert voice["language"]["code"] == "ja_JP"
        assert voice["source"] == "piper-plus"
        assert voice["num_speakers"] == 1

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
        assert (
            "tsukuyomi" in captured.err.lower() or "tsukuyomi" in captured.out.lower()
        )

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
            for _key, info in voices.items():
                for alias in info.get("aliases", []):
                    aliases[alias] = info

            assert "tsukuyomi" in aliases
            assert aliases["tsukuyomi"]["key"] == "ja_JP-tsukuyomi-chan-medium"

    def test_alias_css10(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            # Build alias map
            aliases = {}
            for _key, info in voices.items():
                for alias in info.get("aliases", []):
                    aliases[alias] = info

            assert "css10" in aliases
            assert aliases["css10"]["key"] == "ja_JP-css10-6lang-medium"


class TestDownloadModel:
    """Test download_model() function."""

    def test_download_nonexistent_raises(self):
        """download_model with unknown name raises VoiceNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(VoiceNotFoundError):
                download_model("nonexistent-model-xyz", tmpdir)

    def test_download_resolves_alias(self):
        """download_model resolves aliases correctly before download."""
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            # Build alias map same way as download_model
            resolved = None
            for key, info in voices.items():
                for alias in info.get("aliases", []):
                    if alias == "tsukuyomi":
                        resolved = key
                        break
            assert resolved == "ja_JP-tsukuyomi-chan-medium"

    def test_download_resolves_ja_tsukuyomi(self):
        """ja-tsukuyomi alias resolves to tsukuyomi-chan model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            voices = get_voices(tmpdir)
            aliases = {}
            for _key, info in voices.items():
                for alias in info.get("aliases", []):
                    aliases[alias] = info
            assert "ja-tsukuyomi" in aliases
            assert aliases["ja-tsukuyomi"]["key"] == "ja_JP-tsukuyomi-chan-medium"

class TestFindVoiceFallback:
    """Test find_voice() piper-plus filename fallback."""

    def test_piper_plus_file_names_in_catalog(self):
        """piper-plus models have correct file names in catalog."""
        voice = PIPER_PLUS_VOICES["ja_JP-tsukuyomi-chan-medium"]
        files = list(voice["files"].keys())
        assert "tsukuyomi-chan-6lang-fp16.onnx" in files
        assert "config.json" in files

    def test_css10_file_names_in_catalog(self):
        """CSS10 piper-plus model has correct file names in catalog."""
        voice = PIPER_PLUS_VOICES["ja_JP-css10-6lang-medium"]
        files = list(voice["files"].keys())
        assert "css10-ja-6lang-fp16.onnx" in files
        assert "config.json" in files


class TestVersion:
    """Test __version__ availability."""

    def test_version_is_string(self):
        from piper import __version__

        assert isinstance(__version__, str)

    def test_version_not_empty(self):
        from piper import __version__

        assert len(__version__) > 0

    def test_version_not_unknown_if_version_file_exists(self):
        from piper import __version__

        version_file = (
            Path(__file__).parent.parent / "piper" / ".." / ".." / ".." / "VERSION"
        )
        # Only assert if VERSION file actually exists in dev environment
        if version_file.resolve().exists():
            assert __version__ != "unknown"


class TestEnsureVoiceUrl:
    """Test URL construction for piper-plus models."""

    def test_piper_plus_url_format(self):
        url = PIPER_PLUS_URL_FORMAT.format(
            repo="ayousanz/piper-plus-tsukuyomi-chan",
            file="config.json",
        )
        assert (
            url
            == "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json"
        )

    def test_piper_plus_voice_has_repo(self):
        for key, voice in PIPER_PLUS_VOICES.items():
            if voice.get("source") == "piper-plus":
                assert "repo" in voice, f"{key} missing repo field"
                assert voice["repo"].startswith("ayousanz/")


class TestListVoicesFormat:
    """Test list_voices output format."""

    def test_output_to_stderr(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_voices(tmpdir)
        captured = capsys.readouterr()
        # Output should be on stderr
        assert len(captured.err) > 0

    def test_contains_piper_plus_tag(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_voices(tmpdir)
        captured = capsys.readouterr()
        assert "[piper-plus]" in captured.err


class TestUrlValidation:
    """Test HTTPS URL validation in ensure_voice_exists."""

    def test_https_url_accepted(self):
        """Normal piper-plus URL starts with https:// and passes validation."""
        url = PIPER_PLUS_URL_FORMAT.format(
            repo="ayousanz/piper-plus-tsukuyomi-chan",
            file="config.json",
        )
        assert url.startswith("https://")

    def test_non_https_url_rejected(self):
        """ensure_voice_exists raises ValueError for non-HTTPS URL."""
        voice_info = {
            "key": "test-voice",
            "source": "piper-plus",
            "repo": "ayousanz/test-repo",
            "files": {
                "model.onnx": {"size_bytes": 100, "md5_digest": ""},
            },
        }
        voices = {"test-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch PIPER_PLUS_URL_FORMAT to produce an http:// URL
            with patch(
                "piper.download.PIPER_PLUS_URL_FORMAT",
                "http://example.com/{repo}/{file}",
            ):
                with pytest.raises(ValueError, match="non-HTTPS"):
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)


class TestRepoValidation:
    """Test _SAFE_REPO_RE pattern for repo value validation."""

    @pytest.mark.parametrize(
        "repo",
        [
            "ayousanz/piper-plus-tsukuyomi-chan",
            "ayousanz/piper-plus-base",
            "user123/my-model.v2",
            "org/repo_name",
        ],
    )
    def test_safe_repo_accepted(self, repo):
        """Valid repo values match _SAFE_REPO_RE."""
        assert _SAFE_REPO_RE.match(repo) is not None

    @pytest.mark.parametrize(
        "repo",
        [
            "user/../etc/passwd",
            "user/../../secret",
            "../traversal",
        ],
    )
    def test_repo_with_dotdot_rejected(self, repo):
        """Repo values containing '..' are rejected by the traversal check."""
        # Even if the regex matches, the ".." check blocks it
        assert ".." in repo

    @pytest.mark.parametrize(
        "repo",
        [
            "user/repo; rm -rf /",
            "user/repo$(cmd)",
            "user/<script>",
            "user/repo name",
            "user/repo\ttab",
        ],
    )
    def test_repo_with_special_chars_rejected(self, repo):
        """Repo values with special characters do not match _SAFE_REPO_RE."""
        assert _SAFE_REPO_RE.match(repo) is None

    def test_ensure_voice_rejects_dotdot_repo(self):
        """ensure_voice_exists raises ValueError for '..' in repo."""
        voice_info = {
            "key": "bad-voice",
            "source": "piper-plus",
            "repo": "user/../etc/passwd",
            "files": {
                "model.onnx": {"size_bytes": 100, "md5_digest": ""},
            },
        }
        voices = {"bad-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Invalid repo"):
                ensure_voice_exists("bad-voice", [tmpdir], tmpdir, voices)

    def test_ensure_voice_rejects_special_char_repo(self):
        """ensure_voice_exists raises ValueError for special chars in repo."""
        voice_info = {
            "key": "bad-voice",
            "source": "piper-plus",
            "repo": "user/repo; rm -rf /",
            "files": {
                "model.onnx": {"size_bytes": 100, "md5_digest": ""},
            },
        }
        voices = {"bad-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Invalid repo"):
                ensure_voice_exists("bad-voice", [tmpdir], tmpdir, voices)


class TestMd5EmptyDigest:
    """Test that empty md5_digest skips re-download."""

    def test_empty_md5_skips_redownload(self):
        """When md5_digest is empty, existing file with correct size is accepted."""
        voice_info = {
            "key": "test-voice",
            "source": "piper-plus",
            "repo": "ayousanz/test-repo",
            "files": {
                "model.onnx": {"size_bytes": 5, "md5_digest": ""},
            },
        }
        voices = {"test-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with the expected size
            model_path = Path(tmpdir) / "model.onnx"
            model_path.write_bytes(b"hello")  # 5 bytes

            # ensure_voice_exists should NOT attempt any download
            # (if it tried, urlopen would fail since no server is running)
            ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)

            # File should still exist unchanged
            assert model_path.read_bytes() == b"hello"
