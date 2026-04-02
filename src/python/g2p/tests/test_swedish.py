"""Tests for piper_plus_g2p.swedish -- SwedishPhonemizer.

Test cases derived from Go implementation (swedish_test.go) and the
piper_train SwedishPhonemizer.
"""

from piper_plus_g2p.base import ProsodyInfo
from piper_plus_g2p.swedish import SwedishPhonemizer, apply_retroflex

# ===========================================================================
# Helpers
# ===========================================================================


def _word_phonemes(word: str) -> str:
    """Return the joined phoneme string for a single word."""
    p = SwedishPhonemizer()
    tokens = p.phonemize(word)
    return "".join(tokens)


def _word_contains(word: str, ipa: str) -> bool:
    """Check if phoneme output of a word contains the given IPA substring."""
    return ipa in _word_phonemes(word)


def _word_not_contains(word: str, ipa: str) -> bool:
    """Check that phoneme output does NOT contain the given IPA substring."""
    return ipa not in _word_phonemes(word)


# ===========================================================================
# Long Vowel Tests
# ===========================================================================


class TestLongVowels:
    """V-01 to V-10: long vowels with single following consonant."""

    def test_gata_long_a(self):
        """V-01: a + single consonant -> long ɑː."""
        assert _word_contains("gata", "\u0251\u02d0")

    def test_vet_long_e(self):
        """V-02: e + single consonant -> eː."""
        assert _word_contains("vet", "e\u02d0")

    def test_fin_long_i(self):
        """V-03: i + single consonant -> iː."""
        assert _word_contains("fin", "i\u02d0")

    def test_sol_long_u(self):
        """V-04: o default + single consonant -> uː."""
        assert _word_contains("sol", "u\u02d0")

    def test_hus_long_barred_u(self):
        """V-05: u + single consonant -> ʉː."""
        assert _word_contains("hus", "\u0289\u02d0")

    def test_syn_long_y(self):
        """V-06: y + single consonant -> yː."""
        assert _word_contains("syn", "y\u02d0")

    def test_sal_long_ae(self):
        """V-07: ä + single consonant -> ɛː."""
        assert _word_contains("säl", "\u025b\u02d0")

    def test_ol_long_oe(self):
        """V-08: ö + single consonant -> øː."""
        assert _word_contains("öl", "\u00f8\u02d0")

    def test_ar_long_o(self):
        """V-09: å + single consonant -> oː."""
        assert _word_contains("år", "o\u02d0")

    def test_glas_long_a2(self):
        """V-10: glas single C after vowel -> long ɑː."""
        assert _word_contains("glas", "\u0251\u02d0")


# ===========================================================================
# Short Vowel Tests
# ===========================================================================


class TestShortVowels:
    """V-11 to V-20: short vowels with geminate/cluster."""

    def test_katt_short_a(self):
        """V-11: geminate -> short a (not ɑː)."""
        assert _word_contains("katt", "a")
        assert _word_not_contains("katt", "\u0251\u02d0")

    def test_fest_short_e(self):
        """V-12: cluster -> short ɛ (not eː)."""
        assert _word_contains("fest", "\u025b")
        assert _word_not_contains("fest", "e\u02d0")

    def test_flicka_short_i(self):
        """V-13: HARD_K exception + short ɪ."""
        assert _word_contains("flicka", "\u026a")

    def test_kort_short_o(self):
        """V-14: o + 2 consonants -> short ɔ."""
        assert _word_contains("kort", "\u0254")

    def test_hund_short_u(self):
        """V-15: cluster -> short ɵ (not ʉː)."""
        assert _word_contains("hund", "\u0275")
        assert _word_not_contains("hund", "\u0289\u02d0")

    def test_mygg_short_y(self):
        """V-16: geminate -> short ʏ."""
        assert _word_contains("mygg", "\u028f")

    def test_host_short_oe(self):
        """V-17: cluster -> short œ."""
        assert _word_contains("höst", "\u0153")

    def test_glass_short_a(self):
        """V-18: double s -> short a (not ɑː)."""
        assert _word_contains("glass", "a")
        assert _word_not_contains("glass", "\u0251\u02d0")

    def test_tack_short_a(self):
        """V-19: ck -> short a (not ɑː)."""
        assert _word_contains("tack", "a")
        assert _word_not_contains("tack", "\u0251\u02d0")

    def test_vett_short_e(self):
        """V-20: geminate -> short ɛ (not eː)."""
        assert _word_contains("vett", "\u025b")
        assert _word_not_contains("vett", "e\u02d0")


