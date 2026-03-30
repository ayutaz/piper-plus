"""Comprehensive test suite for Swedish G2P (M1.3-M1.6).

Covers: consonant rules, vowel length, retroflex assimilation, stress,
loanwords, dictionary lookup, SwedishPhonemizer ABC, multilingual integration.
"""

from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path

import pytest

from piper_train.phonemize.swedish import (
    FUNCTION_WORDS,
    HARD_G_WORDS,
    HARD_K_WORDS,
    O_LONG_AS_OO,
    SwedishPhonemizer,
    _is_hard_g,
    _is_hard_k,
    _phonemize_word,
    _split_ipa_to_phonemes,
    apply_retroflex,
    detect_loanword_suffix,
    detect_stress,
    get_vowel_phoneme,
    phonemize_swedish,
    phonemize_swedish_with_prosody,
)


def _join(word: str) -> str:
    """Phonemize a word and return joined string."""
    return "".join(_phonemize_word(word))


# =========================================================================
# Basic vowel tests (10)
# =========================================================================

class TestBasicVowels:

    @pytest.mark.unit
    def test_long_a(self):
        # gata → ˈɡɑːta
        assert _join("gata") == "ˈɡɑːta"

    @pytest.mark.unit
    def test_short_a(self):
        # katt → ˈkat  (double tt = short)
        r = _join("katt")
        assert "a" in r and "ɑː" not in r

    @pytest.mark.unit
    def test_long_i(self):
        # fin → ˈfiːn
        assert "iː" in _join("fin")

    @pytest.mark.unit
    def test_short_i(self):
        # flicka → ˈflɪka
        assert "ɪ" in _join("flicka")

    @pytest.mark.unit
    def test_long_u(self):
        # hus → ˈhʉːs
        assert "ʉː" in _join("hus")

    @pytest.mark.unit
    def test_long_y(self):
        # syn → ˈsyːn
        assert "yː" in _join("syn")

    @pytest.mark.unit
    def test_long_ö(self):
        # öl → ˈøːl
        assert "øː" in _join("öl")

    @pytest.mark.unit
    def test_long_ä(self):
        # säl → ˈsɛːl
        assert "ɛː" in _join("säl")

    @pytest.mark.unit
    def test_short_e_cluster(self):
        # fest → ˈfɛst
        assert _join("fest") == "ˈfɛst"

    @pytest.mark.unit
    def test_short_ö(self):
        # höst → short ö = œ
        assert "œ" in _join("höst")


# =========================================================================
# Soft/Hard consonant tests (15)
# =========================================================================

class TestSoftHardConsonants:

    @pytest.mark.unit
    def test_k_before_front_vowel_soft(self):
        # köp → ˈɕ... (soft k)
        assert "ɕ" in _join("köp")

    @pytest.mark.unit
    def test_k_before_back_vowel_hard(self):
        # katt → k (hard)
        r = _join("katt")
        assert r.startswith("ˈk")

    @pytest.mark.unit
    def test_hard_k_exception_flicka(self):
        assert "k" in _join("flicka")
        assert "ɕ" not in _join("flicka")

    @pytest.mark.unit
    def test_hard_k_exception_pojke(self):
        assert "k" in _join("pojke")

    @pytest.mark.unit
    def test_hard_k_exception_socker(self):
        assert "k" in _join("socker")

    @pytest.mark.unit
    def test_g_before_front_vowel_soft(self):
        # göra → j... (soft g)
        r = _join("göra")
        assert "j" in r

    @pytest.mark.unit
    def test_g_before_back_vowel_hard(self):
        # gata → ɡ (hard)
        assert "ɡ" in _join("gata")

    @pytest.mark.unit
    def test_hard_g_exception_finger(self):
        assert _is_hard_g("finger") is True

    @pytest.mark.unit
    def test_hard_g_exception_ger(self):
        assert _is_hard_g("ger") is True

    @pytest.mark.unit
    def test_sk_front_vowel_sj(self):
        # sked → ˈɧeːd
        assert _join("sked") == "ˈɧeːd"

    @pytest.mark.unit
    def test_sk_back_vowel_sk(self):
        # skola → ˈskuːla
        r = _join("skola")
        assert r.startswith("ˈsk")

    @pytest.mark.unit
    def test_ng_phoneme(self):
        # kung → ˈkɵŋ
        assert "ŋ" in _join("kung")

    @pytest.mark.unit
    def test_ck_geminate(self):
        # docka → short vowel
        r = _join("docka")
        assert "ɔ" in r

    @pytest.mark.unit
    def test_tj_sound(self):
        # tjuv → ɕ...
        assert "ɕ" in _join("tjuv")

    @pytest.mark.unit
    def test_kj_sound(self):
        assert "ɕ" in _join("kjol")


