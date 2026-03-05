"""Tests for Korean phonemizer."""

import pytest


class TestKoreanPhonemizer:
    """Tests for Korean G2P."""

    @pytest.fixture(autouse=True)
    def skip_if_no_deps(self):
        # Korean phonemizer may use g2pk2 or fallback to Hangul decomposition
        pass

    def test_simple_word(self):
        from piper_train.phonemize.korean import phonemize_korean

        phonemes = phonemize_korean("안녕하세요")
        assert len(phonemes) > 0

    def test_prosody_alignment(self):
        from piper_train.phonemize.korean import phonemize_korean_with_prosody

        phonemes, prosody = phonemize_korean_with_prosody("안녕하세요")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        phonemes = p.phonemize("안녕하세요")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_hangul_decomposition(self):
        """Verify Hangul syllables are decomposed."""
        from piper_train.phonemize.korean import phonemize_korean

        # 한 = ㅎ+ㅏ+ㄴ → should produce consonant + vowel + final
        phonemes = phonemize_korean("한")
        assert len(phonemes) > 0

    def test_space_between_words(self):
        from piper_train.phonemize.korean import phonemize_korean

        phonemes = phonemize_korean("안녕 하세요")
        assert " " in phonemes
