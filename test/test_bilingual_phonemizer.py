"""Tests for bilingual (JA+EN) phonemizer."""

import pytest


# ---------------------------------------------------------------------------
# bilingual_id_map tests
# ---------------------------------------------------------------------------


class TestBilingualIdMap:
    """Tests for the unified phoneme ID map."""

    def test_map_contains_japanese_phonemes(self):
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_bilingual_id_map()
        # Check core Japanese phonemes are present
        for sym in ["a", "i", "u", "e", "o", "k", "s", "t", "n"]:
            mapped = register(sym)
            assert mapped in id_map, f"Japanese phoneme '{sym}' missing from bilingual map"

    def test_map_contains_english_phonemes(self):
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_bilingual_id_map()
        # Check English-only IPA symbols
        for sym in ["ɑ", "æ", "ʌ", "ə", "ɪ", "ŋ", "ɹ", "ʃ", "θ", "ð", "ˈ", "ˌ"]:
            mapped = register(sym)
            assert mapped in id_map, f"English phoneme '{sym}' missing from bilingual map"

    def test_map_contains_special_tokens(self):
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_bilingual_id_map()
        for sym in ["_", "^", "$"]:
            mapped = register(sym)
            assert mapped in id_map, f"Special token '{sym}' missing"

    def test_all_ids_unique(self):
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map

        id_map = get_bilingual_id_map()
        all_ids = []
        for ids in id_map.values():
            all_ids.extend(ids)
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs found in bilingual map"

    def test_pad_is_id_zero(self):
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map
        from piper_train.phonemize.token_mapper import register

        id_map = get_bilingual_id_map()
        pad = register("_")
        assert id_map[pad] == [0], "Pad token should be ID 0"


# ---------------------------------------------------------------------------
# _segment_text tests
# ---------------------------------------------------------------------------


class TestSegmentText:
    """Tests for language segmentation."""

    def test_pure_japanese(self):
        from piper_train.phonemize.bilingual import _segment_text

        segments = _segment_text("こんにちは")
        assert len(segments) == 1
        assert segments[0][0] == "ja"
        assert segments[0][1] == "こんにちは"

    def test_pure_english(self):
        from piper_train.phonemize.bilingual import _segment_text

        segments = _segment_text("hello world")
        assert len(segments) == 1
        assert segments[0][0] == "en"

    def test_mixed_ja_en(self):
        from piper_train.phonemize.bilingual import _segment_text

        segments = _segment_text("今日はgoodですね")
        assert len(segments) == 3
        assert segments[0][0] == "ja"
        assert segments[1][0] == "en"
        assert segments[2][0] == "ja"

    def test_mixed_with_spaces(self):
        from piper_train.phonemize.bilingual import _segment_text

        segments = _segment_text("今日は good morning ですね")
        assert segments[0][0] == "ja"
        assert segments[1][0] == "en"
        assert "good morning" in segments[1][1]
        assert segments[2][0] == "ja"

    def test_empty_text(self):
        from piper_train.phonemize.bilingual import _segment_text

        assert _segment_text("") == []
        assert _segment_text("   ") == []


# ---------------------------------------------------------------------------
# BilingualPhonemizer tests
# ---------------------------------------------------------------------------


class TestBilingualPhonemizer:
    """Tests for the bilingual phonemizer."""

    def test_japanese_only(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        phonemes = bp.phonemize("こんにちは")
        assert len(phonemes) > 0
        # Should not contain BOS/EOS (stripped by phonemize_with_prosody)
        from piper_train.phonemize.token_mapper import register
        bos = register("^")
        eos = register("$")
        assert bos not in phonemes
        assert eos not in phonemes

    def test_english_only(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        phonemes = bp.phonemize("hello")
        assert len(phonemes) > 0

    def test_mixed_text(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        phonemes = bp.phonemize("今日はgoodですね")
        assert len(phonemes) > 0

    def test_prosody_alignment(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        phonemes, prosody = bp.phonemize_with_prosody("今日はgoodですね")
        assert len(phonemes) == len(prosody)

    def test_get_phoneme_id_map(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        id_map = bp.get_phoneme_id_map()
        assert id_map is not None
        assert len(id_map) > 0

    def test_post_process_ids_adds_bos_eos(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        id_map = bp.get_phoneme_id_map()

        # Simple test with dummy IDs
        from piper_train.phonemize.token_mapper import register
        a_sym = register("a")
        a_id = id_map[a_sym][0]
        bos_sym = register("^")
        eos_sym = register("$")

        result_ids, result_prosody = bp.post_process_ids(
            [a_id], [None], id_map
        )
        # Should have BOS + pad + a + pad + EOS
        bos_id = id_map[bos_sym][0]
        eos_id = id_map[eos_sym][0]
        assert result_ids[0] == bos_id
        assert result_ids[-1] == eos_id
        assert len(result_ids) == len(result_prosody)


# ---------------------------------------------------------------------------
# Registry integration test
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_ja_en_registered(self):
        from piper_train.phonemize.registry import available_languages, get_phonemizer

        assert "ja-en" in available_languages()
        p = get_phonemizer("ja-en")
        assert p is not None

    def test_end_to_end_with_id_map(self):
        """Full pipeline: text → phonemes → IDs → post-processed IDs."""
        from piper_train.phonemize.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        id_map = p.get_phoneme_id_map()
        assert id_map is not None

        phonemes, prosody = p.phonemize_with_prosody("今日はgoodですね")

        # Convert to IDs
        phoneme_ids = []
        prosody_features = []
        for ph, pr in zip(phonemes, prosody, strict=True):
            if ph in id_map:
                ids = id_map[ph]
                phoneme_ids.extend(ids)
                for _ in ids:
                    if pr is not None:
                        prosody_features.append({"a1": pr.a1, "a2": pr.a2, "a3": pr.a3})
                    else:
                        prosody_features.append(None)

        assert len(phoneme_ids) > 0
        assert len(phoneme_ids) == len(prosody_features)

        # Post-process
        final_ids, final_prosody = p.post_process_ids(
            phoneme_ids, prosody_features, id_map
        )
        assert len(final_ids) == len(final_prosody)
        assert len(final_ids) > len(phoneme_ids)  # BOS/EOS/padding added