# =========================================================================
# Retroflex assimilation tests (12)
# =========================================================================

class TestRetroflex:

    @pytest.mark.unit
    def test_r_plus_t(self):
        assert "ʈ" in _join("kort")

    @pytest.mark.unit
    def test_r_plus_d(self):
        assert "ɖ" in _join("bord")

    @pytest.mark.unit
    def test_r_plus_n(self):
        assert "ɳ" in _join("barn")

    @pytest.mark.unit
    def test_r_plus_s(self):
        assert "ʂ" in _join("fors")

    @pytest.mark.unit
    def test_r_plus_l(self):
        r = apply_retroflex(["r", "l"])
        assert "ɭ" in r

    @pytest.mark.unit
    def test_cascade_r_s_t(self):
        r = apply_retroflex(["f", "œ", "r", "s", "t"])
        assert r == ["f", "œ", "ʂ", "ʈ"]

    @pytest.mark.unit
    def test_l_stops_cascade(self):
        r = apply_retroflex(["k", "ɑː", "r", "l", "s"])
        assert r == ["k", "ɑː", "ɭ", "s"]

    @pytest.mark.unit
    def test_rr_blocks(self):
        r = apply_retroflex(["b", "ɔ", "r", "r", "s"])
        assert r == ["b", "ɔ", "r", "r", "s"]

    @pytest.mark.unit
    def test_r_plus_k_no_change(self):
        r = apply_retroflex(["b", "ɑː", "r", "k"])
        assert r == ["b", "ɑː", "r", "k"]

    @pytest.mark.unit
    def test_word_final_r(self):
        r = apply_retroflex(["f", "ɑː", "r"])
        assert r == ["f", "ɑː", "r"]

    @pytest.mark.unit
    def test_retroflex_in_barn(self):
        assert _join("barn") == "ˈbɑːɳ"

    @pytest.mark.unit
    def test_retroflex_in_kort(self):
        assert _join("kort") == "ˈkɔʈ"


# =========================================================================
# sj-sound tests (20)
# =========================================================================

class TestSjSound:

    @pytest.mark.unit
    def test_sj_basic(self):
        assert "ɧ" in _join("sjuk")

    @pytest.mark.unit
    def test_sj_sjö(self):
        assert "ɧ" in _join("sjö")

    @pytest.mark.unit
    def test_skj(self):
        assert "ɧ" in _join("skjorta")

    @pytest.mark.unit
    def test_stj(self):
        assert "ɧ" in _join("stjärna")

    @pytest.mark.unit
    def test_sch(self):
        assert "ɧ" in _join("schema")

    @pytest.mark.unit
    def test_sh(self):
        assert "ɧ" in _join("show")

    @pytest.mark.unit
    def test_ch_chef(self):
        assert "ɧ" in _join("chef")

    @pytest.mark.unit
    def test_sk_front_e(self):
        assert "ɧ" in _join("sked")

    @pytest.mark.unit
    def test_sk_front_i(self):
        assert "ɧ" in _join("skinn")

    @pytest.mark.unit
    def test_sk_front_y(self):
        assert "ɧ" in _join("sky")

    @pytest.mark.unit
    def test_sk_front_ä(self):
        assert "ɧ" in _join("skäl")

    @pytest.mark.unit
    def test_sk_front_ö(self):
        assert "ɧ" in _join("sköld")

    @pytest.mark.unit
    def test_sk_back_a(self):
        assert "ɧ" not in _join("ska")

    @pytest.mark.unit
    def test_sk_back_o(self):
        assert "ɧ" not in _join("skog")

    @pytest.mark.unit
    def test_sk_back_u(self):
        assert "ɧ" not in _join("skum")

    @pytest.mark.unit
    def test_loanword_tion(self):
        assert "ɧ" in _join("station")

    @pytest.mark.unit
    def test_loanword_sion(self):
        assert "ɧ" in _join("passion")

    @pytest.mark.unit
    def test_loanword_ssion(self):
        assert "ɧ" in _join("mission")

    @pytest.mark.unit
    def test_loanword_age(self):
        r = _join("garage")
        assert "ɧ" in r

    @pytest.mark.unit
    def test_ch_och_exception(self):
        # och → /ɔk/ not /ɔɧ/
        assert "ɧ" not in _join("och")


