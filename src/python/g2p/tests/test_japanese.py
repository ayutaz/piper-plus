"""Tests for piper_plus_g2p.japanese — JapanesePhonemizer."""

from tests.conftest import requires_ja


@requires_ja
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns tokens without BOS marker; '$' is sentence-end."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert len(tokens) > 0
        assert "^" not in tokens, "BOS should not be present"

    def test_no_pua_characters(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("東京タワーに行きましょう")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_prosody_symbols(self):
        """phonemize() includes prosody markers '#', '[', ']'."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        # Use a multi-phrase sentence to trigger prosody markers
        tokens = p.phonemize("今日は良い天気ですね。")
        all_tokens_str = " ".join(tokens)
        has_prosody = any(t in ("#", "[", "]") for t in tokens)
        assert has_prosody, f"Expected at least one prosody marker in: {all_tokens_str}"


@requires_ja
class TestNVariants:
    def test_n_bilabial(self):
        """'新聞' should produce N_m (before bilabial m/b/p)."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("新聞")
        assert "N_m" in tokens, f"Expected N_m in {tokens}"

    def test_n_alveolar(self):
        """'こんにちは' should produce N_n (before alveolar n)."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert "N_n" in tokens, f"Expected N_n in {tokens}"

    def test_n_velar(self):
        """'文化' should produce N_ng (before velar k/g)."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("文化")
        assert "N_ng" in tokens, f"Expected N_ng in {tokens}"

    def test_n_uvular(self):
        """'本' should produce N_uvular (phrase-final)."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("本")
        assert "N_uvular" in tokens, f"Expected N_uvular in {tokens}"


@requires_ja
class TestQuestionMarkers:
    def test_generic_question(self):
        """'何？' should produce '?' marker."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何？")
        assert "?" in tokens, f"Expected '?' in {tokens}"

    def test_emphatic_question(self):
        """'何？！' should produce '?!' marker."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何？！")
        assert "?!" in tokens, f"Expected '?!' in {tokens}"

    def test_neutral_question(self):
        """'何。？' should produce '?.' marker."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何。？")
        assert "?." in tokens, f"Expected '?.' in {tokens}"

    def test_tag_question(self):
        """'何～？' should produce '?~' marker."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        # U+FF5E (full-width tilde) + U+FF1F (full-width question mark)
        tokens = p.phonemize("何\uff5e\uff1f")
        assert "?~" in tokens, f"Expected '?~' in {tokens}"


@requires_ja
class TestGetQuestionType:
    def test_get_question_type_declarative(self):
        """Non-question returns '$'."""
        from piper_plus_g2p.japanese import _get_question_type

        assert _get_question_type("今日は良い天気です。") == "$"

    def test_get_question_type_question(self):
        from piper_plus_g2p.japanese import _get_question_type

        assert _get_question_type("元気ですか？") == "?"

    def test_get_question_type_emphatic(self):
        from piper_plus_g2p.japanese import _get_question_type

        assert _get_question_type("本当ですか？！") == "?!"


@requires_ja
class TestCustomDict:
    def test_japanese_phonemizer_with_custom_dict(self):
        """Custom dict replaces words before phonemization."""
        from piper_plus_g2p.custom_dict import CustomDictionary
        from piper_plus_g2p.japanese import JapanesePhonemizer

        d = CustomDictionary(load_defaults=False)
        d.add_word("API", "エーピーアイ")
        p = JapanesePhonemizer(custom_dict=d)
        tokens = p.phonemize("APIを使う")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_japanese_phonemizer_no_custom_dict(self):
        """Default constructor still works."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert isinstance(tokens, list)
        assert len(tokens) > 0


@requires_ja
class TestPhonemizerCache:
    """日本語音素化キャッシュのテスト."""

    def test_cache_hit_returns_same_result(self):
        """同一テキストの2回呼び出しで同一結果."""
        from piper_plus_g2p.japanese import (
            _phonemize_core_cached,
            clear_phonemize_cache,
        )

        clear_phonemize_cache()
        result1 = _phonemize_core_cached("こんにちは")
        result2 = _phonemize_core_cached("こんにちは")
        assert result1 == result2

    def test_cache_returns_tuples(self):
        """キャッシュ版は tuple を返す."""
        from piper_plus_g2p.japanese import (
            _phonemize_core_cached,
            clear_phonemize_cache,
        )

        clear_phonemize_cache()
        tokens, prosody = _phonemize_core_cached("テスト")
        assert isinstance(tokens, tuple)
        assert isinstance(prosody, tuple)

    def test_clear_cache(self):
        """cache_clear() 後に再計算."""
        from piper_plus_g2p.japanese import (
            _phonemize_core_cached,
            clear_phonemize_cache,
        )

        clear_phonemize_cache()
        _phonemize_core_cached("テスト")
        info_before = _phonemize_core_cached.cache_info()
        assert info_before.hits >= 0
        clear_phonemize_cache()
        info_after = _phonemize_core_cached.cache_info()
        assert info_after.hits == 0
        assert info_after.misses == 0

    def test_phonemizer_uses_cache(self):
        """JapanesePhonemizer がキャッシュ版を使用."""
        from piper_plus_g2p.japanese import (
            JapanesePhonemizer,
            _phonemize_core_cached,
            clear_phonemize_cache,
        )

        clear_phonemize_cache()
        p = JapanesePhonemizer()
        p.phonemize("こんにちは")
        p.phonemize("こんにちは")
        info = _phonemize_core_cached.cache_info()
        assert info.hits >= 1


@requires_ja
class TestProsody:
    def test_prosody_length_matches(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("こんにちは")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_values(self):
        """At least some prosody entries are ProsodyInfo (not all None)."""
        from piper_plus_g2p.base import ProsodyInfo
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("こんにちは")
        has_info = any(isinstance(pi, ProsodyInfo) for pi in prosody)
        assert has_info, "Expected at least one non-None ProsodyInfo entry"
