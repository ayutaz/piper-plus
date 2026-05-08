"""Tests for piper_plus_g2p.chinese -- ChinesePhonemizer.

These tests pin the current ChinesePhonemizer behaviour as a regression
gate. Expected values reflect what pypinyin currently returns; they are
snapshots, not phonological ground truth.
"""

from tests.conftest import requires_zh


@requires_zh
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns tokens without BOS/EOS markers."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你好")
        assert len(tokens) > 0
        assert "^" not in tokens, "BOS should not be present"
        assert "$" not in tokens, "EOS should not be present"

    def test_no_pua_characters(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("今天天气很好")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_tone_markers(self):
        """phonemize() includes tone markers (tone1 through tone5)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("中国人民")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) > 0, f"Expected tone markers in {tokens}"
        valid_tones = {"tone1", "tone2", "tone3", "tone4", "tone5"}
        for t in tone_tokens:
            assert t in valid_tones, f"Invalid tone marker: {t}"

    def test_punctuation(self):
        """Chinese punctuation characters are processed."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你好！")
        assert "!" in tokens, f"Expected '!' (mapped from fullwidth) in {tokens}"

    def test_capital_city_beijing(self):
        """北京 -> p eɪ tone3 tɕ iŋ tone1."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("北京")
        assert tokens == ["p", "eɪ", "tone3", "tɕ", "iŋ", "tone1"], tokens

    def test_china(self):
        """中国 produces full IPA + tones."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("中国")
        assert tokens == ["tʂ", "uŋ", "tone1", "k", "uo", "tone2"], tokens


@requires_zh
class TestHeteronyms:
    """多音字 (characters with context-dependent readings)."""

    def test_xing_walk(self):
        """行李 -> 行 reads as xíng (xing) before 李."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("行李")
        assert tokens == ["ɕ", "iŋ", "tone2", "l", "i", "tone3"], tokens

    def test_hang_bank(self):
        """银行 -> 行 reads as háng (hang) after 银."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("银行")
        assert tokens == ["in", "tone2", "x", "aŋ", "tone2"], tokens

    def test_chang_grow(self):
        """长大 -> 长 reads as zhǎng (tʂ aŋ tone3)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("长大")
        assert tokens == ["tʂ", "aŋ", "tone3", "t", "a", "tone4"], tokens

    def test_chang_principal(self):
        """校长 -> 长 reads as zhǎng (principal)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("校长")
        assert tokens == ["ɕ", "iaʊ", "tone4", "tʂ", "aŋ", "tone3"], tokens

    def test_zhong_important(self):
        """重要 -> 重 reads as zhòng (tone4)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("重要")
        assert tokens == ["tʂ", "uŋ", "tone4", "iaʊ", "tone4"], tokens

    def test_chong_again(self):
        """重新 -> 重 reads as chóng (tʂʰ uŋ tone2)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("重新")
        assert tokens == ["tʂʰ", "uŋ", "tone2", "ɕ", "in", "tone1"], tokens