# ===========================================================================
# Consonant Rules - 3-char patterns
# ===========================================================================


class TestConsonant3Char:
    """C-01 to C-04: 3-character consonant patterns."""

    def test_skjorta_sj(self):
        """C-01: skj -> ɧ."""
        assert _word_contains("skjorta", "\u0267")

    def test_stjarna_sj(self):
        """C-02: stj -> ɧ."""
        assert _word_contains("stjärna", "\u0267")

    def test_schema_sj(self):
        """C-03: sch -> ɧ."""
        assert _word_contains("schema", "\u0267")

    def test_sang_ng(self):
        """C-04: sng rule, ng is processed as ŋ."""
        assert _word_contains("sång", "\u014b")


# ===========================================================================
# Consonant Rules - sk context-dependent
# ===========================================================================


class TestConsonantSK:
    """C-06 to C-12: sk + front/back vowel."""

    def test_sked_sk_front(self):
        """C-06: sk+e -> ɧ."""
        assert _word_contains("sked", "\u0267")

    def test_skinn_sk_front(self):
        """C-07: sk+i -> ɧ."""
        assert _word_contains("skinn", "\u0267")

    def test_sky_sk_front(self):
        """C-08: sk+y -> ɧ."""
        assert _word_contains("sky", "\u0267")

    def test_skal_sk_front(self):
        """C-09: sk+ä -> ɧ."""
        assert _word_contains("skäl", "\u0267")

    def test_skold_sk_front(self):
        """C-10: sk+ö -> ɧ."""
        assert _word_contains("sköld", "\u0267")

    def test_ska_sk_back(self):
        """C-11: sk+a -> sk (hard, no ɧ)."""
        assert _word_not_contains("ska", "\u0267")

    def test_skog_sk_back(self):
        """C-12: sk+o -> sk (hard, no ɧ)."""
        assert _word_not_contains("skog", "\u0267")


# ===========================================================================
# Consonant Rules - 2-char patterns
# ===========================================================================


class TestConsonant2Char:
    """C-13 to C-22: 2-character consonant patterns."""

    def test_sjuk_sj(self):
        """C-13: sj -> ɧ."""
        assert _word_contains("sjuk", "\u0267")

    def test_show_sh(self):
        """C-14: sh -> ɧ."""
        assert _word_contains("show", "\u0267")

    def test_chef_ch(self):
        """C-15: ch -> ɧ (default)."""
        assert _word_contains("chef", "\u0267")

    def test_och_ch_exception(self):
        """C-16: ch -> k (CH_EXCEPTIONS)."""
        assert _word_not_contains("och", "\u0267")

    def test_tjuv_tj(self):
        """C-17: tj -> ɕ."""
        assert _word_contains("tjuv", "\u0255")

    def test_kjol_kj(self):
        """C-18: kj -> ɕ."""
        assert _word_contains("kjol", "\u0255")

    def test_kung_ng(self):
        """C-19: ng -> ŋ."""
        assert _word_contains("kung", "\u014b")

    def test_bank_nk(self):
        """C-20: nk -> ŋ+k."""
        assert _word_contains("bank", "\u014b")

    def test_docka_ck(self):
        """C-21: ck -> k (short vowel ɔ)."""
        assert _word_contains("docka", "\u0254")

    def test_photo_ph(self):
        """C-22: ph -> f."""
        assert _word_contains("photo", "f")


# ===========================================================================
# Consonant Rules - 1-char and word-initial digraphs
# ===========================================================================


class TestConsonant1CharAndInitialDigraphs:
    """C-23 to C-30: word-initial digraphs and single-char rules."""

    def test_gjord_gj(self):
        """C-23: gj word-initial -> j."""
        assert _word_contains("gjord", "j")

    def test_djur_dj(self):
        """C-24: dj word-initial -> j."""
        assert _word_contains("djur", "j")

    def test_hjalp_hj(self):
        """C-25: hj word-initial -> j."""
        assert _word_contains("hjälp", "j")

    def test_ljus_lj(self):
        """C-26: lj word-initial -> j."""
        assert _word_contains("ljus", "j")

    def test_center_c_e(self):
        """C-27: c+e -> s."""
        assert _word_contains("center", "s")

    def test_camping_c_a(self):
        """C-28: c+a -> k."""
        assert _word_contains("camping", "k")

    def test_gnaga_gn_initial(self):
        """C-29: gn word-initial -> ɡ+n."""
        assert _word_contains("gnaga", "\u0261")

    def test_signal_gn_medial(self):
        """C-30: gn word-medial -> ŋ+n."""
        assert _word_contains("signal", "\u014b")


