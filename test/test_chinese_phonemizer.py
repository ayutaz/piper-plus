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

    def test_tone_sandhi_t3_t3(self):
        """T3+T3 should become T2+T3 (third tone sandhi): 你好."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_train.phonemize.token_mapper import register

        phonemes, prosody = phonemize_chinese_with_prosody("你好")
        # 你 is tone3, 好 is tone3 → sandhi: 你 becomes tone2
        tone2_char = register("tone2")
        tone3_char = register("tone3")
        # Find all tone markers in the phoneme sequence
        tones_found = [p for p in phonemes if p in (tone2_char, tone3_char)]
        # First Chinese syllable should have tone2 (sandhi), second tone3
        assert len(tones_found) >= 2
        assert tones_found[0] == tone2_char, "First syllable should be tone2 after sandhi"
        assert tones_found[1] == tone3_char, "Second syllable should remain tone3"

    def test_uan_mapping_yuan(self):
        """üan final should map to yɛn IPA (not yan): 元 yuan."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_train.phonemize.token_mapper import register

        phonemes, _ = phonemize_chinese_with_prosody("元")
        yen_char = register("yɛn")
        assert yen_char in phonemes, (
            f"Expected yɛn (üan) in phonemes for 元, got: {phonemes}"
        )

    def test_digit_passthrough(self):
        """Digits should pass through as-is."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        phonemes, prosody = phonemize_chinese_with_prosody("有3个")
        assert len(phonemes) == len(prosody)
        # The digit '3' should appear in the phoneme output
        assert "3" in phonemes, f"Digit 3 should be in phonemes, got: {phonemes}"

    def test_digit_prosody(self):
        """Digits should have neutral prosody (a1=0, a2=0, a3=1)."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        phonemes, prosody = phonemize_chinese_with_prosody("有3个")
        # Find the index of the digit '3'
        digit_idx = phonemes.index("3")
        p = prosody[digit_idx]
        assert p is not None
        assert p.a1 == 0
        assert p.a2 == 0
        assert p.a3 == 1
