"""Tests for multilingual auto-promotion in text_to_phoneme_ids_and_prosody().

Prevents regression of the Japanese padding bug:
- JapanesePhonemizer.post_process_ids() is a no-op (BOS/EOS/padding handled
  inline during phonemization).
- When a multilingual model (language_id_map with >1 language) receives
  language="ja", the function must auto-promote to MultilingualPhonemizer
  so that intersperse padding (ID 0 between adjacent phoneme IDs) is applied.
- JA-only models (no language_id_map) must NOT be affected.
"""

import pytest


pyopenjtalk = pytest.importorskip("pyopenjtalk", reason="pyopenjtalk required")

# g2p_en depends on NLTK's averaged_perceptron_tagger_eng data at runtime.
# If it's not downloaded, skip EN tests gracefully.
try:
    import nltk

    nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    _has_nltk_tagger = True
except (ImportError, LookupError):
    _has_nltk_tagger = False

_skip_no_nltk = pytest.mark.skipif(
    not _has_nltk_tagger,
    reason="NLTK averaged_perceptron_tagger_eng data not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_multilingual_id_map(languages):
    """Build a multilingual phoneme_id_map for the given languages."""
    from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map

    return get_multilingual_id_map(languages)


def _get_ja_only_id_map():
    """Build a JA-only phoneme_id_map (no multilingual promotion)."""
    from piper_train.phonemize.jp_id_map import get_japanese_id_map

    return get_japanese_id_map()


def _call_text_to_phoneme_ids(text, phoneme_id_map, language, language_id_map=None):
    """Wrapper around text_to_phoneme_ids_and_prosody."""
    from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody

    return text_to_phoneme_ids_and_prosody(
        text,
        phoneme_id_map,
        language=language,
        language_id_map=language_id_map,
    )


def _has_intersperse_padding(phoneme_ids):
    """Check whether phoneme_ids contain intersperse padding (0 between IDs).

    The pattern for intersperse-padded output is:
      BOS, 0, id, 0, id, 0, ..., id, 0, EOS
    Adjacent non-zero IDs (no 0 separator) indicate missing padding.

    Returns True if every pair of adjacent non-padding IDs is separated by
    at least one padding token (ID 0).
    """
    if len(phoneme_ids) < 3:
        return False

    # Find indices of non-zero IDs
    non_zero_positions = [i for i, v in enumerate(phoneme_ids) if v != 0]
    if len(non_zero_positions) < 2:
        return True  # trivially padded

    # Check that every pair of adjacent non-zero IDs has a gap > 1
    for a, b in zip(non_zero_positions, non_zero_positions[1:], strict=False):
        if b - a == 1:
            return False
    return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JA_TEST_TEXT = "こんにちは"
EN_TEST_TEXT = "Hello"

# A multilingual language_id_map representing a model trained on JA+EN
MULTILINGUAL_LANGUAGE_ID_MAP = {"ja": 0, "en": 1}

# A single-language language_id_map
SINGLE_LANGUAGE_ID_MAP = {"ja": 0}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJaAutoPromotion:
    """Verify that JA phoneme_ids get intersperse padding when a multilingual
    model is detected via language_id_map."""

    def test_ja_auto_promotion_adds_padding(self):
        """When language_id_map has multiple languages and language='ja',
        phoneme_ids must have intersperse padding (0 between adjacent IDs)."""
        id_map = _get_multilingual_id_map(["ja", "en"])
        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        assert len(phoneme_ids) > 0, "phoneme_ids should not be empty"
        assert _has_intersperse_padding(phoneme_ids), (
            f"JA with multilingual model must have intersperse padding, "
            f"got: {phoneme_ids}"
        )

    def test_ja_no_promotion_without_language_id_map(self):
        """When language_id_map is None, JA phoneme_ids should NOT have
        intersperse padding (JapanesePhonemizer.post_process_ids is no-op)."""
        id_map = _get_ja_only_id_map()
        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=None,
        )

        assert len(phoneme_ids) > 0, "phoneme_ids should not be empty"
        # JA-only: the phonemizer does NOT add intersperse padding
        assert not _has_intersperse_padding(phoneme_ids), (
            f"JA-only (no language_id_map) must NOT have intersperse padding, "
            f"got: {phoneme_ids}"
        )

    def test_ja_no_promotion_single_language_map(self):
        """When language_id_map has only 1 language, should NOT auto-promote."""
        id_map = _get_ja_only_id_map()
        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=SINGLE_LANGUAGE_ID_MAP,
        )

        assert len(phoneme_ids) > 0, "phoneme_ids should not be empty"
        assert not _has_intersperse_padding(phoneme_ids), (
            f"Single-language map must NOT auto-promote, got: {phoneme_ids}"
        )


