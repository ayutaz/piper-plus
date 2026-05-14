"""Network resilience tests for piper.download.

Covers error paths that the existing test_cli_models.py suite does not exercise:
    - urlopen timeout
    - HTTP 500 / 404 responses
    - Partial download (Content-Length mismatch surfaces as wrong-size on disk)
    - Disk-full simulation (os.write / file.write raising OSError)

All network I/O is mocked. No real HuggingFace requests are issued.
Style follows test_cli_models.py: classes, tempfile.TemporaryDirectory, and
``with patch("piper.download.urlopen", ...)`` to intercept the urllib call site.
"""

import io
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest


# Add the parent directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.download import (  # noqa: E402
    ensure_voice_exists,
    get_voices,
)


def _make_voice_info(size_bytes: int = 5, md5_digest: str = "") -> dict:
    """Build a piper-plus voice entry pointing at a single fake .onnx file."""
    return {
        "key": "test-voice",
        "source": "piper-plus",
        "repo": "ayousanz/test-repo",
        "files": {
            "model.onnx": {"size_bytes": size_bytes, "md5_digest": md5_digest},
        },
    }


class _FakeResponse(io.BytesIO):
    """Minimal urlopen-like response usable as a context manager."""

    def __init__(self, payload: bytes):
        super().__init__(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class TestDownloadTimeout:
    """urlopen() raising a socket/URLError surfaces to the caller."""

    def test_socket_timeout_propagates(self):
        voice_info = _make_voice_info()
        voices = {"test-voice": voice_info}

        # socket.timeout was unified with TimeoutError in Python 3.10; older
        # Python versions and some urllib code paths may surface either type.
        # We raise socket.timeout from the patch to match real urlopen behavior
        # (urllib lets socket.timeout propagate without wrapping it in URLError),
        # and accept both types on the assertion side for cross-version safety.
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "piper.download.urlopen",
                side_effect=TimeoutError("connection timed out"),
            ):
                with pytest.raises((socket.timeout, TimeoutError)):
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)

    def test_urlerror_propagates(self):
        """urllib.error.URLError (e.g. DNS / network unreachable) propagates."""
        voice_info = _make_voice_info()
        voices = {"test-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "piper.download.urlopen",
                side_effect=URLError("Temporary failure in name resolution"),
            ):
                with pytest.raises(URLError):
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)


class TestDownloadHTTPErrors:
    """HTTP 5xx / 4xx responses raised by urlopen must surface as HTTPError."""

    def test_http_500_raises(self):
        voice_info = _make_voice_info()
        voices = {"test-voice": voice_info}

        http_500 = HTTPError(
            url="https://huggingface.co/ayousanz/test-repo/resolve/main/model.onnx",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("piper.download.urlopen", side_effect=http_500):
                with pytest.raises(HTTPError) as exc_info:
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)
                assert exc_info.value.code == 500

    def test_http_404_raises(self):
        voice_info = _make_voice_info()
        voices = {"test-voice": voice_info}

        http_404 = HTTPError(
            url="https://huggingface.co/ayousanz/test-repo/resolve/main/model.onnx",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("piper.download.urlopen", side_effect=http_404):
                with pytest.raises(HTTPError) as exc_info:
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)
                assert exc_info.value.code == 404


class TestPartialDownload:
    """Content-Length mismatch: write fewer bytes than expected_size.

    download.py uses shutil.copyfileobj(response, file) without verifying the
    written byte count, so a truncated response writes a smaller file on disk.
    A subsequent ensure_voice_exists call must detect the size mismatch and
    plan a re-download.
    """

    def test_truncated_payload_detected_on_recheck(self):
        # voice expects 1024 bytes; server returns 10 bytes.
        voice_info = _make_voice_info(size_bytes=1024)
        voices = {"test-voice": voice_info}
        truncated = b"x" * 10

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch(
                "piper.download.urlopen",
                return_value=_FakeResponse(truncated),
            ):
                ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)

            downloaded = tmp_path / "model.onnx"
            assert downloaded.exists()
            assert downloaded.stat().st_size == 10  # truncated, not 1024

            # Second call should observe wrong size and try to re-download.
            recheck_mock = MagicMock(side_effect=URLError("simulated re-download"))
            with patch("piper.download.urlopen", recheck_mock):
                with pytest.raises(URLError):
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)
            assert recheck_mock.called, "wrong-size file should trigger re-download"


class TestDiskFull:
    """Simulate disk-full during the write loop.

    shutil.copyfileobj calls file.write() in a loop; raising OSError(ENOSPC) on
    write must propagate out of ensure_voice_exists rather than silently
    leaving a partial file undetected.
    """

    def test_oserror_on_write_propagates(self, monkeypatch):
        import errno

        voice_info = _make_voice_info(size_bytes=1024)
        voices = {"test-voice": voice_info}

        payload = b"y" * 1024

        # Monkey-patch the built-in open used in download.py so the resulting
        # file object raises OSError(ENOSPC) on write. We only intercept the
        # download target path; other opens (e.g. voices.json) fall through.
        real_open = open
        target_filename = "model.onnx"

        class _DiskFullFile:
            def __init__(self):
                self.closed = False

            def write(self, _data):
                raise OSError(errno.ENOSPC, "No space left on device")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.closed = True
                return False

            def close(self):
                self.closed = True

        def fake_open(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, Path)) and Path(file).name == target_filename:
                return _DiskFullFile()
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "piper.download.urlopen",
                return_value=_FakeResponse(payload),
            ):
                with pytest.raises(OSError) as exc_info:
                    ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)
                assert exc_info.value.errno == errno.ENOSPC


class TestGetVoicesNetworkFailure:
    """get_voices(update_voices=True) must surface network errors from urlopen."""

    def test_update_voices_propagates_urlerror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "piper.download.urlopen",
                side_effect=URLError("network down"),
            ):
                with pytest.raises(URLError):
                    get_voices(tmpdir, update_voices=True)

    def test_no_update_does_not_call_network(self):
        """get_voices without update_voices must not touch the network."""
        with tempfile.TemporaryDirectory() as tmpdir:
            url_mock = MagicMock(
                side_effect=AssertionError("urlopen should not be called"),
            )
            with patch("piper.download.urlopen", url_mock):
                voices = get_voices(tmpdir, update_voices=False)
            assert "ja_JP-tsukuyomi-chan-medium" in voices
            assert not url_mock.called


class TestRedownloadOnSizeMismatch:
    """Existing wrong-size file must trigger one re-download attempt."""

    def test_wrong_size_triggers_redownload(self):
        voice_info = _make_voice_info(size_bytes=1024)
        voices = {"test-voice": voice_info}

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Pre-existing file with wrong size on disk.
            (tmp_path / "model.onnx").write_bytes(b"short")

            url_mock = MagicMock(return_value=_FakeResponse(b"y" * 1024))
            with patch("piper.download.urlopen", url_mock):
                ensure_voice_exists("test-voice", [tmpdir], tmpdir, voices)

            # Exactly one urlopen call for the missing/wrong file.
            assert url_mock.call_count == 1
            assert (tmp_path / "model.onnx").stat().st_size == 1024