# ===========================================================================
# Soft/Hard k/g
# ===========================================================================


class TestSoftHardKG:
    """KG-01 to KG-15: soft/hard k and g before front vowels."""

    def test_soft_k_kop(self):
        """KG-01: k + ö -> ɕ (soft)."""
        assert _word_contains("köp", "\u0255")

    def test_hard_k_katt(self):
        """KG-02: k + a -> k (hard, back vowel)."""
        ph = _word_phonemes("katt")
        assert ph.startswith("\u02c8k")

    def test_soft_g_gora(self):
        """KG-03: g + ö -> j (soft)."""
        assert _word_contains("göra", "j")

    def test_hard_g_gata(self):
        """KG-04: g + a -> ɡ (hard, back vowel)."""
        assert _word_contains("gata", "\u0261")

    def test_hard_k_flicka(self):
        """KG-05: HARD_K: flicka -> k not ɕ."""
        assert _word_contains("flicka", "k")
        assert _word_not_contains("flicka", "\u0255")

    def test_hard_k_pojke(self):
        """KG-06: HARD_K: pojke -> k."""
        assert _word_contains("pojke", "k")

    def test_hard_k_socker(self):
        """KG-07: HARD_K: socker -> k."""
        assert _word_contains("socker", "k")

    def test_hard_k_kille(self):
        """KG-08: HARD_K: kille -> k."""
        assert _word_contains("kille", "k")

    def test_hard_k_soker(self):
        """KG-09: HARD_K: söker -> k."""
        assert _word_contains("söker", "k")

    def test_hard_g_finger(self):
        """KG-10: HARD_G: finger."""
        from piper_plus_g2p.swedish import _is_hard_g

        assert _is_hard_g("finger")

    def test_hard_g_ger(self):
        """KG-11: HARD_G: ger."""
        from piper_plus_g2p.swedish import _is_hard_g

        assert _is_hard_g("ger")

    def test_hard_g_ge_output(self):
        """KG-12: ge -> ɡ in output."""
        assert _word_contains("ge", "\u0261")

    def test_hard_g_agera(self):
        """KG-13: -era verb -> hard."""
        from piper_plus_g2p.swedish import _is_hard_g

        assert _is_hard_g("agera")

    def test_hard_g_berg(self):
        """KG-14: -erg -> hard."""
        from piper_plus_g2p.swedish import _is_hard_g

        assert _is_hard_g("berg")

    def test_hard_g_borg(self):
        """KG-15: -org -> hard."""
        from piper_plus_g2p.swedish import _is_hard_g

        assert _is_hard_g("borg")


# ===========================================================================
# Retroflex Assimilation
# ===========================================================================


class TestRetroflexBasic:
    """RT-01 to RT-05: basic retroflex assimilation."""

    def test_kort_rt(self):
        """RT-01: r+t -> ʈ."""
        assert _word_contains("kort", "\u0288")

    def test_bord_rd(self):
        """RT-02: r+d -> ɖ."""
        assert _word_contains("bord", "\u0256")

    def test_fors_rs(self):
        """RT-03: r+s -> ʂ."""
        assert _word_contains("fors", "\u0282")

    def test_barn_rn(self):
        """RT-04: r+n -> ɳ."""
        assert _word_contains("barn", "\u0273")

    def test_rl_direct(self):
        """RT-05: r+l -> ɭ (direct apply_retroflex test)."""
        result = apply_retroflex(["r", "l"])
        assert "\u026d" in result


class TestRetroflexCascade:
    """RT-06 to RT-08: retroflex cascade behavior."""

    def test_cascade_rst(self):
        """RT-06: r+s+t -> ʂ+ʈ (cascade)."""
        result = apply_retroflex(["r", "s", "t"])
        assert "\u0282" in result  # ʂ
        assert "\u0288" in result  # ʈ

    def test_cascade_stops_at_l(self):
        """RT-07: r+l stops cascade (ɭ is non-propagating)."""
        result = apply_retroflex(["r", "l", "t"])
        assert "\u026d" in result  # ɭ
        assert "t" in result  # t stays (cascade stopped by ɭ)

    def test_no_cascade_rr(self):
        """RT-08: r+r -> no assimilation (geminate block)."""
        result = apply_retroflex(["r", "r", "t"])
        assert "r" in result
        assert "t" in result  # t stays


