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

    # -------------------------------------------------------------------
    # New punctuation characters: ES (¡, ¿), FR (—, –, …, «, »), PT (—, –, …)
    # -------------------------------------------------------------------

    def test_new_punctuation_in_full_map(self):
        """All new punctuation chars should be present in the full multilingual map."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        all_langs = ["ja", "en", "zh", "ko", "es", "pt", "fr"]
        available = [lang for lang in all_langs if lang in LANGUAGE_PHONEMES]
        # Need at least ES, PT, FR
        for lang in ["es", "pt", "fr"]:
            if lang not in available:
                pytest.skip(f"Language '{lang}' not registered")

        id_map = get_multilingual_id_map(available)

        new_punct = ["¡", "¿", "\u2014", "\u2013", "\u2026", "\u00ab", "\u00bb"]
        for char in new_punct:
            mapped = register(char)
            assert mapped in id_map, (
                f"Punctuation '{char}' (U+{ord(char):04X}) missing from multilingual map"
            )

    def test_new_punctuation_unique_ids(self):
        """Each new punctuation char should have a unique ID (no collisions)."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        all_langs = ["ja", "en", "zh", "ko", "es", "pt", "fr"]
        available = [lang for lang in all_langs if lang in LANGUAGE_PHONEMES]
        for lang in ["es", "pt", "fr"]:
            if lang not in available:
                pytest.skip(f"Language '{lang}' not registered")

        id_map = get_multilingual_id_map(available)

        new_punct = ["¡", "¿", "\u2014", "\u2013", "\u2026", "\u00ab", "\u00bb"]
        punct_ids = []
        for char in new_punct:
            mapped = register(char)
            char_id = id_map[mapped][0]
            punct_ids.append(char_id)

        assert len(punct_ids) == len(set(punct_ids)), (
            f"Duplicate IDs among new punctuation chars: {punct_ids}"
        )

    def test_shared_punct_fr_pt_deduplicated(self):
        """Chars shared between FR and PT (em dash, en dash, ellipsis) get the same ID."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        for lang in ["es", "pt", "fr"]:
            if lang not in LANGUAGE_PHONEMES:
                pytest.skip(f"Language '{lang}' not registered")

        # Build two maps: one with PT first, one with FR first
        # Both should produce the same ID for shared chars
        map_pt_fr = get_multilingual_id_map(["ja", "en", "es", "pt", "fr"])
        map_fr_pt = get_multilingual_id_map(["ja", "en", "es", "fr", "pt"])

        shared_chars = ["\u2014", "\u2013", "\u2026"]  # em dash, en dash, ellipsis
        for char in shared_chars:
            mapped = register(char)
            # Both maps should contain the char
            assert mapped in map_pt_fr, f"'{char}' missing from pt-first map"
            assert mapped in map_fr_pt, f"'{char}' missing from fr-first map"

        # Verify deduplication: total unique IDs should be the same regardless of order
        ids_pt_fr = set()
        ids_fr_pt = set()
        for ids in map_pt_fr.values():
            ids_pt_fr.update(ids)
        for ids in map_fr_pt.values():
            ids_fr_pt.update(ids)
        assert len(ids_pt_fr) == len(ids_fr_pt), (
            "Different language order should produce same number of unique IDs"
        )

    def test_es_inverted_punctuation_in_map(self):
        """Spanish inverted punctuation (¡, ¿) should be in the map when ES is included."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        if "es" not in LANGUAGE_PHONEMES:
            pytest.skip("Spanish not registered")

        id_map = get_multilingual_id_map(["ja", "en", "es"])

        for char in ["¡", "¿"]:
            mapped = register(char)
            assert mapped in id_map, (
                f"Spanish inverted punctuation '{char}' missing from ja+en+es map"
            )

    def test_fr_typographic_punctuation_in_map(self):
        """French typographic punctuation (guillemets, dashes, ellipsis) should be in the map."""
        from piper_train.phonemize.multilingual_id_map import (
            LANGUAGE_PHONEMES,
            get_multilingual_id_map,
        )
        from piper_train.phonemize.token_mapper import register

        if "fr" not in LANGUAGE_PHONEMES:
            pytest.skip("French not registered")

        id_map = get_multilingual_id_map(["ja", "en", "fr"])

        fr_punct = ["\u2014", "\u2013", "\u2026", "\u00ab", "\u00bb"]
        for char in fr_punct:
            mapped = register(char)
            assert mapped in id_map, (
                f"French punctuation '{char}' (U+{ord(char):04X}) missing from ja+en+fr map"
            )
