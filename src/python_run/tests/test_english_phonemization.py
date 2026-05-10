#!/usr/bin/env python3
"""Test English phonemization functionality.

Note: piper-plus does NOT depend on espeak-ng at runtime.  English G2P uses
``g2p-en`` (Apache-2.0); see ``piper/phonemize/english.py``.  The legacy
``espeak_phonemizer.py`` module was removed as dead code.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.config import PhonemeType, PiperConfig


# Import PiperVoice separately to avoid import issues during testing
try:
    from piper.voice import PiperVoice
except ImportError:
    PiperVoice = None


class TestVoicePhonemizerIntegration:
    """Test voice.py phonemizer integration"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock PiperConfig for testing"""
        config = MagicMock(spec=PiperConfig)
        config.phoneme_type = PhonemeType.MULTILINGUAL
        config.sample_rate = 16000
        config.phoneme_id_map = {
            "^": [1],
            "$": [2],
            "_": [0],
            " ": [3],
            "h": [20],
            "ə": [59],
            "l": [24],
            "ˈ": [120],
            "o": [27],
            "ʊ": [100],
            "w": [35],
            "ɜ": [62],
            "ː": [122],
            "d": [17],
            "ɹ": [88],
        }
        return config

    def test_phonemes_to_ids_with_ipa(self, mock_config):
        """Test conversion of IPA phonemes to IDs"""
        if PiperVoice is None:
            pytest.skip("PiperVoice not available")

        voice = MagicMock()
        voice.config = mock_config

        # Test with IPA phonemes
        test_phonemes = ["h", "ə", "l", "ˈ", "o", "ʊ"]

        import piper.voice

        ids = piper.voice.PiperVoice.phonemes_to_ids(voice, test_phonemes)

        # Should start with BOS
        assert ids[0] == 1  # BOS = ^

        # Should contain mapped phoneme IDs
        assert 20 in ids  # h
        assert 59 in ids  # ə
        assert 24 in ids  # l
        assert 120 in ids  # ˈ

        # Should end with EOS
        assert ids[-1] == 2  # EOS = $


class TestCLIIntegration:
    """Test CLI integration with English models"""

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent.parent.parent
            / "test"
            / "models"
            / "multilingual-test-medium.onnx"
        ).exists(),
        reason="Test model not available",
    )
    def test_cli_english_synthesis(self, tmp_path):
        """Test English synthesis via CLI"""
        output_file = tmp_path / "test_output.wav"

        # Construct the model path dynamically
        model_path = (
            Path(__file__).parent.parent.parent.parent
            / "test"
            / "models"
            / "multilingual-test-medium.onnx"
        )

        # Run piper CLI
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper",
                "--model",
                str(model_path),
                "--output_file",
                str(output_file),
            ],
            check=False,
            input="Hello world",
            text=True,
            capture_output=True,
            cwd=Path(__file__).parent.parent,
        )

        # Should succeed
        assert result.returncode == 0, f"CLI failed with: {result.stderr}"

        # Should create output file
        assert output_file.exists()
        assert output_file.stat().st_size > 0

        # Verify it's a valid WAV file
        import wave

        with wave.open(str(output_file), "rb") as wav:
            assert wav.getnchannels() == 1  # Mono
            assert wav.getsampwidth() == 2  # 16-bit
            assert wav.getframerate() in [16000, 22050]  # Common TTS sample rates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