# ===========================================================================
# Stress Detection
# ===========================================================================


class TestStress:
    """Stress marker tests."""

    def test_stress_marker_present(self):
        """Stressed content words have primary stress marker."""
        p = SwedishPhonemizer()
        tokens = p.phonemize("Hej")
        assert "\u02c8" in tokens

    def test_function_word_no_stress(self):
        """Function words have no stress marker."""
        p = SwedishPhonemizer()
        tokens = p.phonemize("och")
        assert "\u02c8" not in tokens

    def test_stress_attracting_suffix(self):
        """Words with stress-attracting suffixes are stressed on the suffix."""
        from piper_plus_g2p.swedish import detect_stress

        # -tion suffix: stress on syllable after stem
        assert detect_stress("station") > 0

    def test_monosyllabic_stress(self):
        """Monosyllabic words are stressed on syllable 0."""
        from piper_plus_g2p.swedish import detect_stress

        assert detect_stress("hus") == 0


# ===========================================================================
# Prosody
# ===========================================================================


class TestProsody:
    """Prosody output tests."""

    def test_prosody_length_matches_tokens(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        p = SwedishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Hej världen")
        assert len(tokens) == len(prosody)

    def test_prosody_stress_value(self):
        """Stressed phonemes have a2=2 in prosody info."""
        p = SwedishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Hej")
        has_stress = any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
        assert has_stress, "Expected at least one ProsodyInfo with a2=2 (stress)"

    def test_prosody_a3_word_count(self):
        """a3 contains the word phoneme count (excluding stress markers)."""
        p = SwedishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("sol")
        # Filter out stress marker
        non_stress = [
            pi for t, pi in zip(tokens, prosody, strict=False) if t != "\u02c8"
        ]
        if non_stress:
            # All non-stress phonemes should have same a3
            a3_values = {pi.a3 for pi in non_stress if pi is not None}
            assert len(a3_values) == 1, f"Expected uniform a3, got {a3_values}"


# ===========================================================================
# language_code property
# ===========================================================================


class TestLanguageCode:
    def test_language_code(self):
        """SwedishPhonemizer.language_code returns 'sv'."""
        p = SwedishPhonemizer()
        assert p.language_code == "sv"


# ===========================================================================
# Loanword handling
# ===========================================================================


class TestLoanwords:
    """Loanword suffix and prefix tests."""

    def test_tion_suffix(self):
        """Words ending in -tion get ɧ uː n."""
        assert _word_contains("station", "\u0267")

    def test_age_suffix_loanword(self):
        """Loanword -age gets ɑː ɧ."""
        assert _word_contains("garage", "\u0251\u02d0")
        assert _word_contains("garage", "\u0267")

    def test_age_suffix_native(self):
        """Native -age words do NOT get loanword treatment."""
        # "mage" is in AGE_NATIVE_WORDS
        assert _word_not_contains("mage", "\u0267")


# ===========================================================================
# Word boundary and multi-word
# ===========================================================================


class TestMultiWord:
    def test_word_boundary(self):
        """Multi-word text includes space as word boundary."""
        p = SwedishPhonemizer()
        tokens = p.phonemize("Hej världen")
        assert " " in tokens

    def test_punctuation(self):
        """Punctuation characters are passed through."""
        p = SwedishPhonemizer()
        tokens = p.phonemize("Hej!")
        assert "!" in tokens


# ===========================================================================
# Edge cases / sanitization
# ===========================================================================


class TestEdgeCases:
    def test_empty_string(self):
        """Empty string returns empty list."""
        p = SwedishPhonemizer()
        assert p.phonemize("") == []

    def test_sanitize_rejects_non_str(self):
        """Non-str input raises TypeError."""
        p = SwedishPhonemizer()
        try:
            p.phonemize(123)  # type: ignore[arg-type]
            raise AssertionError("Expected TypeError")
        except TypeError:
            pass

    def test_o_long_as_oo(self):
        """Words in O_LONG_AS_OO produce oː instead of uː."""
        # "mor" is in O_LONG_AS_OO
        assert _word_contains("mor", "o\u02d0")
        assert _word_not_contains("mor", "u\u02d0")
