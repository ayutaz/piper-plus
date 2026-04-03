"""Tests for English G2P module (g2p-en based)."""

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody
from piper_plus_g2p.base import ProsodyInfo
from piper_plus_g2p.english import (
    ARPABET_TO_IPA,
    _arpabet_to_ipa,
    _convert_word_to_ipa,
    phonemize_english,
    phonemize_english_with_prosody,
)

# EnglishProsodyInfo was always an alias for ProsodyInfo
EnglishProsodyInfo = ProsodyInfo


class TestArpabetToIpa:
    """Tests for ARPAbet to IPA conversion."""

    def test_consonant_no_stress(self):
        ipa, stress = _arpabet_to_ipa("B")
        assert ipa == "b"
        assert stress == -1

    def test_vowel_with_primary_stress(self):
        ipa, stress = _arpabet_to_ipa("OW1")
        assert ipa == "oʊ"
        assert stress == 1

    def test_vowel_with_secondary_stress(self):
        ipa, stress = _arpabet_to_ipa("AO2")
        assert ipa == "ɔː"
        assert stress == 2

    def test_vowel_unstressed(self):
        ipa, stress = _arpabet_to_ipa("IH0")
        assert ipa == "ɪ"
        assert stress == 0

    def test_ah_unstressed_is_schwa(self):
        ipa, stress = _arpabet_to_ipa("AH0")
        assert ipa == "ə"
        assert stress == 0

    def test_ah_stressed_is_not_schwa(self):
        ipa, stress = _arpabet_to_ipa("AH1")
        assert ipa == "ʌ"
        assert stress == 1

    def test_punctuation_passthrough(self):
        ipa, stress = _arpabet_to_ipa(",")
        assert ipa == ","
        assert stress == -1

    def test_all_arpabet_symbols_mapped(self):
        """Every ARPAbet symbol should produce a non-empty IPA string."""
        for arpa, expected_ipa in ARPABET_TO_IPA.items():
            ipa, stress = _arpabet_to_ipa(arpa)
            assert ipa == expected_ipa
            assert stress == -1  # No stress digit → -1


class TestConvertWordToIpa:
    """Tests for context-dependent ARPAbet → IPA conversion."""

    def test_aa_r_merges_to_long_vowel(self):
        """AA + R → ɑːɹ (single token)."""
        result = _convert_word_to_ipa(["K", "AA1", "R"])
        ipas = [ipa for ipa, _ in result]
        assert "ɑːɹ" in ipas

    def test_stressed_er_becomes_long(self):
        """ER1 → ɜː (stressed r-colored vowel)."""
        result = _convert_word_to_ipa(["B", "ER1", "D"])
        ipas = [ipa for ipa, _ in result]
        assert "ɜː" in ipas

    def test_unstressed_er_becomes_schwa_r(self):
        """ER0 → ɚ (unstressed r-colored vowel)."""
        result = _convert_word_to_ipa(["L", "EH1", "T", "ER0"])
        ipas = [ipa for ipa, _ in result]
        assert "ɚ" in ipas


class TestStressToProsody:
    """Tests for stress marker to prosody A2 mapping."""

    def test_primary_stress_maps_to_a2_2(self):
        _, prosody_list = phonemize_english_with_prosody("go")
        a2_values = [p.a2 for p in prosody_list]
        assert 2 in a2_values

    def test_unstressed_maps_to_a2_0(self):
        _, prosody_list = phonemize_english_with_prosody("the")
        a2_values = [p.a2 for p in prosody_list]
        assert 0 in a2_values

    def test_a1_always_zero(self):
        _, prosody_list = phonemize_english_with_prosody("Hello world")
        for p in prosody_list:
            assert p.a1 == 0


