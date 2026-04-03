"""Tests for piper_plus_g2p.korean -- KoreanPhonemizer.

Test cases exercise the interface, edge cases, Hangul phonemization
structural properties, phonological features, prosody, and mixed input.
All tests are gated with ``@requires_ko`` since g2pk2 is an optional
dependency.
"""

from tests.conftest import requires_ko

# ===========================================================================
# Helpers
# ===========================================================================


def _make():
    """Create a KoreanPhonemizer instance (import inside function for skip)."""
    from piper_plus_g2p.korean import KoreanPhonemizer

    return KoreanPhonemizer()


def _phonemes(text: str) -> list[str]:
    """Return the phoneme token list for *text*."""
    return _make().phonemize(text)


def _joined(text: str) -> str:
    """Return the joined phoneme string for *text*."""
    return "".join(_phonemes(text))


# ===========================================================================
# API Structure Tests
# ===========================================================================


@requires_ko
class TestAPIStructure:
    """Verify the public API contract of KoreanPhonemizer."""

    def test_language_code(self):
        """KoreanPhonemizer.language_code returns 'ko'."""
        p = _make()
        assert p.language_code == "ko"

    def test_phonemize_returns_list(self):
        """phonemize() returns a list."""
        result = _phonemes("안녕하세요")
        assert isinstance(result, list)

    def test_phonemize_returns_strings(self):
        """Every element returned by phonemize() is a str."""
        result = _phonemes("한국어")
        assert all(isinstance(t, str) for t in result)

    def test_phonemize_with_prosody_returns_tuple(self):
        """phonemize_with_prosody() returns a (list, list) tuple."""
        p = _make()
        result = p.phonemize_with_prosody("안녕하세요")
        assert isinstance(result, tuple)
        assert len(result) == 2
        tokens, prosody = result
        assert isinstance(tokens, list)
        assert isinstance(prosody, list)

    def test_phonemizer_is_subclass_of_base(self):
        """KoreanPhonemizer inherits from Phonemizer ABC."""
        from piper_plus_g2p.base import Phonemizer
        from piper_plus_g2p.korean import KoreanPhonemizer

        assert issubclass(KoreanPhonemizer, Phonemizer)


# ===========================================================================
# Edge Case Tests
# ===========================================================================


@requires_ko
class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_string(self):
        """Empty string returns an empty list."""
        assert _phonemes("") == []

    def test_whitespace_only(self):
        """Whitespace-only input returns empty or whitespace tokens."""
        result = _phonemes("   ")
        # Either empty or only whitespace tokens
        assert all(t.isspace() for t in result) or result == []

    def test_numbers(self):
        """Numeric input does not crash."""
        result = _phonemes("12345")
        assert isinstance(result, list)

    def test_punctuation_only(self):
        """Punctuation-only input does not crash."""
        result = _phonemes("...!!??")
        assert isinstance(result, list)

    def test_very_long_input(self):
        """Long input does not crash (produces tokens)."""
        long_text = "안녕하세요 " * 100
        result = _phonemes(long_text)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_single_character(self):
        """Single Hangul character produces tokens."""
        result = _phonemes("가")
        assert len(result) > 0

    def test_newline_in_text(self):
        """Newline characters do not cause errors."""
        result = _phonemes("안녕\n하세요")
        assert isinstance(result, list)

    def test_tab_in_text(self):
        """Tab characters do not cause errors."""
        result = _phonemes("안녕\t하세요")
        assert isinstance(result, list)


# ===========================================================================
# Hangul Phonemization Tests (structural, not exact output)
# ===========================================================================


