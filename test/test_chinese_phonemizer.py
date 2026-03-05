"""Tests for Chinese (Mandarin) phonemizer."""

import pytest


class TestChinesePhonemizer:
    """Tests for Chinese Mandarin G2P using pypinyin."""

    @pytest.fixture(autouse=True)
    def skip_if_no_pypinyin(self):
        pytest.importorskip("pypinyin")

    def test_simple_word(self):
        from piper_train.phonemize.chinese import phonemize_chinese

        phonemes = phonemize_chinese("你好")
        assert len(phonemes) > 0

    def test_contains_tone_markers(self):
        from piper_train.phonemize.chinese import phonemize_chinese

        phonemes = phonemize_chinese("你好")
        # Should contain tone markers
        tone_markers = {"tone1", "tone2", "tone3", "tone4", "tone5"}
        from piper_train.phonemize.token_mapper import register

        tone_chars = {register(t) for t in tone_markers}
        assert any(p in tone_chars for p in phonemes), "No tone markers found"

    def test_prosody_alignment(self):
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        phonemes, prosody = phonemize_chinese_with_prosody("你好世界")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        phonemes = p.phonemize("你好")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_punctuation_passthrough(self):
        from piper_train.phonemize.chinese import phonemize_chinese

        phonemes = phonemize_chinese("你好！")
        assert len(phonemes) > 0

    def test_prosody_a1_is_tone(self):
        """a1 should contain tone number (1-5)."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        phonemes, prosody = phonemize_chinese_with_prosody("你好")
        # At least some prosody entries should have a1 in [1,5]
        tone_values = [p.a1 for p in prosody if p is not None and p.a1 > 0]
        assert len(tone_values) > 0
        for t in tone_values:
            assert 1 <= t <= 5
