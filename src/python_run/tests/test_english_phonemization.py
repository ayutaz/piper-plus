#!/usr/bin/env python3
"""Test English phonemization functionality"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.config import PhonemeType, PiperConfig
from piper.espeak_phonemizer import phonemize_espeak_ng, phonemize_espeak_phonemes


# Import PiperVoice separately to avoid import issues during testing
try:
    from piper.voice import PiperVoice
except ImportError:
    PiperVoice = None


class TestEspeakPhonemizerFallback:
    """Test espeak-ng phonemizer fallback implementation"""

    def test_phonemize_espeak_ng_basic(self):
        """Test basic IPA phonemization"""
        # Test with simple text
        result = phonemize_espeak_ng("Hello world", "en-us")

        # Should return a list of lists
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], list)

        # Check that we get IPA symbols (not just characters)
        phonemes = result[0]
        phoneme_str = "".join(phonemes)

        # Should contain IPA symbols like ə, ˈ, ʊ, ɜ, etc.
        assert any(
            char in phoneme_str for char in ["ə", "ˈ", "ʊ", "ɜ", "ː", "ɹ", "ɔ", "æ"]
        )

        # Should NOT be just the original text split into characters
        assert phonemes != list("Hello world")

    def test_phonemize_espeak_ng_fallback(self):
        """Test fallback when espeak-ng is not available"""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = phonemize_espeak_ng("Hello", "en-us")

            # Should fall back to character list
            assert result == [list("Hello")]

    def test_phonemize_espeak_ng_error_handling(self):
        """Test error handling when espeak-ng fails"""
        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["espeak-ng"]),
        ):
            result = phonemize_espeak_ng("Test", "en-us")

            # Should fall back to character list
            assert result == [list("Test")]

    def test_phonemize_espeak_phonemes(self):
        """Test phoneme-based (non-IPA) output"""
        result = phonemize_espeak_phonemes("Hello", "en-us")

        # Should return a list of lists
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], list)

        # Check that we get phonemes
        phonemes = result[0]
        assert len(phonemes) > 0


class TestVoicePhonemizerIntegration:
    """Test voice.py phonemizer integration"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock PiperConfig for testing"""
        config = MagicMock(spec=PiperConfig)
        config.phoneme_type = PhonemeType.ESPEAK
        config.espeak_voice = "en-us"
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

    def test_voice_phonemize_with_espeak_fallback(self, mock_config):
        """Test that voice.py correctly uses espeak fallback"""
        if PiperVoice is None:
            pytest.skip("PiperVoice not available")

        # Patch the import to simulate piper_phonemize not available
        with patch.dict(sys.modules, {"piper_phonemize": None}):
            # Need to reload voice module to pick up the import change
            import importlib

            import piper.voice

            importlib.reload(piper.voice)

            # Create a mock voice
            voice = MagicMock()
            voice.config = mock_config

            # Manually call phonemize method
            phonemes = piper.voice.PiperVoice.phonemize(voice, "Hello")

            # Should get phonemes, not just characters
            assert isinstance(phonemes, list)
            assert len(phonemes) > 0

            # If espeak-ng is available, should get IPA phonemes
            if (
                subprocess.run(
                    ["which", "espeak-ng"], check=False, capture_output=True
                ).returncode
                == 0
            ):
                phoneme_str = "".join(phonemes[0])
                assert any(char in phoneme_str for char in ["ə", "ˈ", "ʊ", "ɜ"])

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
            / "test_voice.onnx"
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
            / "test_voice.onnx"
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