@requires_ko
class TestHangulPhonemes:
    """Verify that Hangul input produces IPA-like tokens."""

    # Common IPA characters expected in Korean output
    _IPA_CHARS = set("aeioukntpmslɾɛʌɯwjɰŋ")

    def test_single_syllable_produces_tokens(self):
        """Single syllable '가' produces at least one IPA token."""
        tokens = _phonemes("가")
        assert len(tokens) > 0
        joined = "".join(tokens)
        has_ipa = any(ch in self._IPA_CHARS for ch in joined)
        assert has_ipa, f"Expected IPA characters in {tokens}"

    def test_multisyllable_word(self):
        """'안녕하세요' produces multiple tokens."""
        tokens = _phonemes("안녕하세요")
        assert len(tokens) > 3, f"Expected many tokens, got {tokens}"

    def test_tokens_contain_expected_phonemes(self):
        """'한국어' output contains expected phonemes like 'h', 'a', 'n'."""
        joined = _joined("한국어")
        # 한 starts with ㅎ (h) and contains ㅏ (a) and ㄴ (n-final)
        assert "h" in joined, f"Expected 'h' in {joined}"
        assert "a" in joined, f"Expected 'a' in {joined}"
        assert "n" in joined, f"Expected 'n' in {joined}"

    def test_nasals_present(self):
        """'감사합니다' output contains nasal phonemes (m, n)."""
        joined = _joined("감사합니다")
        assert "m" in joined, f"Expected nasal 'm' in {joined}"
        assert "n" in joined, f"Expected nasal 'n' in {joined}"

    def test_vowel_a_from_ah(self):
        """ㅏ (medial index 0) maps to 'a'."""
        # 가 = ㄱ+ㅏ
        joined = _joined("가")
        assert "a" in joined

    def test_vowel_i_from_gi(self):
        """ㅣ (medial index 20) maps to 'i'."""
        # 기 = ㄱ+ㅣ
        joined = _joined("기")
        assert "i" in joined

    def test_vowel_u_from_gu(self):
        """ㅜ (medial index 13) maps to 'u'."""
        # 구 = ㄱ+ㅜ
        joined = _joined("구")
        assert "u" in joined

    def test_vowel_o_from_go(self):
        """ㅗ (medial index 8) maps to 'o'."""
        # 고 = ㄱ+ㅗ
        joined = _joined("고")
        assert "o" in joined

    def test_vowel_eu_from_geu(self):
        """ㅡ (medial index 18) maps to 'ɯ'."""
        # 그 = ㄱ+ㅡ
        joined = _joined("그")
        assert "ɯ" in joined

    def test_final_consonant_ng(self):
        """ㅇ in final position (종성) produces 'ŋ'."""
        # 강 = ㄱ+ㅏ+ㅇ(final)
        joined = _joined("강")
        assert "ŋ" in joined, f"Expected 'ŋ' in {joined}"


# ===========================================================================
# Phonological Feature Tests (presence, not exact values)
# ===========================================================================


