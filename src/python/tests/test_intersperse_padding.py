"""Tests for intersperse padding pattern across all supported languages.

The multilingual training data uses intersperse padding: a pad token (ID 0)
is inserted between every phoneme, and the sequence is wrapped with BOS/EOS:

    [BOS, 0, ph1, 0, ph2, 0, ..., 0, EOS]

JapanesePhonemizer.post_process_ids() is a no-op -- it does NOT add
intersperse padding.  For multilingual models, text_to_phoneme_ids_and_prosody
auto-promotes single language codes (e.g. "ja") to the MultilingualPhonemizer
so that intersperse padding is applied correctly.

These tests verify the padding pattern is correct for every supported language.
"""

import pytest

pyopenjtalk = pytest.importorskip(
    "pyopenjtalk", reason="pyopenjtalk required for JA tests"
)
g2p_en = pytest.importorskip("g2p_en", reason="g2p_en required for EN tests")

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody
from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
from piper_train.phonemize.jp_id_map import get_japanese_id_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The six languages used in the multilingual model
_ALL_LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt"]

# language_id_map matching the multilingual dataset config
_LANGUAGE_ID_MAP: dict[str, int] = {
    lang: idx for idx, lang in enumerate(_ALL_LANGUAGES)
}


def _get_multilingual_id_map() -> dict[str, list[int]]:
    """Return the real multilingual phoneme ID map."""
    return get_multilingual_id_map(_ALL_LANGUAGES)


def has_intersperse_padding(ids: list[int], pad_id: int = 0) -> bool:
    """Check if phoneme IDs have intersperse padding pattern.

    In a properly padded sequence, the pattern should be:
    [BOS, pad, ph, pad, ph, pad, ..., pad, EOS]

    We check: starting from BOS, every even index (0, 2, 4, ...) should be
    a real phoneme, and every odd index (1, 3, 5, ...) should be pad (0).
    Exception: the pad token itself (0) can appear at even positions as a
    pause/silence phoneme.
    """
    if len(ids) < 3:
        return False
    # Check that odd positions are all pad tokens
    for i in range(1, len(ids), 2):
        if ids[i] != pad_id:
            return False
    return True


def _no_intersperse_padding(ids: list[int], pad_id: int = 0) -> bool:
    """Check that there is NO intersperse padding pattern.

    Returns True if the sequence does NOT follow the intersperse pattern --
    i.e. at least one odd-indexed position is not a pad token, or the
    sequence is too short to have the pattern.
    """
    if len(ids) < 3:
        return True
    for i in range(1, len(ids), 2):
        if ids[i] != pad_id:
            return True
    return False


# ---------------------------------------------------------------------------
# Tests: multilingual model (intersperse padding expected)
# ---------------------------------------------------------------------------


class TestMultilingualInterspersePadding:
    """Verify intersperse padding for each language in multilingual mode."""

    @pytest.fixture
    def phoneme_id_map(self):
        return _get_multilingual_id_map()

    def test_ja_multilingual_has_intersperse_pattern(self, phoneme_id_map):
        """JA text through multilingual pipeline should have intersperse padding."""
        text = "こんにちは"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="ja",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"JA multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)

    def test_en_has_intersperse_pattern(self, phoneme_id_map):
        """EN text through multilingual pipeline should have intersperse padding."""
        text = "Hello, how are you today?"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="en",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"EN multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)

    def test_zh_has_intersperse_pattern(self, phoneme_id_map):
        """ZH text through multilingual pipeline should have intersperse padding."""
        pytest.importorskip("pypinyin", reason="pypinyin required for ZH tests")

        text = "你好世界"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="zh",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"ZH multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)

    def test_es_has_intersperse_pattern(self, phoneme_id_map):
        """ES text through multilingual pipeline should have intersperse padding."""
        text = "Hola, buenos dias."
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="es",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"ES multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)

    def test_fr_has_intersperse_pattern(self, phoneme_id_map):
        """FR text through multilingual pipeline should have intersperse padding."""
        text = "Bonjour, comment allez-vous?"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="fr",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"FR multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)

    def test_pt_has_intersperse_pattern(self, phoneme_id_map):
        """PT text through multilingual pipeline should have intersperse padding."""
        text = "Bom dia, como vai?"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="pt",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert has_intersperse_padding(ids), (
            f"PT multilingual output lacks intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)


# ---------------------------------------------------------------------------
# Test: JA-only model (NO intersperse padding)
# ---------------------------------------------------------------------------


class TestJaOnlyNoIntersperse:
    """Verify that JA without language_id_map does NOT add intersperse padding."""

    def test_ja_only_no_intersperse(self):
        """JA text without language_id_map should use JapanesePhonemizer (no-op post_process)."""
        phoneme_id_map = get_japanese_id_map()
        text = "こんにちは"

        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="ja",
            language_id_map=None,
        )

        assert len(ids) > 0, "Should produce non-empty output"
        assert _no_intersperse_padding(ids), (
            f"JA-only output should NOT have intersperse padding. "
            f"First 20 IDs: {ids[:20]}"
        )
        assert len(ids) == len(prosody)


# ---------------------------------------------------------------------------
# Test: padding length relation
# ---------------------------------------------------------------------------


class TestPaddingLengthRelation:
    """Verify padded length is roughly 2x unpadded length."""

    def test_padding_length_relation(self):
        """Padded (multilingual) output should be roughly 2x the unpadded (JA-only) length.

        The intersperse pattern inserts a pad token between every phoneme and
        adds BOS + pad at the start and EOS at the end. So the padded length
        should be approximately 2 * unpadded + 3 (BOS, pad-after-BOS, EOS).

        JA-only already includes BOS (^) and EOS ($) inline from phonemization,
        so the unpadded count includes those tokens. The multilingual pipeline
        strips BOS/EOS from the raw phonemes, then re-adds them with padding.

        We verify the ratio is between 1.5 and 2.5 to account for differences
        in BOS/EOS handling between the two paths.
        """
        ja_only_map = get_japanese_id_map()
        multilingual_map = _get_multilingual_id_map()

        text = "こんにちは"

        # JA-only: no intersperse padding
        ids_plain, _ = text_to_phoneme_ids_and_prosody(
            text,
            ja_only_map,
            language="ja",
            language_id_map=None,
        )

        # Multilingual: with intersperse padding
        ids_padded, _ = text_to_phoneme_ids_and_prosody(
            text,
            multilingual_map,
            language="ja",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids_plain) > 0, "JA-only should produce output"
        assert len(ids_padded) > 0, "Multilingual should produce output"

        ratio = len(ids_padded) / len(ids_plain)
        assert 1.5 <= ratio <= 2.5, (
            f"Expected padded/unpadded ratio between 1.5 and 2.5, "
            f"got {ratio:.2f} (padded={len(ids_padded)}, unpadded={len(ids_plain)})"
        )
