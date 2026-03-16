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

    def test_er_final_uses_schwa(self):
        """er final should produce ɚ (rhotacized schwa), not ɑɻ."""
        from piper_train.phonemize.chinese import phonemize_chinese
        from piper_train.phonemize.token_mapper import register

        # 二 (èr) uses pinyin "er"
        phonemes = phonemize_chinese("二")
        schwa_char = register("ɚ")
        assert schwa_char in phonemes, (
            f"Expected ɚ (rhotacized schwa) in phonemes for 二, got: {phonemes}"
        )

    def test_er_final_not_old_aer(self):
        """er final should NOT produce ɑɻ (old incorrect mapping)."""
        from piper_train.phonemize.chinese import phonemize_chinese
        from piper_train.phonemize.token_mapper import register

        phonemes = phonemize_chinese("二")
        old_char = register("ɑɻ")
        assert old_char not in phonemes, (
            f"ɑɻ should no longer appear for 二; phonemes: {phonemes}"
        )

    def test_u_umlaut_uses_y_vowel(self):
        """Pinyin ü should use y_vowel token, not bare y."""
        from piper_train.phonemize.chinese import phonemize_chinese
        from piper_train.phonemize.token_mapper import TOKEN2CHAR

        # 女 (nǚ) uses ü vowel
        phonemes = phonemize_chinese("女")
        y_vowel_char = TOKEN2CHAR.get("y_vowel")
        assert y_vowel_char is not None, "y_vowel should be registered in TOKEN2CHAR"
        assert y_vowel_char in phonemes, (
            f"Expected y_vowel token in phonemes for 女, got: {phonemes}"
        )
        # bare "y" should not appear as a standalone phoneme
        assert "y" not in phonemes, (
            f"Bare 'y' should not appear; phonemes: {phonemes}"
        )

    def test_yi_tone_sandhi_before_tone4(self):
        """一 (yi T1) before T4 should become T2: 一定 yī dìng → yí dìng."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_train.phonemize.token_mapper import register

        phonemes, _ = phonemize_chinese_with_prosody("一定")
        tone2_char = register("tone2")
        tone4_char = register("tone4")
        tones = [p for p in phonemes if p in (tone2_char, tone4_char)]
        assert len(tones) >= 2, f"Expected at least 2 tone markers, got: {tones}"
        assert tones[0] == tone2_char, (
            "一 before T4 should become T2 (sandhi)"
        )
        assert tones[1] == tone4_char, "定 should remain T4"

    def test_yi_tone_sandhi_before_tone1(self):
        """一 (yi T1) before T1 should become T4: 一般 yī bān → yì bān."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_train.phonemize.token_mapper import register

        phonemes, _ = phonemize_chinese_with_prosody("一般")
        tone1_char = register("tone1")
        tone4_char = register("tone4")
        tones = [p for p in phonemes if p in (tone1_char, tone4_char)]
        assert len(tones) >= 2, f"Expected at least 2 tone markers, got: {tones}"
        assert tones[0] == tone4_char, (
            "一 before T1 should become T4 (sandhi)"
        )

    def test_bu_tone_sandhi_before_tone4(self):
        """不 (bu T4) before T4 should become T2: 不对 bù duì → bú duì."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_train.phonemize.token_mapper import register

        phonemes, _ = phonemize_chinese_with_prosody("不对")
        tone2_char = register("tone2")
        tone4_char = register("tone4")
        tones = [p for p in phonemes if p in (tone2_char, tone4_char)]
        assert len(tones) >= 2, f"Expected at least 2 tone markers, got: {tones}"
        assert tones[0] == tone2_char, (
            "不 before T4 should become T2 (sandhi)"
        )
        assert tones[1] == tone4_char, "对 should remain T4"

    def test_erhua_basic(self):
        """Erhua r-coloring should produce ɚ appended to base syllable."""
        from piper_train.phonemize.chinese import phonemize_chinese
        from piper_train.phonemize.token_mapper import register

        # 哪儿 (nǎr) — pypinyin may output "nar3" indicating erhua
        # We test with 儿 standalone which pypinyin outputs as "er5"
        # For erhua test use a word known to produce r-suffixed pinyin
        # 这儿 (zhèr): pypinyin often gives "zher4" for erhua
        phonemes = phonemize_chinese("这儿")
        schwa_char = register("ɚ")
        # Either the ɚ appears from erhua processing or from standalone 儿
        assert schwa_char in phonemes, (
            f"Expected ɚ token for erhua in 这儿, got: {phonemes}"
        )

    def test_mixed_chinese_latin_alignment(self):
        """Mixed Chinese+Latin text should not cause index misalignment.

        pypinyin groups consecutive non-Chinese chars into single entries,
        so len(py_result) can be less than len(text). The phonemizer must
        iterate by text character index, not pypinyin result index.
        """
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        # "你好ABC世界" — ABC is non-Chinese, pypinyin merges it into 1 entry
        phonemes, prosody = phonemize_chinese_with_prosody("你好ABC世界")
        assert len(phonemes) == len(prosody)
        assert len(phonemes) > 0
        # Latin chars A, B, C should pass through
        assert "A" in phonemes
        assert "B" in phonemes
        assert "C" in phonemes

    def test_mixed_chinese_digits_alignment(self):
        """Mixed Chinese+digits should not cause index misalignment."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        # "第123章" — digits 1,2,3 are non-Chinese
        phonemes, prosody = phonemize_chinese_with_prosody("第123章")
        assert len(phonemes) == len(prosody)
        assert "1" in phonemes
        assert "2" in phonemes
        assert "3" in phonemes

    def test_mixed_chinese_punctuation_alignment(self):
        """Mixed Chinese+punctuation should maintain prosody alignment."""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody

        phonemes, prosody = phonemize_chinese_with_prosody("你好，世界！")
        assert len(phonemes) == len(prosody)
        assert len(phonemes) > 0