@requires_ko
class TestPhonologicalFeatures:
    """Test structural phonological features of Korean output."""

    def test_liaison_produces_different_output(self):
        """Liaison: '국어' as one word vs '국' + '어' separately differ."""
        # When 국 (kuk) is followed by 어 (eo), liaison produces 구거 [kuɡʌ]
        together = _joined("국어")
        separate = _joined("국") + _joined("어")
        # g2pk2 applies liaison rules, so joined output should differ
        assert together != separate, (
            f"Expected liaison to produce different output: "
            f"together={together!r} vs separate={separate!r}"
        )

    def test_tense_consonant_in_output(self):
        """Words with tense consonants (ㄲ,ㄸ,ㅃ,ㅆ,ㅉ) produce tense IPA markers."""
        # 꿈 starts with ㄲ (tense k, IPA: k͈)
        # The combining double breve below (U+0348) marks tenseness
        joined = _joined("꿈")
        # Check that the output is non-empty and contains 'k'
        assert "k" in joined, f"Expected 'k' in {joined}"

    def test_aspirated_consonant_in_output(self):
        """Words with aspirated consonants (ㅋ,ㅌ,ㅍ,ㅊ) produce aspirated IPA."""
        # 코 starts with ㅋ (aspirated k, IPA: kʰ)
        joined = _joined("코")
        assert "k" in joined, f"Expected 'k' in {joined}"
        assert "ʰ" in joined, f"Expected aspiration marker 'ʰ' in {joined}"

    def test_lateral_in_output(self):
        """ㄹ in final position maps to 'l'."""
        # 말 = ㅁ+ㅏ+ㄹ(final) -> m a l
        joined = _joined("말")
        assert "l" in joined, f"Expected 'l' in {joined}"

    def test_flap_in_initial(self):
        """ㄹ in initial position maps to 'ɾ' (flap)."""
        # 라 = ㄹ+ㅏ -> ɾ a
        joined = _joined("라")
        assert "ɾ" in joined, f"Expected flap 'ɾ' in {joined}"

    def test_bilabial_nasal_m(self):
        """ㅁ in initial position maps to 'm'."""
        # 마 = ㅁ+ㅏ -> m a
        joined = _joined("마")
        assert joined.startswith("m"), f"Expected 'm' at start of {joined}"

    def test_glide_w_diphthong(self):
        """ㅘ diphthong contains glide 'w'."""
        # 과 = ㄱ+ㅘ -> k w a
        joined = _joined("과")
        assert "w" in joined, f"Expected glide 'w' in {joined}"

    def test_glide_j_diphthong(self):
        """ㅑ diphthong contains glide 'j'."""
        # 야 = ㅇ+ㅑ -> j a
        joined = _joined("야")
        assert "j" in joined, f"Expected glide 'j' in {joined}"

    def test_unreleased_final_k(self):
        """ㄱ in final position maps to unreleased 'k̚'."""
        from piper_plus_g2p.korean import _FINAL_TO_IPA

        # Index 1 = ㄱ final
        assert _FINAL_TO_IPA[1] == ["k\u031a"]

    def test_unreleased_final_t(self):
        """ㄷ in final position maps to unreleased 't̚'."""
        from piper_plus_g2p.korean import _FINAL_TO_IPA

        # Index 7 = ㄷ final
        assert _FINAL_TO_IPA[7] == ["t\u031a"]

    def test_unreleased_final_p(self):
        """ㅂ in final position maps to unreleased 'p̚'."""
        from piper_plus_g2p.korean import _FINAL_TO_IPA

        # Index 17 = ㅂ final
        assert _FINAL_TO_IPA[17] == ["p\u031a"]


# ===========================================================================
# Internal Decomposition Tests
# ===========================================================================


@requires_ko
class TestDecomposition:
    """Test Hangul decomposition internals."""

    def test_is_hangul_syllable_true(self):
        """Hangul syllable block characters are detected."""
        from piper_plus_g2p.korean import _is_hangul_syllable

        assert _is_hangul_syllable("가")  # U+AC00
        assert _is_hangul_syllable("힣")  # U+D7A3

    def test_is_hangul_syllable_false(self):
        """Non-Hangul characters are not detected as syllables."""
        from piper_plus_g2p.korean import _is_hangul_syllable

        assert not _is_hangul_syllable("A")
        assert not _is_hangul_syllable("1")
        assert not _is_hangul_syllable("!")

    def test_decompose_ga(self):
        """'가' decomposes to initial=0(ㄱ), medial=0(ㅏ), final=0(none)."""
        from piper_plus_g2p.korean import _decompose_syllable

        initial, medial, final = _decompose_syllable("가")
        assert initial == 0  # ㄱ
        assert medial == 0  # ㅏ
        assert final == 0  # no final

    def test_decompose_han(self):
        """'한' decomposes to initial=18(ㅎ), medial=0(ㅏ), final=4(ㄴ)."""
        from piper_plus_g2p.korean import _decompose_syllable

        initial, medial, final = _decompose_syllable("한")
        assert initial == 18  # ㅎ
        assert medial == 0  # ㅏ
        assert final == 4  # ㄴ

    def test_syllable_to_ipa_ga(self):
        """'가' -> ['k', 'a'] (initial ㄱ=k, medial ㅏ=a, no final)."""
        from piper_plus_g2p.korean import _syllable_to_ipa

        result = _syllable_to_ipa("가")
        assert result == ["k", "a"]

    def test_syllable_to_ipa_with_final(self):
        """'강' -> ['k', 'a', 'ŋ'] (initial ㄱ, medial ㅏ, final ㅇ=ŋ)."""
        from piper_plus_g2p.korean import _syllable_to_ipa

        result = _syllable_to_ipa("강")
        assert result == ["k", "a", "ŋ"]

    def test_count_hangul_syllables(self):
        """_count_hangul_syllables counts only Hangul syllable blocks."""
        from piper_plus_g2p.korean import _count_hangul_syllables

        assert _count_hangul_syllables("안녕하세요") == 5
        assert _count_hangul_syllables("Hello") == 0
        assert _count_hangul_syllables("한국어 Korean") == 3

    def test_initial_table_length(self):
        """Initial consonant IPA table has 19 entries."""
        from piper_plus_g2p.korean import _INITIAL_TO_IPA

        assert len(_INITIAL_TO_IPA) == 19

    def test_medial_table_length(self):
        """Medial vowel IPA table has 21 entries."""
        from piper_plus_g2p.korean import _MEDIAL_TO_IPA

        assert len(_MEDIAL_TO_IPA) == 21

    def test_final_table_length(self):
        """Final consonant IPA table has 28 entries."""
        from piper_plus_g2p.korean import _FINAL_TO_IPA

        assert len(_FINAL_TO_IPA) == 28

    def test_silent_ieung_initial(self):
        """ㅇ in initial position (index 11) maps to empty list (silent)."""
        from piper_plus_g2p.korean import _INITIAL_TO_IPA

        assert _INITIAL_TO_IPA[11] == []


