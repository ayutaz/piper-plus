"""
Runtime tests for piper voice synthesis
Tests actual implementation without excessive mocking
"""

import numpy as np
import pytest

from piper.util import audio_float_to_int16


class TestAudioUtils:
    """Test audio utility functions"""

    @pytest.mark.unit
    def test_audio_float_to_int16_conversion(self):
        """Test float to int16 audio conversion"""
        # Test normal range
        float_audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        int16_audio = audio_float_to_int16(float_audio)

        assert int16_audio.dtype == np.int16
        assert int16_audio[0] == 0
        assert int16_audio[1] > 0  # 0.5 -> positive
        assert int16_audio[2] < 0  # -0.5 -> negative
        assert int16_audio[3] == 32767  # 1.0 -> max
        assert int16_audio[4] == -32767  # -1.0 -> min (normalized)

    @pytest.mark.unit
    def test_audio_clipping(self):
        """Test clipping of out-of-range values"""
        float_audio = np.array([2.0, -2.0], dtype=np.float32)
        int16_audio = audio_float_to_int16(float_audio)

        assert int16_audio[0] == 32767  # Clipped to max
        assert int16_audio[1] == -32767  # Clipped to min (normalized)


class TestPiperConfig:
    """Test PiperConfig.from_dict() actually parses production config shape."""

    @pytest.mark.unit
    def test_config_from_dict_canonical_shape(self):
        """from_dict() builds a PiperConfig with the expected attribute values.

        Pin the canonical config shape used by `PiperVoice.load()` so that a
        future refactor of `PiperConfig.from_dict()` cannot silently rename
        keys, drop fields, or change defaults without an explicit test
        update.  This replaces the previous tautology that only inspected
        the input dict without ever calling production code.
        """
        from piper.config import PhonemeType, PiperConfig

        config_dict = {
            "audio": {"sample_rate": 22050, "hop_size": 256},
            "num_symbols": 100,
            "num_speakers": 1,
            "phoneme_type": "multilingual",
            "phoneme_id_map": {"_": [0], "a": [10]},
            "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
        }
        cfg = PiperConfig.from_dict(config_dict)

        assert isinstance(cfg, PiperConfig)
        assert cfg.sample_rate == 22050
        assert cfg.num_symbols == 100
        assert cfg.num_speakers == 1
        assert cfg.hop_size == 256
        assert cfg.noise_scale == pytest.approx(0.667)
        assert cfg.length_scale == pytest.approx(1.0)
        assert cfg.noise_w == pytest.approx(0.8)
        assert cfg.phoneme_type is PhonemeType.MULTILINGUAL
        assert cfg.phoneme_id_map == {"_": [0], "a": [10]}
        assert cfg.num_languages == 1
        assert cfg.language_id_map is None

    @pytest.mark.unit
    def test_config_from_dict_inference_defaults(self):
        """When `inference` is missing, the documented defaults apply.

        Pinned defaults (PR #222 / DR-008 v2 canonical): noise_scale=0.4,
        length_scale=1.0, noise_w=0.5. These come from `from_dict()`
        directly \u2014 not the dict \u2014 so this test fails if anyone changes
        the defaults without bumping the doc.
        """
        from piper.config import PiperConfig

        cfg = PiperConfig.from_dict({
            "audio": {"sample_rate": 22050},
            "num_symbols": 50,
            "num_speakers": 1,
            "phoneme_id_map": {"_": [0]},
            # No "inference" key at all.
        })
        assert cfg.noise_scale == pytest.approx(0.4)
        assert cfg.length_scale == pytest.approx(1.0)
        assert cfg.noise_w == pytest.approx(0.5)
        # hop_size default
        assert cfg.hop_size == 256

    @pytest.mark.unit
    def test_config_from_dict_zero_noise_scale_preserved(self):
        """Regression: noise_scale=0.0 must NOT be overridden by the default.

        Pre-fix, an `inference.get("noise_scale", 0.667)` could swallow
        an explicit zero. Verify the explicit value reaches the config.
        """
        from piper.config import PiperConfig

        cfg = PiperConfig.from_dict({
            "audio": {"sample_rate": 22050},
            "num_symbols": 50,
            "num_speakers": 1,
            "phoneme_id_map": {"_": [0]},
            "inference": {"noise_scale": 0.0, "length_scale": 1.0, "noise_w": 0.0},
        })
        assert cfg.noise_scale == 0.0
        assert cfg.noise_w == 0.0

    @pytest.mark.unit
    def test_japanese_phoneme_id_map_with_pua(self):
        """Japanese OpenJTalk config: PUA-mapped multi-char phonemes survive parsing.

        The `\ue00e` \u2194 "ch" / `\ue00f` \u2194 "ts" mapping is the production
        contract enforced by token_mapper.FIXED_PUA_MAPPING.  Use the real
        `PiperConfig.from_dict()` path so a future regression in PUA-key
        preservation is caught.
        """
        from piper.config import PhonemeType, PiperConfig

        cfg = PiperConfig.from_dict({
            "audio": {"sample_rate": 22050},
            "num_symbols": 100,
            "num_speakers": 1,
            "phoneme_type": "openjtalk",
            "phoneme_id_map": {
                "_": [0],
                "\ue00e": [30],  # ch
                "\ue00f": [31],  # ts
            },
            "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
        })
        assert cfg.phoneme_type is PhonemeType.OPENJTALK
        assert "\ue00e" in cfg.phoneme_id_map
        assert "\ue00f" in cfg.phoneme_id_map
        # PUA codepoints are preserved as keys (not silently mangled).
        pua_keys = [k for k in cfg.phoneme_id_map if 0xE000 <= ord(k[0]) <= 0xF8FF]
        assert len(pua_keys) == 2
        assert cfg.phoneme_id_map["\ue00e"] == [30]
        assert cfg.phoneme_id_map["\ue00f"] == [31]

    @pytest.mark.unit
    def test_config_from_dict_with_language_id_map(self):
        """language_id_map round-trips through from_dict()."""
        from piper.config import PiperConfig

        cfg = PiperConfig.from_dict({
            "audio": {"sample_rate": 22050},
            "num_symbols": 50,
            "num_speakers": 1,
            "phoneme_id_map": {"_": [0]},
            "num_languages": 6,
            "language_id_map": {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5},
        })
        assert cfg.num_languages == 6
        assert cfg.language_id_map == {
            "ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5
        }


class TestFileHash:
    """Test file hashing utilities"""

    @pytest.mark.unit
    def test_file_hash_calculation(self, temp_dir):
        """Test file hash calculation"""
        try:
            from piper.file_hash import get_file_hash
        except ImportError:
            pytest.skip("File hash module not available")

        # Create test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello world")

        # Calculate hash
        hash1 = get_file_hash(str(test_file))
        assert isinstance(hash1, str)
        assert len(hash1) > 0

        # Same content should give same hash
        hash2 = get_file_hash(str(test_file))
        assert hash1 == hash2

        # Different content should give different hash
        test_file.write_text("Different content")
        hash3 = get_file_hash(str(test_file))
        assert hash3 != hash1
