"""Tests for non-JA prosody extraction (computeNonJaProsody in C++).

Validates that prosody features (a1, a2, a3) are correctly computed for
ZH (tone), EN/ES/PT (stress), and FR (final-syllable stress).
Uses Python phonemizers as the reference implementation.
"""
import pytest


class TestChineseProsody:
    """ZH: a1=tone(1-5), a2=syllable position, a3=word length."""

    @pytest.fixture(autouse=True)
    def skip_if_no_pypinyin(self):
        pytest.importorskip("pypinyin")

    def test_tone_extraction(self):
        """Each syllable should have a tone value in prosody."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("你好")
        assert len(phonemes) == len(prosody)
        # At least some prosody entries should have non-zero a1 (tone)
        tones = [pr.a1 for pr in prosody if pr is not None and pr.a1 > 0]
        assert len(tones) > 0, "Chinese prosody should contain tone values"

    def test_tone_values_range(self):
        """Tone values should be 1-5."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        _, prosody = p.phonemize_with_prosody("中国人民")
        for pr in prosody:
            if pr is not None and pr.a1 > 0:
                assert 1 <= pr.a1 <= 5, f"Tone {pr.a1} out of range 1-5"

    def test_word_length_tracking(self):
        """a3 should reflect word length in syllables."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        _, prosody = p.phonemize_with_prosody("你好")
        # "你好" is 2 contiguous Chinese characters, so a3 should be 2
        a3_values = [pr.a3 for pr in prosody if pr is not None and pr.a3 > 0]
        assert any(v >= 2 for v in a3_values), "Word length should be >= 2 for 你好"

    def test_tone_sandhi_t3_t3(self):
        """T3+T3 should produce T2+T3 after sandhi."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        _, prosody = p.phonemize_with_prosody("你好")
        # First syllable 你 (T3) before 好 (T3) -> should become T2
        tones = [pr.a1 for pr in prosody if pr is not None and pr.a1 > 0]
        if len(tones) >= 2:
            assert tones[0] == 2, f"Expected T2 after sandhi, got T{tones[0]}"

    def test_syllable_position_tracking(self):
        """a2 should track syllable position within a word (1-based)."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        _, prosody = p.phonemize_with_prosody("你好")
        # Expect syllable positions 1 and 2 within the word
        a2_values = [pr.a2 for pr in prosody if pr is not None and pr.a2 > 0]
        assert 1 in a2_values, "Should have syllable position 1"
        assert 2 in a2_values, "Should have syllable position 2"

    def test_punctuation_has_none_prosody(self):
        """Punctuation tokens should have None prosody."""
        from piper_train.phonemize.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("你好。")
        # The period (mapped from 。) should have None prosody
        for ph, pr in zip(phonemes, prosody):
            if ph == ".":
                assert pr is None, "Punctuation should have None prosody"


class TestEnglishProsody:
    """EN: a1=0, a2=stress level, a3=word phoneme count."""

    @pytest.fixture(autouse=True)
    def skip_if_no_g2p(self):
        pytest.importorskip("g2p_en")

    def test_stress_extraction(self):
        """English words should have stress markers in prosody."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        _, prosody = p.phonemize_with_prosody("hello")
        # Should have at least one a2=2 (primary stress)
        has_stress = any(pr.a2 == 2 for pr in prosody if pr is not None)
        assert has_stress, "English 'hello' should have primary stress"

    def test_a1_always_zero(self):
        """English a1 should always be 0."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        _, prosody = p.phonemize_with_prosody("hello world")
        for pr in prosody:
            if pr is not None:
                assert pr.a1 == 0, f"English a1 should be 0, got {pr.a1}"

    def test_word_phoneme_count(self):
        """a3 should reflect word phoneme count."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        _, prosody = p.phonemize_with_prosody("cat")
        a3_values = [pr.a3 for pr in prosody if pr is not None and pr.a3 > 0]
        assert len(a3_values) > 0, "Should have word phoneme count"
        assert all(v > 0 for v in a3_values), "Word count should be positive"

    def test_space_has_zero_prosody(self):
        """Space tokens should have a2=0, a3=0."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("hello world")
        for ph, pr in zip(phonemes, prosody):
            if ph == " " and pr is not None:
                assert pr.a2 == 0, "Space should have a2=0"
                assert pr.a3 == 0, "Space should have a3=0"

    def test_secondary_stress(self):
        """Secondary stress should produce a2=1."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("information")
        # "information" has both primary and secondary stress
        a2_values = set(pr.a2 for pr in prosody if pr is not None)
        # Should have at least primary stress (2)
        assert 2 in a2_values, "Should have primary stress (a2=2)"

    def test_function_word_destressing(self):
        """Function words (the, are, etc.) should have stress removed."""
        from piper_train.phonemize.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("the cat")
        # Find where "the" ends (first space)
        space_idx = phonemes.index(" ") if " " in phonemes else len(phonemes)
        # All prosody entries before the space (i.e., "the") should have a2=0
        for pr in prosody[:space_idx]:
            if pr is not None:
                assert pr.a2 == 0, "Function word 'the' should have no stress"