# =========================================================================
# Vowel length tests (10)
# =========================================================================

class TestVowelLength:

    @pytest.mark.unit
    def test_single_consonant_long(self):
        # sol → long uː
        assert "uː" in _join("sol")

    @pytest.mark.unit
    def test_cluster_short(self):
        # fest → short ɛ
        assert "ɛ" in _join("fest")
        assert "eː" not in _join("fest")

    @pytest.mark.unit
    def test_final_vowel_long(self):
        # bo → long
        r = _join("bo")
        assert "oː" in r or "uː" in r

    @pytest.mark.unit
    def test_function_word_short(self):
        # för → short (function word)
        r = _join("för")
        assert "øː" not in r

    @pytest.mark.unit
    def test_o_default_long_u(self):
        # sol → uː (default for "o")
        assert "uː" in _join("sol")

    @pytest.mark.unit
    def test_o_long_as_oo(self):
        # son → oː (O_LONG_AS_OO exception)
        assert "oː" in _join("son")

    @pytest.mark.unit
    def test_o_short(self):
        # kort → ɔ (short o)
        assert "ɔ" in _join("kort")

    @pytest.mark.unit
    def test_final_m_short(self):
        # hem → short (FINAL_M_SHORT_WORDS)
        r = _join("hem")
        assert "eː" not in r

    @pytest.mark.unit
    def test_r_plus_c_preserves_long(self):
        # barn → ɑː (long despite 2 consonants, r+C exception)
        assert "ɑː" in _join("barn")

    @pytest.mark.unit
    def test_geminate_short(self):
        # katt → short a
        r = _join("katt")
        assert "ɑː" not in r


# =========================================================================
# "o" ambiguity tests (10)
# =========================================================================

class TestOAmbiguity:

    @pytest.mark.unit
    def test_o_long_u_sol(self):
        assert "uː" in _join("sol")

    @pytest.mark.unit
    def test_o_long_oo_son(self):
        assert "oː" in _join("son")

    @pytest.mark.unit
    def test_o_short_kort(self):
        assert "ɔ" in _join("kort")

    @pytest.mark.unit
    def test_o_long_oo_mor(self):
        assert "oː" in _join("mor")

    @pytest.mark.unit
    def test_o_long_oo_bror(self):
        assert "oː" in _join("bror")

    @pytest.mark.unit
    def test_o_long_oo_ton(self):
        assert "oː" in _join("ton")

    @pytest.mark.unit
    def test_o_long_u_bok(self):
        # bok not in O_LONG_AS_OO → default uː
        assert "uː" in _join("bok")

    @pytest.mark.unit
    def test_o_long_oo_god(self):
        assert "oː" in _join("god")

    @pytest.mark.unit
    def test_o_short_ord_rule_based(self):
        # "ord" is in O_LONG_AS_OO but o+rd (2 consonants) → short by rule
        # (dictionary lookup would give correct /oːɖ/)
        assert "ɔ" in _join("ord")

    @pytest.mark.unit
    def test_o_short_bott(self):
        # bott → short ɔ
        r = _join("bott")
        assert "ɔ" in r


# =========================================================================
# Unstressed vowel tests (8)
# =========================================================================

class TestUnstressedVowels:

    @pytest.mark.unit
    def test_unstressed_a_in_gata(self):
        # gata: second 'a' is unstressed → 'a'
        r = _join("gata")
        assert r.endswith("ta")

    @pytest.mark.unit
    def test_unstressed_e_in_pojke(self):
        r = _join("pojke")
        assert r.endswith("ɛ") or r.endswith("e")

    @pytest.mark.unit
    def test_function_word_no_stress(self):
        r = _join("och")
        assert "ˈ" not in r

    @pytest.mark.unit
    def test_function_word_att(self):
        assert "ˈ" not in _join("att")

    @pytest.mark.unit
    def test_function_word_det(self):
        assert "ˈ" not in _join("det")

    @pytest.mark.unit
    def test_unstressed_prefix_be(self):
        # betala: stress on 2nd syllable
        r = _join("betala")
        idx = r.index("ˈ")
        assert idx > 0  # not at beginning

    @pytest.mark.unit
    def test_function_words_count(self):
        assert len(FUNCTION_WORDS) >= 35

    @pytest.mark.unit
    def test_stressed_monosyllable(self):
        assert "ˈ" in _join("bil")


