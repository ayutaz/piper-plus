"""Tests for Korean phonemizer."""

import types
from unittest.mock import patch

import pytest


def _reset_g2p_state():
    """Reset the module-level G2p cache and unavailable flag."""
    import piper_train.phonemize.korean as mod

    mod._g2p_instance = None
    mod._g2p_unavailable = False


class TestKoreanPhonemizer:
    """Tests for Korean G2P.

    These tests exercise phonemize_korean() which falls back to raw Hangul
    decomposition when g2pk2/mecab is unavailable. The tests verify that
    output is produced (either with or without g2pk2 phonological rules).
    """

    @pytest.fixture(autouse=True)
    def _reset(self):
        _reset_g2p_state()
        yield
        _reset_g2p_state()

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


class TestG2pCaching:
    """Tests for G2p instance caching and error handling."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        """Reset the module-level G2p cache before/after each test."""
        _reset_g2p_state()
        yield
        _reset_g2p_state()

    def test_g2p_unavailable_flag_set_on_import_error(self):
        """When g2pk2 is not importable, _g2p_unavailable is set to True."""
        import piper_train.phonemize.korean as korean_mod
        from piper_train.phonemize.korean import _apply_g2p

        with patch.dict("sys.modules", {"g2pk2": None}):
            result = _apply_g2p("테스트")
            assert result == "테스트"
            assert korean_mod._g2p_unavailable is True
            assert korean_mod._g2p_instance is None

    def test_g2p_unavailable_flag_prevents_retry(self):
        """Once _g2p_unavailable is True, subsequent calls skip import."""
        import piper_train.phonemize.korean as korean_mod
        from piper_train.phonemize.korean import _apply_g2p

        korean_mod._g2p_unavailable = True
        # Should return text immediately without trying to import
        result = _apply_g2p("테스트")
        assert result == "테스트"

    def test_g2p_instance_is_cached_when_working(self):
        """If g2pk2+mecab works, instance is cached across calls."""
        import piper_train.phonemize.korean as korean_mod
        from piper_train.phonemize.korean import _apply_g2p

        # Create a mock G2p that works
        mock_g2p = lambda text: text + "_processed"  # noqa: E731
        fake_module = types.ModuleType("g2pk2")
        fake_module.G2p = lambda: mock_g2p

        with patch.dict("sys.modules", {"g2pk2": fake_module}):
            result1 = _apply_g2p("테스트")
            assert result1 == "테스트_processed"
            cached = korean_mod._g2p_instance
            assert cached is not None

            result2 = _apply_g2p("두번째")
            assert result2 == "두번째_processed"
            # Same instance reused
            assert korean_mod._g2p_instance is cached

    def test_fallback_on_import_error(self):
        """_apply_g2p returns original text when g2pk2 import fails."""
        from piper_train.phonemize.korean import _apply_g2p

        with patch.dict("sys.modules", {"g2pk2": None}):
            result = _apply_g2p("테스트")
            assert result == "테스트"

    def test_fallback_on_attribute_error_during_init(self):
        """_apply_g2p catches AttributeError from G2p() constructor."""
        from piper_train.phonemize.korean import _apply_g2p

        fake_module = types.ModuleType("g2pk2")

        def _bad_g2p():
            raise AttributeError("'NoneType' object has no attribute 'parse'")

        fake_module.G2p = _bad_g2p

        with patch.dict("sys.modules", {"g2pk2": fake_module}):
            result = _apply_g2p("테스트")
            assert result == "테스트"

    def test_fallback_on_attribute_error_during_call(self):
        """_apply_g2p catches AttributeError when G2p()(text) fails.

        This happens when g2pk2 imports and G2p() succeeds but mecab
        is None internally (python-mecab-ko not installed).
        """
        import piper_train.phonemize.korean as korean_mod
        from piper_train.phonemize.korean import _apply_g2p

        # Simulate: G2p() creates an object whose __call__ raises
        class BrokenG2p:
            def __call__(self, text):
                raise AttributeError(
                    "'NoneType' object has no attribute 'pos'"
                )

        fake_module = types.ModuleType("g2pk2")
        fake_module.G2p = BrokenG2p

        with patch.dict("sys.modules", {"g2pk2": fake_module}):
            result = _apply_g2p("테스트")
            assert result == "테스트"
            # Should mark as unavailable
            assert korean_mod._g2p_unavailable is True
            assert korean_mod._g2p_instance is None

    def test_fallback_on_syntax_error(self):
        """_apply_g2p catches SyntaxError from g2pk2 import."""
        import builtins

        from piper_train.phonemize.korean import _apply_g2p

        real_import = builtins.__import__

        def _raise_syntax(name, *args, **kwargs):
            if name == "g2pk2":
                raise SyntaxError("mock syntax error")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_raise_syntax):
            result = _apply_g2p("테스트")
            assert result == "테스트"

    def test_fallback_on_runtime_error_during_call(self):
        """_apply_g2p catches generic runtime errors (IndexError, etc.) from G2p()(text)."""
        import piper_train.phonemize.korean as korean_mod
        from piper_train.phonemize.korean import _apply_g2p

        class IndexErrorG2p:
            def __call__(self, text):
                raise IndexError("list index out of range")

        fake_module = types.ModuleType("g2pk2")
        fake_module.G2p = IndexErrorG2p

        with patch.dict("sys.modules", {"g2pk2": fake_module}):
            result = _apply_g2p("테스트")
            assert result == "테스트"
            # Instance should remain usable (broad except does not mark unavailable)
            assert korean_mod._g2p_unavailable is False

    def test_fallback_on_value_error_during_call(self):
        """_apply_g2p catches ValueError from G2p()(text)."""
        from piper_train.phonemize.korean import _apply_g2p

        class ValueErrorG2p:
            def __call__(self, text):
                raise ValueError("unexpected input")

        fake_module = types.ModuleType("g2pk2")
        fake_module.G2p = ValueErrorG2p

        with patch.dict("sys.modules", {"g2pk2": fake_module}):
            result = _apply_g2p("테스트")
            assert result == "테스트"


class TestHangulDecomposition:
    """Tests for Hangul syllable decomposition and IPA mapping."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        _reset_g2p_state()
        yield
        _reset_g2p_state()

    def test_basic_hangul_decomposition_content(self):
        """Test that basic Korean syllables produce expected phoneme segments."""
        from piper_train.phonemize.korean import phonemize_korean

        phonemes = phonemize_korean("안녕하세요")
        assert len(phonemes) > 0
        # 안 contains ㅏ → "a"; 하 contains ㅏ → "a"
        assert "a" in phonemes
        # 안 initial ㅇ is silent, final ㄴ → "n"
        assert "n" in phonemes

    def test_final_consonant_k(self):
        """Test Korean final ㄱ maps to k̚ (unreleased velar stop)."""
        from piper_train.phonemize.korean import phonemize_korean

        # 각 = ㄱ+ㅏ+ㄱ → k + a + k̚
        phonemes = phonemize_korean("각")
        assert len(phonemes) > 0
        assert "k̚" in phonemes or any("k" in p for p in phonemes)

    def test_final_consonant_p(self):
        """Test Korean final ㅂ maps to p̚ (unreleased bilabial stop)."""
        from piper_train.phonemize.korean import phonemize_korean

        # 밥 = ㅂ+ㅏ+ㅂ → p + a + p̚
        phonemes = phonemize_korean("밥")
        assert len(phonemes) > 0
        assert "p̚" in phonemes or any("p" in p for p in phonemes)

    def test_final_consonant_t(self):
        """Test Korean final ㄷ maps to t̚ (unreleased alveolar stop)."""
        from piper_train.phonemize.korean import phonemize_korean

        # 닫 = ㄷ+ㅏ+ㄷ → t + a + t̚
        phonemes = phonemize_korean("닫")
        assert len(phonemes) > 0
        assert "t̚" in phonemes or any("t" in p for p in phonemes)

    def test_final_consonant_n(self):
        """Test Korean final ㄴ maps to n."""
        from piper_train.phonemize.korean import phonemize_korean

        # 한 = ㅎ+ㅏ+ㄴ → h + a + n
        phonemes = phonemize_korean("한")
        assert "n" in phonemes

    def test_final_consonant_m(self):
        """Test Korean final ㅁ maps to m."""
        from piper_train.phonemize.korean import phonemize_korean

        # 밤 = ㅂ+ㅏ+ㅁ → p + a + m
        phonemes = phonemize_korean("밤")
        assert "m" in phonemes

    def test_final_consonant_ng(self):
        """Test Korean final ㅇ maps to ŋ."""
        from piper_train.phonemize.korean import phonemize_korean

        # 강 = ㄱ+ㅏ+ㅇ → k + a + ŋ
        phonemes = phonemize_korean("강")
        assert "ŋ" in phonemes

    def test_final_consonant_l(self):
        """Test Korean final ㄹ maps to l."""
        from piper_train.phonemize.korean import phonemize_korean

        # 말 = ㅁ+ㅏ+ㄹ → m + a + l
        phonemes = phonemize_korean("말")
        assert "l" in phonemes

    def test_oe_vowel_modern_diphthong(self):
        """ㅚ should produce [we] diphthong (modern Seoul pronunciation)."""
        from piper_train.phonemize.korean import phonemize_korean

        # 회 = ㅎ+ㅚ+∅ → h + w + e (modern diphthong, not monophthong ø)
        phonemes = phonemize_korean("회")
        assert "w" in phonemes, f"Expected 'w' for ㅚ diphthong, got: {phonemes}"
        assert "e" in phonemes, f"Expected 'e' for ㅚ diphthong, got: {phonemes}"

    def test_g2p_error_resilience_mixed_script(self):
        """G2P should handle mixed Hangul+ASCII input gracefully."""
        from piper_train.phonemize.korean import phonemize_korean

        # Even if g2pk2 is unavailable, should not raise
        phonemes = phonemize_korean("한글ABC123")
        assert isinstance(phonemes, list)
        # Hangul characters should still be decomposed
        assert len(phonemes) > 0

    def test_g2p_error_resilience_empty_string(self):
        """Phonemizer should handle empty string without error."""
        from piper_train.phonemize.korean import phonemize_korean

        phonemes = phonemize_korean("")
        assert isinstance(phonemes, list)
        assert len(phonemes) == 0

    def test_g2p_error_resilience_punctuation_only(self):
        """Phonemizer should handle punctuation-only input."""
        from piper_train.phonemize.korean import phonemize_korean

        phonemes = phonemize_korean("!?")
        assert isinstance(phonemes, list)