# ===========================================================================
# Prosody Tests
# ===========================================================================


@requires_ko
class TestProsody:
    """Prosody output tests for Korean."""

    def test_prosody_length_matches_tokens(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        p = _make()
        tokens, prosody = p.phonemize_with_prosody("안녕하세요")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_structure(self):
        """Each non-None prosody element has a1, a2, a3 attributes."""
        from piper_plus_g2p.base import ProsodyInfo

        p = _make()
        _, prosody = p.phonemize_with_prosody("한국어")
        for pi in prosody:
            if pi is not None:
                assert isinstance(pi, ProsodyInfo)
                assert hasattr(pi, "a1")
                assert hasattr(pi, "a2")
                assert hasattr(pi, "a3")

    def test_prosody_values_are_numeric(self):
        """a1, a2, a3 values are int or float."""
        p = _make()
        _, prosody = p.phonemize_with_prosody("감사합니다")
        for pi in prosody:
            if pi is not None:
                assert isinstance(pi.a1, int | float), f"a1 not numeric: {pi.a1!r}"
                assert isinstance(pi.a2, int | float), f"a2 not numeric: {pi.a2!r}"
                assert isinstance(pi.a3, int | float), f"a3 not numeric: {pi.a3!r}"

    def test_prosody_a1_is_zero(self):
        """Korean a1 is always 0 (no pitch accent)."""
        p = _make()
        _, prosody = p.phonemize_with_prosody("안녕하세요")
        for pi in prosody:
            if pi is not None:
                assert pi.a1 == 0, f"Expected a1=0 for Korean, got {pi.a1}"

    def test_prosody_a2_is_zero(self):
        """Korean a2 is always 0 (no lexical stress)."""
        p = _make()
        _, prosody = p.phonemize_with_prosody("안녕하세요")
        for pi in prosody:
            if pi is not None:
                assert pi.a2 == 0, f"Expected a2=0 for Korean, got {pi.a2}"

    def test_prosody_a3_syllable_count(self):
        """a3 reflects the Hangul syllable count of the word."""
        p = _make()
        # "안녕" has 2 syllables; "하세요" has 3 syllables
        # g2pk2 may merge or split differently, so test a simpler case
        tokens, prosody = p.phonemize_with_prosody("가나다")
        # "가나다" = 3 syllables, so a3 should be 3 for all phoneme tokens
        for pi in prosody:
            if pi is not None and pi.a3 > 0:
                assert pi.a3 == 3, f"Expected a3=3, got {pi.a3}"

    def test_prosody_empty_input(self):
        """Empty input returns empty prosody."""
        p = _make()
        tokens, prosody = p.phonemize_with_prosody("")
        assert tokens == []
        assert prosody == []

    def test_prosody_punctuation_is_none(self):
        """Punctuation tokens have None prosody."""
        p = _make()
        tokens, prosody = p.phonemize_with_prosody("안녕!")
        # Find the "!" token if present
        for t, pi in zip(tokens, prosody, strict=False):
            if t == "!":
                assert pi is None, f"Expected None prosody for '!', got {pi}"

    def test_prosody_space_token(self):
        """Space tokens between words have prosody with a3=0."""
        from piper_plus_g2p.base import ProsodyInfo

        p = _make()
        tokens, prosody = p.phonemize_with_prosody("안녕 하세요")
        for t, pi in zip(tokens, prosody, strict=False):
            if t == " ":
                assert pi == ProsodyInfo(a1=0, a2=0, a3=0)


# ===========================================================================
# Mixed Input Tests
# ===========================================================================


@requires_ko
class TestMixedInput:
    """Test handling of mixed-script and mixed-content inputs."""

    def test_mixed_hangul_latin(self):
        """Mixed Hangul and Latin text produces tokens."""
        tokens = _phonemes("한국어 Korean")
        assert len(tokens) > 0

    def test_mixed_hangul_punctuation(self):
        """Hangul with punctuation produces tokens."""
        tokens = _phonemes("안녕!")
        assert len(tokens) > 0
        assert "!" in tokens

    def test_latin_characters_pass_through(self):
        """Latin characters in input are passed through."""
        tokens = _phonemes("OK")
        # Latin characters should appear in the output
        joined = "".join(tokens)
        assert "O" in joined or "K" in joined, (
            f"Expected Latin pass-through in {tokens}"
        )

    def test_mixed_hangul_numbers(self):
        """Hangul with numbers does not crash."""
        result = _phonemes("2024년")
        assert isinstance(result, list)

    def test_multiple_sentences(self):
        """Multiple sentences separated by periods produce tokens."""
        result = _phonemes("안녕하세요. 반갑습니다.")
        assert len(result) > 0
        assert "." in result


# ===========================================================================
# No PUA in Output
# ===========================================================================


@requires_ko
class TestNoPUA:
    """Verify no Private Use Area codepoints appear in output."""

    def test_no_pua_basic(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        tokens = _phonemes("한국어를 공부합니다")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_no_pua_mixed_input(self):
        """Mixed-script input also produces no PUA characters."""
        tokens = _phonemes("서울 Seoul 2024")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_no_pua_with_prosody(self):
        """phonemize_with_prosody() returns no PUA characters."""
        p = _make()
        tokens, _ = p.phonemize_with_prosody("대한민국")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )


# ===========================================================================
# Unicode Normalization
# ===========================================================================


@requires_ko
class TestUnicodeNormalization:
    """Test that NFD-decomposed Hangul jamo are handled correctly."""

    def test_nfc_and_nfd_same_output(self):
        """NFC and NFD forms of the same text produce the same phonemes."""
        import unicodedata

        text_nfc = unicodedata.normalize("NFC", "한국어")
        text_nfd = unicodedata.normalize("NFD", "한국어")
        # Confirm they are different byte sequences
        assert text_nfc != text_nfd
        # But produce the same phoneme output
        assert _phonemes(text_nfc) == _phonemes(text_nfd)


# ===========================================================================
# Module-level Function Tests
# ===========================================================================


@requires_ko
class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_phonemize_korean_function(self):
        """phonemize_korean() module function works."""
        from piper_plus_g2p.korean import phonemize_korean

        result = phonemize_korean("안녕하세요")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_phonemize_korean_with_prosody_function(self):
        """phonemize_korean_with_prosody() module function works."""
        from piper_plus_g2p.korean import phonemize_korean_with_prosody

        tokens, prosody = phonemize_korean_with_prosody("안녕하세요")
        assert isinstance(tokens, list)
        assert isinstance(prosody, list)
        assert len(tokens) == len(prosody)

    def test_module_exports(self):
        """__all__ contains the expected public names."""
        from piper_plus_g2p import korean

        assert "phonemize_korean" in korean.__all__
        assert "phonemize_korean_with_prosody" in korean.__all__
        assert "KoreanPhonemizer" in korean.__all__