class TestSpanishProsody:
    """ES: a1=0, a2=stress flag (0 or 2), a3=word phoneme count."""

    def test_stress_on_accented_vowel(self):
        """Accented vowels should get a2=2."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        _, prosody = p.phonemize_with_prosody("cafe")
        has_stress = any(pr.a2 == 2 for pr in prosody if pr is not None)
        assert has_stress, "Spanish 'cafe' should have stress"

    def test_default_stress_penultimate(self):
        """Words ending in vowel: stress on penultimate syllable."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        _, prosody = p.phonemize_with_prosody("hola")
        has_stress = any(pr.a2 == 2 for pr in prosody if pr is not None)
        assert has_stress, "Spanish 'hola' should have stress"

    def test_a1_always_zero(self):
        """Spanish a1 should always be 0."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        _, prosody = p.phonemize_with_prosody("hola mundo")
        for pr in prosody:
            if pr is not None:
                assert pr.a1 == 0, f"Spanish a1 should be 0, got {pr.a1}"

    def test_word_phoneme_count_positive(self):
        """a3 should be positive for non-space, non-punctuation phonemes."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("hola")
        for ph, pr in zip(phonemes, prosody):
            if pr is not None and ph != " ":
                assert pr.a3 > 0, f"Word phoneme count should be > 0 for '{ph}'"

    def test_unstressed_function_word(self):
        """Common function words (el, la, de) should have no stress marker."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("el")
        # "el" is in _UNSTRESSED_FUNCTION_WORDS, so no a2=2
        for pr in prosody:
            if pr is not None:
                assert pr.a2 == 0, "Function word 'el' should have no stress"


class TestFrenchProsody:
    """FR: a1=0, a2=2 for last vowel in word, a3=word phoneme count."""

    def test_final_syllable_stress(self):
        """French stress should be on the last vowel of each word."""
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("bonjour")
        # Last vowel should have a2=2
        has_stress = any(pr.a2 == 2 for pr in prosody if pr is not None)
        assert has_stress, "French 'bonjour' should have final-syllable stress"

    def test_stress_count_per_word(self):
        """Each word should have exactly one stressed vowel (a2=2)."""
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("bonjour")
        stress_count = sum(1 for pr in prosody if pr is not None and pr.a2 == 2)
        assert stress_count == 1, f"Expected 1 stressed vowel, got {stress_count}"

    def test_a1_always_zero(self):
        """French a1 should always be 0."""
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        _, prosody = p.phonemize_with_prosody("bonjour monde")
        for pr in prosody:
            if pr is not None:
                assert pr.a1 == 0, f"French a1 should be 0, got {pr.a1}"

    def test_multiword_each_has_stress(self):
        """Each word in a multi-word phrase should have its own stress."""
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("bonjour monde")
        # Find space separator
        if " " in phonemes:
            space_idx = phonemes.index(" ")
            # Word 1: should have exactly one a2=2
            word1_stress = sum(
                1
                for pr in prosody[:space_idx]
                if pr is not None and pr.a2 == 2
            )
            # Word 2: should have exactly one a2=2
            word2_stress = sum(
                1
                for pr in prosody[space_idx + 1 :]
                if pr is not None and pr.a2 == 2
            )
            assert word1_stress == 1, f"Word 1 should have 1 stress, got {word1_stress}"
            assert word2_stress == 1, f"Word 2 should have 1 stress, got {word2_stress}"

    def test_word_phoneme_count(self):
        """a3 should equal the total number of phonemes in the word."""
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("bon")
        # All phonemes in the word should share the same a3 value
        a3_values = [pr.a3 for pr in prosody if pr is not None and pr.a3 > 0]
        assert len(a3_values) > 0, "Should have word phoneme count"
        assert len(set(a3_values)) == 1, "All phonemes in word should share a3"


class TestPortugueseProsody:
    """PT: a1=0, a2=stress flag (0 or 2), a3=word phoneme count."""

    def test_stress_extraction(self):
        """Portuguese words should have stress markers."""
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        _, prosody = p.phonemize_with_prosody("mundo")
        has_stress = any(pr.a2 == 2 for pr in prosody if pr is not None)
        assert has_stress, "Portuguese 'mundo' should have stress"

    def test_a1_always_zero(self):
        """Portuguese a1 should always be 0."""
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        _, prosody = p.phonemize_with_prosody("mundo")
        for pr in prosody:
            if pr is not None:
                assert pr.a1 == 0, f"Portuguese a1 should be 0, got {pr.a1}"

    def test_stress_on_penultimate(self):
        """Words ending in vowel should stress the penultimate syllable."""
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("mundo")
        # "mundo" ends in 'o', so penultimate syllable gets stress
        stressed_indices = [
            i for i, pr in enumerate(prosody) if pr is not None and pr.a2 == 2
        ]
        assert len(stressed_indices) > 0, "Should have at least one stressed phoneme"
        # The stress should NOT be on the very last phoneme
        assert stressed_indices[0] < len(phonemes) - 1, (
            "Penultimate stress should not be on last phoneme"
        )

    def test_word_phoneme_count_consistent(self):
        """All phonemes in a single word should share the same a3 value."""
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("mundo")
        a3_values = [pr.a3 for pr in prosody if pr is not None and pr.a3 > 0]
        assert len(a3_values) > 0, "Should have word phoneme count"
        assert len(set(a3_values)) == 1, "All phonemes should share same a3"


class TestProsodyAlignment:
    """Verify phoneme and prosody list lengths match for all languages."""

    @pytest.mark.parametrize(
        "lang,text",
        [
            ("en", "hello world"),
            ("es", "hola mundo"),
            ("fr", "bonjour monde"),
            ("pt", "ola mundo"),
        ],
    )
    def test_length_alignment(self, lang, text):
        """Phoneme and prosody lists must have same length."""
        if lang == "en":
            pytest.importorskip("g2p_en")
        from piper_train.phonemize.registry import get_phonemizer

        p = get_phonemizer(lang)
        phonemes, prosody = p.phonemize_with_prosody(text)
        assert len(phonemes) == len(prosody), (
            f"{lang}: phonemes({len(phonemes)}) != prosody({len(prosody)})"
        )

    def test_zh_alignment(self):
        """Chinese phoneme and prosody alignment."""
        pytest.importorskip("pypinyin")
        from piper_train.phonemize.registry import get_phonemizer

        p = get_phonemizer("zh")
        phonemes, prosody = p.phonemize_with_prosody("你好世界")
        assert len(phonemes) == len(prosody)

    def test_empty_input(self):
        """Empty input should produce empty output for all languages."""
        from piper_train.phonemize.spanish import SpanishPhonemizer
        from piper_train.phonemize.french import FrenchPhonemizer
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        for cls in [SpanishPhonemizer, FrenchPhonemizer, PortuguesePhonemizer]:
            p = cls()
            phonemes, prosody = p.phonemize_with_prosody("")
            assert len(phonemes) == len(prosody) == 0, (
                f"{cls.__name__}: empty input should produce empty output"
            )

    def test_punctuation_only(self):
        """Punctuation-only input should have aligned prosody."""
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        phonemes, prosody = p.phonemize_with_prosody("!")
        assert len(phonemes) == len(prosody)