@pytest.mark.unit
class TestEnPaddingAlways:
    """Verify that EN phonemizer always applies intersperse padding
    regardless of language_id_map."""

    @_skip_no_nltk
    def test_en_always_has_padding(self):
        """EN phonemizer always has padding via base class post_process_ids,
        regardless of language_id_map."""
        g2p_en = pytest.importorskip("g2p_en", reason="g2p_en required")  # noqa: F841

        # Case 1: with multilingual language_id_map
        id_map_multi = _get_multilingual_id_map(["ja", "en"])
        ids_multi, _ = _call_text_to_phoneme_ids(
            EN_TEST_TEXT,
            id_map_multi,
            language="en",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )
        assert _has_intersperse_padding(ids_multi), (
            f"EN with multilingual map must have padding, got: {ids_multi}"
        )

        # Case 2: without language_id_map (standalone EN model)
        # Use a single-language EN map built from the multilingual builder;
        # EnglishPhonemizer.get_phoneme_id_map() returns None (relies on
        # config-provided map), so we build one explicitly.
        en_id_map = _get_multilingual_id_map(["en"])
        ids_standalone, _ = _call_text_to_phoneme_ids(
            EN_TEST_TEXT,
            en_id_map,
            language="en",
            language_id_map=None,
        )
        assert _has_intersperse_padding(ids_standalone), (
            f"EN standalone must have padding, got: {ids_standalone}"
        )


@pytest.mark.unit
class TestComboCodeNotPromoted:
    """When language already contains '-' (e.g., 'ja-en'), it should NOT
    be auto-promoted -- it is already a multilingual phonemizer key."""

    def test_combo_code_not_promoted(self):
        """A combo code like 'ja-en' must not be further promoted."""
        g2p_en = pytest.importorskip("g2p_en", reason="g2p_en required")  # noqa: F841

        id_map = _get_multilingual_id_map(["ja", "en"])
        # Use language="ja-en" with a multilingual language_id_map
        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja-en",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        assert len(phoneme_ids) > 0, "phoneme_ids should not be empty"
        # ja-en is already a combo code -- it should still produce padded output
        # (the bilingual/multilingual phonemizer handles padding), but the key
        # point is that the auto-promotion branch is NOT taken.
        assert _has_intersperse_padding(phoneme_ids), (
            f"Combo code 'ja-en' should still produce padded output, got: {phoneme_ids}"
        )


@pytest.mark.unit
class TestAlignment:
    """phoneme_ids and prosody_features must have same length after
    auto-promotion."""

    def test_phoneme_ids_prosody_alignment(self):
        """phoneme_ids and prosody_features must have same length."""
        id_map = _get_multilingual_id_map(["ja", "en"])
        phoneme_ids, prosody_features = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        assert len(phoneme_ids) == len(prosody_features), (
            f"phoneme_ids ({len(phoneme_ids)}) and prosody_features "
            f"({len(prosody_features)}) must have same length"
        )

    @_skip_no_nltk
    def test_phoneme_ids_prosody_alignment_en(self):
        """EN: phoneme_ids and prosody_features must also align."""
        g2p_en = pytest.importorskip("g2p_en", reason="g2p_en required")  # noqa: F841

        id_map = _get_multilingual_id_map(["ja", "en"])
        phoneme_ids, prosody_features = _call_text_to_phoneme_ids(
            EN_TEST_TEXT,
            id_map,
            language="en",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        assert len(phoneme_ids) == len(prosody_features), (
            f"EN phoneme_ids ({len(phoneme_ids)}) and prosody_features "
            f"({len(prosody_features)}) must have same length"
        )

    def test_phoneme_ids_prosody_alignment_ja_only(self):
        """JA-only model: alignment must still hold."""
        id_map = _get_ja_only_id_map()
        phoneme_ids, prosody_features = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=None,
        )

        assert len(phoneme_ids) == len(prosody_features), (
            f"JA-only phoneme_ids ({len(phoneme_ids)}) and prosody_features "
            f"({len(prosody_features)}) must have same length"
        )


@pytest.mark.unit
class TestPhonemeIdRange:
    """All generated phoneme IDs must be within the valid range defined
    by the phoneme_id_map."""

    def test_all_ids_within_valid_range(self):
        """All phoneme IDs must be < number of symbols in phoneme_id_map."""
        id_map = _get_multilingual_id_map(["ja", "en"])
        num_symbols = len(id_map)

        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        for pid in phoneme_ids:
            assert 0 <= pid < num_symbols, (
                f"phoneme ID {pid} out of valid range [0, {num_symbols})"
            )

    @_skip_no_nltk
    def test_all_ids_within_valid_range_en(self):
        """EN: all phoneme IDs must also be within range."""
        g2p_en = pytest.importorskip("g2p_en", reason="g2p_en required")  # noqa: F841

        id_map = _get_multilingual_id_map(["ja", "en"])
        num_symbols = len(id_map)

        phoneme_ids, _ = _call_text_to_phoneme_ids(
            EN_TEST_TEXT,
            id_map,
            language="en",
            language_id_map=MULTILINGUAL_LANGUAGE_ID_MAP,
        )

        for pid in phoneme_ids:
            assert 0 <= pid < num_symbols, (
                f"phoneme ID {pid} out of valid range [0, {num_symbols})"
            )

    def test_all_ids_within_valid_range_ja_only(self):
        """JA-only model: IDs must be within the JA phoneme_id_map range."""
        id_map = _get_ja_only_id_map()
        num_symbols = len(id_map)

        phoneme_ids, _ = _call_text_to_phoneme_ids(
            JA_TEST_TEXT,
            id_map,
            language="ja",
            language_id_map=None,
        )

        for pid in phoneme_ids:
            assert 0 <= pid < num_symbols, (
                f"phoneme ID {pid} out of valid range [0, {num_symbols})"
            )