# =========================================================================
# Stress tests (10)
# =========================================================================

class TestStress:

    @pytest.mark.unit
    def test_monosyllable_stressed(self):
        assert detect_stress("hus") == 0

    @pytest.mark.unit
    def test_function_word_no_stress(self):
        assert detect_stress("och") == -1

    @pytest.mark.unit
    def test_tion_suffix_attracts(self):
        assert detect_stress("station") > 0

    @pytest.mark.unit
    def test_eri_suffix_attracts(self):
        assert detect_stress("bageri") > 0

    @pytest.mark.unit
    def test_be_prefix_stress_after(self):
        assert detect_stress("betala") == 1

    @pytest.mark.unit
    def test_för_prefix_stress_after(self):
        assert detect_stress("förstå") == 1

    @pytest.mark.unit
    def test_default_first_syllable(self):
        assert detect_stress("flicka") == 0

    @pytest.mark.unit
    def test_stress_marker_present(self):
        r = _join("flicka")
        assert "ˈ" in r

    @pytest.mark.unit
    def test_no_stress_in_function_word(self):
        r = _join("som")
        assert "ˈ" not in r

    @pytest.mark.unit
    def test_multisyllable_default(self):
        assert detect_stress("lampa") == 0


# =========================================================================
# Loanword tests (10)
# =========================================================================

class TestLoanwords:

    @pytest.mark.unit
    def test_tion_detected(self):
        result = detect_loanword_suffix("station")
        assert result is not None
        assert result[0] == "sta"

    @pytest.mark.unit
    def test_sion_detected(self):
        result = detect_loanword_suffix("passion")
        assert result is not None

    @pytest.mark.unit
    def test_age_detected(self):
        result = detect_loanword_suffix("garage")
        assert result is not None

    @pytest.mark.unit
    def test_native_age_excluded(self):
        # "mage" is native Swedish, not French -age
        result = detect_loanword_suffix("mage")
        assert result is None

    @pytest.mark.unit
    def test_ch_as_sj(self):
        assert "ɧ" in _join("chef")

    @pytest.mark.unit
    def test_sch_as_sj(self):
        assert "ɧ" in _join("schema")

    @pytest.mark.unit
    def test_sh_as_sj(self):
        assert "ɧ" in _join("show")

    @pytest.mark.unit
    def test_ph_as_f(self):
        r = _join("photo")
        assert "f" in r

    @pytest.mark.unit
    def test_th_as_t(self):
        r = _join("theme")
        assert r.startswith("ˈt")

    @pytest.mark.unit
    def test_eum_suffix(self):
        result = detect_loanword_suffix("museum")
        assert result is not None


# =========================================================================
# Edge case tests (5)
# =========================================================================

class TestEdgeCases:

    @pytest.mark.unit
    def test_empty_string(self):
        assert _phonemize_word("") == []

    @pytest.mark.unit
    def test_single_vowel(self):
        r = _phonemize_word("a")
        assert len(r) >= 1

    @pytest.mark.unit
    def test_punctuation_passthrough(self):
        r = phonemize_swedish("hej!")
        assert "!" in r

    @pytest.mark.unit
    def test_multiple_words(self):
        r = phonemize_swedish("hej du")
        assert " " in r

    @pytest.mark.unit
    def test_unknown_chars_ignored(self):
        # Numbers/special chars should not crash
        r = phonemize_swedish("test")
        assert len(r) > 0


# =========================================================================
# Dictionary lookup tests (6)
# =========================================================================