class TestStressMarkers:
    """Tests for stress marker insertion (espeak-ng compatibility)."""

    def test_stress_markers_inserted(self):
        """Primary stress marker ˈ should appear before stressed vowels."""
        phonemes, _ = phonemize_english_with_prosody("hello")
        # "hello" → HH AH0 L OW1 → h ə l ˈ o ʊ
        assert "ˈ" in phonemes
        idx = phonemes.index("ˈ")
        assert phonemes[idx + 1] == "o"

    def test_secondary_stress_marker(self):
        """Secondary stress marker ˌ should appear for stress=2 vowels."""
        phonemes, _ = phonemize_english_with_prosody("information")
        assert "ˌ" in phonemes

    def test_no_stress_marker_for_unstressed(self):
        """Unstressed vowels should not have stress markers."""
        phonemes, _ = phonemize_english_with_prosody("hello")
        idx = phonemes.index("ə")
        if idx > 0:
            assert phonemes[idx - 1] not in ("ˈ", "ˌ")


class TestFunctionWordStress:
    """Tests for function word stress removal."""

    def test_function_word_no_stress(self):
        """Function words (are, you) should have no stress markers."""
        phonemes, _ = phonemize_english_with_prosody("how are you today")
        # Find "are" region (ɑːɹ) - should have no stress marker
        phoneme_str = " ".join(phonemes)
        # "are" as function word should not have ˈ before ɑ
        assert "ˈ ɑ" not in phoneme_str

    def test_content_word_keeps_stress(self):
        """Content words should keep their stress."""
        phonemes, _ = phonemize_english_with_prosody("the cat")
        # "cat" → k ˈ æ t
        assert "ˈ" in phonemes

    def test_today_keeps_stress(self):
        """'today' is a content word and should keep stress on second syllable."""
        phonemes, _ = phonemize_english_with_prosody("today")
        assert "ˈ" in phonemes
        idx = phonemes.index("ˈ")
        assert phonemes[idx + 1] == "e"  # ˈeɪ


class TestWordBoundarySpaces:
    """Tests for word boundary space insertion."""

    def test_word_boundary_spaces(self):
        phonemes, _ = phonemize_english_with_prosody("hello world")
        assert " " in phonemes

    def test_no_leading_space(self):
        phonemes, _ = phonemize_english_with_prosody("hello world")
        assert phonemes[0] != " "

    def test_no_trailing_space(self):
        phonemes, _ = phonemize_english_with_prosody("hello world")
        assert phonemes[-1] != " "

    def test_single_word_no_space(self):
        phonemes, _ = phonemize_english_with_prosody("hello")
        assert " " not in phonemes


class TestPunctuationHandling:
    """Tests for punctuation placement (espeak-ng compatibility)."""

    def test_comma_attached_to_previous_word(self):
        """Comma should follow previous word without space before it."""
        phonemes, _ = phonemize_english_with_prosody("Hello, world")
        # There should be no space before comma
        comma_idx = phonemes.index(",")
        assert phonemes[comma_idx - 1] != " "

    def test_space_after_comma(self):
        """Space should appear after comma (before next word)."""
        phonemes, _ = phonemize_english_with_prosody("Hello, world")
        comma_idx = phonemes.index(",")
        assert phonemes[comma_idx + 1] == " "

    def test_question_mark_no_space_before(self):
        """Question mark should attach to previous word."""
        phonemes, _ = phonemize_english_with_prosody("Hello?")
        assert phonemes[-1] == "?"
        assert phonemes[-2] != " "


