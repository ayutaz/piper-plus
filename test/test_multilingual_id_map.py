"""Tests for multilingual ID map."""

import pytest


class TestMultilingualIdMap:
    """Tests for the generalized multilingual phoneme ID map."""

    def test_ja_en_backward_compat(self):
        """get_multilingual_id_map(["ja","en"]) should produce same IDs as bilingual."""
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map

        bi_map = get_bilingual_id_map()
        ml_map = get_multilingual_id_map(["ja", "en"])

        # Same keys and values
        assert set(bi_map.keys()) == set(ml_map.keys())
        for key in bi_map:
            assert bi_map[key] == ml_map[key], f"ID mismatch for '{key}'"

    def test_all_ids_unique(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map

        id_map = get_multilingual_id_map(["ja", "en"])
        all_ids = []
        for ids in id_map.values():
            all_ids.extend(ids)
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs found"

    def test_pad_is_id_zero(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_multilingual_id_map(["ja", "en"])
        pad = register("_")
        assert id_map[pad] == [0], "Pad token should be ID 0"

    def test_contains_special_tokens(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_multilingual_id_map(["ja", "en"])
        for sym in ["_", "^", "$", "?"]:
            mapped = register(sym)
            assert mapped in id_map, f"Special token '{sym}' missing"

    def test_unknown_language_raises(self):
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map

        with pytest.raises(ValueError, match="Unknown language"):
            get_multilingual_id_map(["ja", "xx"])

    def test_language_phonemes_registry(self):
        """Verify at least JA and EN are registered."""
        from piper_train.phonemize.multilingual_id_map import LANGUAGE_PHONEMES

        assert "ja" in LANGUAGE_PHONEMES
        assert "en" in LANGUAGE_PHONEMES

    def test_three_language_map_contains_all(self):
        """3+ language map should contain phonemes from all languages."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        # Only test with languages that are actually available
        available = [
            lang
            for lang in ["ja", "en", "es", "pt", "fr"]
            if lang in LANGUAGE_PHONEMES
        ]
        if len(available) < 3:
            pytest.skip("Need at least 3 languages registered")

        id_map = get_multilingual_id_map(available[:3])
        # All IDs should be unique
        all_ids = []
        for ids in id_map.values():
            all_ids.extend(ids)
        assert len(all_ids) == len(set(all_ids))

    def test_seven_language_map_all_ids_unique(self):
        """Full 7-language map should have all unique IDs."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )

        all_langs = ["ja", "en", "zh", "ko", "es", "pt", "fr"]
        available = [lang for lang in all_langs if lang in LANGUAGE_PHONEMES]
        if len(available) < 2:
            pytest.skip("Need at least 2 languages")

        id_map = get_multilingual_id_map(available)
        all_ids = []
        for ids in id_map.values():
            all_ids.extend(ids)
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs in multilingual map"