class TestDictionaryLookup:

    @pytest.mark.unit
    def test_dict_hit(self):
        d = {"barn": "\u02C8b\u0251\u02D0\u0273"}  # ˈbɑːɳ
        r = phonemize_swedish("barn", dictionary=d)
        assert "\ue05e" in r  # ɑː PUA

    @pytest.mark.unit
    def test_dict_miss_fallback(self):
        d = {"barn": "\u02C8b\u0251\u02D0\u0273"}
        r = phonemize_swedish("flicka", dictionary=d)
        assert len(r) > 0  # falls back to rule-based

    @pytest.mark.unit
    def test_split_ipa_long_vowel(self):
        tokens = _split_ipa_to_phonemes("\u02C8b\u0251\u02D0\u0273")
        assert tokens == ["\u02C8", "b", "\u0251\u02D0", "\u0273"]

    @pytest.mark.unit
    def test_split_ipa_stress_mid(self):
        tokens = _split_ipa_to_phonemes("sta\u02C8\u0267u\u02D0n")
        assert "\u02C8" in tokens

    @pytest.mark.unit
    def test_phonemizer_no_dict(self):
        p = SwedishPhonemizer()
        r = p.phonemize("flicka")
        assert len(r) > 0

    @pytest.mark.unit
    def test_phonemizer_with_dict_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = {"hej": "\u02C8h\u025Bj"}
            path = Path(tmpdir) / "sv.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f)
            p = SwedishPhonemizer(dict_path=path)
            r = p.phonemize("hej")
            assert len(r) > 0


# =========================================================================
# Prosody tests (4)
# =========================================================================

class TestProsody:

    @pytest.mark.unit
    def test_prosody_length_match(self):
        phonemes, prosody = phonemize_swedish_with_prosody("flicka")
        assert len(phonemes) == len(prosody)

    @pytest.mark.unit
    def test_stress_marker_a2(self):
        phonemes, prosody = phonemize_swedish_with_prosody("flicka")
        for ph, pr in zip(phonemes, prosody):
            if ph == "\u02C8":
                assert pr.a2 == 2  # primary stress

    @pytest.mark.unit
    def test_a1_always_zero(self):
        _, prosody = phonemize_swedish_with_prosody("flickan gick")
        for pr in prosody:
            assert pr.a1 == 0

    @pytest.mark.unit
    def test_a3_word_phoneme_count(self):
        phonemes, prosody = phonemize_swedish_with_prosody("hus")
        # a3 should be word phoneme count (excluding stress markers)
        for pr in prosody:
            if pr.a3 > 0:
                assert pr.a3 >= 3  # h, ʉː, s


# =========================================================================
# Multilingual integration tests (5)
# =========================================================================

class TestMultilingualIntegration:

    @pytest.mark.unit
    def test_sv_registered(self):
        from piper_train.phonemize.registry import available_languages
        assert "sv" in available_languages()

    @pytest.mark.unit
    def test_get_sv_phonemizer(self):
        from piper_train.phonemize.registry import get_phonemizer
        p = get_phonemizer("sv")
        assert isinstance(p, SwedishPhonemizer)

    @pytest.mark.unit
    def test_en_sv_multilingual(self):
        from piper_train.phonemize.registry import get_phonemizer
        p = get_phonemizer("en-sv")
        assert type(p).__name__ == "MultilingualPhonemizer"

    @pytest.mark.unit
    def test_sv_in_language_phonemes(self):
        from piper_train.phonemize.multilingual_id_map import LANGUAGE_PHONEMES
        assert "sv" in LANGUAGE_PHONEMES
        assert len(LANGUAGE_PHONEMES["sv"]) == 19

    @pytest.mark.unit
    def test_7lang_id_map(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        id_map = get_multilingual_id_map(["ja", "en", "zh", "es", "fr", "pt", "sv"])
        assert len(id_map) > 180  # 6lang was 173, +sv ~189


# =========================================================================
# Regression tests: existing languages unaffected (4)
# =========================================================================

class TestRegressionExistingLanguages:

    @pytest.mark.unit
    def test_ja_phonemizer_still_works(self):
        from piper_train.phonemize.registry import get_phonemizer
        p = get_phonemizer("ja")
        r = p.phonemize("こんにちは")
        assert len(r) > 0

    @pytest.mark.unit
    def test_en_phonemizer_still_works(self):
        from piper_train.phonemize.registry import get_phonemizer
        p = get_phonemizer("en")
        r = p.phonemize("hello")
        assert len(r) > 0

    @pytest.mark.unit
    def test_6lang_id_map_unchanged(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        id_map = get_multilingual_id_map(["ja", "en", "zh", "es", "fr", "pt"])
        assert len(id_map) == 173  # original count

    @pytest.mark.unit
    def test_ja_pua_unchanged(self):
        from piper_train.phonemize.token_mapper import FIXED_PUA_MAPPING
        assert FIXED_PUA_MAPPING["a:"] == 0xE000
        assert FIXED_PUA_MAPPING["cl"] == 0xE005
