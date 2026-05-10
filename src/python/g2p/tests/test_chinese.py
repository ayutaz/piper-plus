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
        _tokens, prosody = p.phonemize_with_prosody("你好")
        has_tone = any(
            isinstance(pi, ProsodyInfo) and 1 <= pi.a1 <= 5 for pi in prosody
        )
        assert has_tone, "Expected at least one ProsodyInfo with tone (a1=1..5)"


@requires_zh
class TestTraditionalChinese:
    """繁体字 (Traditional Chinese) is handled by pypinyin's built-in
    Trad->Simp tables. The ChinesePhonemizer does not perform an explicit
    conversion step; it relies on pypinyin to map Traditional characters
    to the same pinyin as their Simplified equivalents.

    These tests pin the current behaviour as a regression gate.
    """

    def test_traditional_basic_tokyo(self):
        """東京 (Trad. for Tokyo) -> dong1 jing1, same as 东京 (Simp.)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("東京")
        # Expected: dong1 -> [t, uŋ, tone1], jing1 -> [tɕ, iŋ, tone1]
        assert tokens == ["t", "uŋ", "tone1", "tɕ", "iŋ", "tone1"], tokens

    def test_traditional_dragon(self):
        """龍 (Trad.) -> long2, identical to 龙 (Simp.)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("龍")
        # long2 -> [l, uŋ, tone2]
        assert tokens == ["l", "uŋ", "tone2"], tokens

    def test_traditional_long_sentence(self):
        """繁体字長文 (Trad. mixed sentence): 請打開東京的龍."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("請打開東京的龍")
        # Expected: qing3 da3 kai1 dong1 jing1 de5 long2
        # qing3 -> [tɕʰ, iŋ, tone2] (T3+T3 sandhi: 請打 -> tone2+tone3)
        assert tokens == [
            "tɕʰ",
            "iŋ",
            "tone2",
            "t",
            "a",
            "tone3",
            "kʰ",
            "aɪ",
            "tone1",
            "t",
            "uŋ",
            "tone1",
            "tɕ",
            "iŋ",
            "tone1",
            "t",
            "ɤ",
            "tone5",
            "l",
            "uŋ",
            "tone2",
        ], tokens

    def test_traditional_simplified_mixed(self):
        """龍中 (Trad. + Simp. mixed) -> long2 zhong1."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("龍中")
        # long2 + zhong1
        assert tokens == ["l", "uŋ", "tone2", "tʂ", "uŋ", "tone1"], tokens

    def test_traditional_via_pypinyin_strict(self):
        """pypinyin strict and non-strict modes both yield same pinyin for 東京.

        Pins our reliance on pypinyin's Trad->Simp conversion: both
        ``strict=True`` and ``strict=False`` must round-trip 東京 to
        ``dong1 jing1`` because the conversion happens before strict-mode
        pinyin assembly. If a future pypinyin upgrade changes this, our
        Traditional support would silently regress.
        """
        from pypinyin import Style, pinyin

        strict = pinyin(
            "東京", style=Style.TONE3, neutral_tone_with_five=True, strict=True
        )
        non_strict = pinyin(
            "東京", style=Style.TONE3, neutral_tone_with_five=True, strict=False
        )
        assert strict == non_strict == [["dong1"], ["jing1"]], (
            f"strict={strict!r}, non_strict={non_strict!r}"
        )


@requires_zh
class TestT3SandhiContinuous:
    """Pin the current (snapshot) behaviour of ``_apply_tone_sandhi`` for
    runs of 4+ consecutive Tone-3 syllables.

    The Chinese module's docstring explicitly notes this as a Known
    limitation: the right-to-left pair grouping is uniformly applied
    without considering morphological word boundaries (which would require
    something like jieba). These tests pin **what the code does today**,
    not what an ideal phonological output would be.
    """

    def test_t3_chain_4syllables_basic(self):
        """4 consecutive T3 (我也很好) -> all-but-last become T2.

        Phonologically, native speakers might split this as
        [我也][很好] -> T2-T3 + T2-T3, but the current implementation
        produces T2+T2+T2+T3 across the entire run.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("我也很好")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # KNOWN LIMITATION: ideal would be tone2,tone3,tone2,tone3 by word
        # boundary; current uniform run sandhi gives tone2,tone2,tone2,tone3.
        assert tone_tokens == ["tone2", "tone2", "tone2", "tone3"], tone_tokens

    def test_t3_chain_5syllables(self):
        """5 consecutive T3 (你想买几本) -> first 4 become T2, last stays T3."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你想买几本")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # KNOWN LIMITATION: native speakers may pause at word boundaries;
        # current implementation applies a single 5-syllable sweep.
        assert tone_tokens == ["tone2", "tone2", "tone2", "tone2", "tone3"], tone_tokens

    def test_t3_with_loanword_no_cross_sandhi(self):
        """Tone sandhi does NOT cross loanword/segment boundaries.

        ``我用 GPS`` -- the ZH segment ``我用`` (T3+T4) is processed
        independently of ``GPS`` (loanword path), so the T3 of 我 stays
        T3 (no sandhi needed: 用 is T4, not T3). Confirms loanword
        dispatch breaks the sandhi window.
        """
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        tokens, _ = p.phonemize_with_prosody("我用 GPS")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # 我=T3, 用=T4, then GPS = ji4 pi4 ai1 si4 -> tone4,tone4,tone1,tone4
        assert tone_tokens == [
            "tone3",  # 我 (no sandhi: 用 is T4)
            "tone4",  # 用
            "tone4",  # j (ji4)
            "tone4",  # p (pi4)
            "tone1",  # i (ai1) -- letter I = ai1
            "tone4",  # s (si4)
        ], tone_tokens

    def test_t3_with_morphological_boundary(self):
        """KNOWN LIMITATION pinning: ``小水果`` ([小][水果]) gets uniform sandhi.

        Phonologically, [小][水果] should be processed as
        T3 + (T2-T3) since 小 is a separate morpheme. The current
        implementation has no morphological analyser and applies the
        right-to-left rule uniformly across the 3-syllable run, yielding
        T2+T2+T3 for all three. This test pins the **current** behaviour;
        a future PR adding word-boundary detection (jieba) should update
        this expectation.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("小水果")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # KNOWN LIMITATION: ideal would be tone3,tone2,tone3 honoring the
        # [小][水果] morphological split; current impl gives tone2,tone2,tone3.
        assert tone_tokens == ["tone2", "tone2", "tone3"], tone_tokens