@requires_zh
class TestErhua:
    """儿化音 (rhotacization with -er suffix)."""

    def test_huar_flower(self):
        """花儿 emits ɚ token."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("花儿")
        assert "ɚ" in tokens, tokens
        assert tokens == ["x", "ua", "tone1", "ɚ", "tone2"], tokens

    def test_yihuir_a_while(self):
        """一会儿 -> i tone2 x ueɪ tone4 ɚ tone5."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("一会儿")
        assert tokens == ["i", "tone2", "x", "ueɪ", "tone4", "ɚ", "tone5"], tokens

    def test_nar_where(self):
        """哪儿 -> n a tone3 ɚ tone2."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("哪儿")
        assert tokens == ["n", "a", "tone3", "ɚ", "tone2"], tokens

    def test_wanr_play(self):
        """玩儿 -> uan tone2 ɚ tone2."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("玩儿")
        assert tokens == ["uan", "tone2", "ɚ", "tone2"], tokens

    def test_xiaohair_kid(self):
        """小孩儿 keeps three syllables + er."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("小孩儿")
        assert tokens == ["ɕ", "iaʊ", "tone3", "x", "aɪ", "tone2", "ɚ", "tone2"], tokens


@requires_zh
class TestNeutralTone:
    """中性声調 (neutral / weak tone, marked tone5)."""

    def test_mama(self):
        """妈妈 -> m a tone1 m a tone1 (no neutral on second 妈 in pypinyin)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("妈妈")
        assert tokens == ["m", "a", "tone1", "m", "a", "tone1"], tokens

    def test_baba(self):
        """爸爸 -> p a tone4 p a tone4."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("爸爸")
        assert tokens == ["p", "a", "tone4", "p", "a", "tone4"], tokens

    def test_women(self):
        """我们 -> 我 tone3 + 们 neutral (tone5)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("我们")
        assert "tone5" in tokens
        assert tokens == ["uo", "tone3", "m", "ən", "tone5"], tokens

    def test_zhuozi(self):
        """桌子 -> tʂ uo tone1 ts ɨ tone5."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("桌子")
        assert tokens == ["tʂ", "uo", "tone1", "ts", "ɨ", "tone5"], tokens

    def test_pengyou_friend(self):
        """朋友 -> 友 tone3 (pypinyin keeps full tone, not neutralised)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("朋友")
        assert tokens == ["pʰ", "əŋ", "tone2", "iou", "tone3"], tokens


@requires_zh
class TestSandhi:
    """yi/bu sandhi and third-tone sandhi (snapshot of pypinyin behaviour)."""

    def test_yi_ge(self):
        """一个 -> 一 reads as yí (tone2) before 个 (tone4)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("一个")
        assert tokens == ["i", "tone2", "k", "ɤ", "tone4"], tokens

    def test_yi_nian(self):
        """一年 -> 一 stays tone4 before 年 (pypinyin retains lexical tone)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("一年")
        assert tokens == ["i", "tone4", "n", "iɛn", "tone2"], tokens

    def test_yi_zhi(self):
        """一直 -> 一 tone4 + 直 tone2."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("一直")
        assert tokens == ["i", "tone4", "tʂ", "ɻ̩", "tone2"], tokens

    def test_yi_ding(self):
        """一定 -> 一 tone2 (sandhi'd before 定 tone4)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("一定")
        assert tokens == ["i", "tone2", "t", "iŋ", "tone4"], tokens

    def test_bu_shi(self):
        """不是 -> 不 reads as bú (tone2) before 是 (tone4)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("不是")
        assert tokens == ["p", "u", "tone2", "ʂ", "ɻ̩", "tone4"], tokens

    def test_bu_dui(self):
        """不对 -> 不 tone2 + 对 tone4."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("不对")
        assert tokens == ["p", "u", "tone2", "t", "ueɪ", "tone4"], tokens

    def test_bu_hao(self):
        """不好 -> 不 keeps tone4 before 好 tone3."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("不好")
        assert tokens == ["p", "u", "tone4", "x", "aʊ", "tone3"], tokens

    def test_third_tone_sandhi_nihao(self):
        """你好 -> 你 stays tone3 (sandhi not applied at IPA layer)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你好")
        assert tokens == ["n", "i", "tone2", "x", "aʊ", "tone3"], tokens

    def test_third_tone_henhao(self):
        """很好 -> 很 sandhi (tone2) + 好 tone3."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("很好")
        assert tokens == ["x", "ən", "tone2", "x", "aʊ", "tone3"], tokens

    def test_third_tone_laohu(self):
        """老虎 -> 老 sandhi'd to tone2."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("老虎")
        assert tokens == ["l", "aʊ", "tone2", "x", "u", "tone3"], tokens


@requires_zh
class TestProsody:
    def test_prosody_length_matches(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("你好世界")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_tone_info(self):
        """ProsodyInfo a1 carries tone number for Chinese characters."""
        from piper_plus_g2p.base import ProsodyInfo
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("你好")
        has_tone = any(
            isinstance(pi, ProsodyInfo) and 1 <= pi.a1 <= 5 for pi in prosody
        )
        assert has_tone, "Expected at least one ProsodyInfo with tone (a1=1..5)"