class TestEspeakCompatibility:
    """Tests for espeak-ng output compatibility on exact-match cases."""

    def test_the_cat(self):
        """'the cat' should exactly match espeak-ng output."""
        phonemes, _ = phonemize_english_with_prosody("the cat")
        assert phonemes == ["ð", "ə", " ", "k", "ˈ", "æ", "t"]

    def test_car(self):
        """'car' should exactly match espeak-ng: k ˈ ɑ ː ɹ"""
        phonemes, _ = phonemize_english_with_prosody("car")
        assert " ".join(phonemes) == "k ˈ ɑ ː ɹ"

    def test_information(self):
        """'information' should exactly match espeak-ng."""
        phonemes, _ = phonemize_english_with_prosody("information")
        assert " ".join(phonemes) == "ˌ ɪ n f ɚ m ˈ e ɪ ʃ ə n"

    def test_bird(self):
        """'bird' should exactly match espeak-ng: b ˈ ɜ ː d"""
        phonemes, _ = phonemize_english_with_prosody("bird")
        assert " ".join(phonemes) == "b ˈ ɜ ː d"

    def test_hello(self):
        """'hello' should match: h ə l ˈ o ʊ"""
        phonemes, _ = phonemize_english_with_prosody("hello")
        assert " ".join(phonemes) == "h ə l ˈ o ʊ"

    def test_phonemes_are_single_chars(self):
        """Each phoneme should be a single character (mappable to phoneme_id_map)."""
        phonemes = phonemize_english("Hello, how are you today?")
        for p in phonemes:
            assert len(p) == 1, f"Multi-char phoneme found: {p!r}"


class TestBosEos:
    """Tests for BOS/EOS markers in phoneme ID conversion."""

    def test_bos_eos_added(self):
        """Phoneme IDs should have BOS (^) and EOS ($) markers."""
        phoneme_id_map = {
            "_": [0],
            "^": [1],
            "$": [2],
            " ": [3],
            "h": [10],
            "ˈ": [120],
            "ˌ": [121],
            "ɪ": [30],
            "ə": [31],
            "l": [32],
            "o": [33],
            "ʊ": [34],
        }
        ids, prosody = text_to_phoneme_ids_and_prosody(
            "hello", phoneme_id_map, language="en"
        )
        assert ids[0] == 1, "First ID should be BOS (^)"
        assert ids[-1] == 2, "Last ID should be EOS ($)"
        assert prosody[0] is None
        assert prosody[-1] is None

    def test_inter_phoneme_padding(self):
        """Pad token (0) should be inserted between every phoneme ID."""
        phoneme_id_map = {
            "_": [0],
            "^": [1],
            "$": [2],
            "h": [10],
            "ˈ": [120],
            "ə": [31],
            "l": [32],
            "o": [33],
            "ʊ": [34],
        }
        ids, _ = text_to_phoneme_ids_and_prosody("hello", phoneme_id_map, language="en")
        # Pattern: BOS, 0, phoneme, 0, phoneme, 0, ..., phoneme, 0, EOS
        assert ids[0] == 1  # BOS
        assert ids[1] == 0  # pad after BOS
        assert ids[-1] == 2  # EOS
        # Every odd-indexed element (1, 3, 5, ...) before EOS should be pad=0
        for i in range(1, len(ids) - 1, 2):
            assert ids[i] == 0, f"Expected pad at index {i}, got {ids[i]}"


class TestPhonemizeEnglish:
    """Tests for full English phonemization pipeline."""

    def test_basic_word(self):
        phonemes = phonemize_english("hello")
        assert len(phonemes) > 0
        assert all(isinstance(p, str) for p in phonemes)

    def test_multiple_words(self):
        phonemes = phonemize_english("Hello world")
        assert len(phonemes) > 0

    def test_with_prosody_lengths_match(self):
        phonemes, prosody = phonemize_english_with_prosody("How are you?")
        assert len(phonemes) == len(prosody)

    def test_prosody_info_type(self):
        _, prosody = phonemize_english_with_prosody("test")
        for p in prosody:
            assert isinstance(p, EnglishProsodyInfo)

    def test_a3_is_word_phoneme_count(self):
        phonemes, prosody = phonemize_english_with_prosody("cat")
        a3_values = {p.a3 for p in prosody}
        assert len(a3_values) == 1

    def test_empty_string(self):
        phonemes, prosody = phonemize_english_with_prosody("")
        assert phonemes == []
        assert prosody == []

    def test_numbers(self):
        phonemes = phonemize_english("123")
        assert len(phonemes) > 0
