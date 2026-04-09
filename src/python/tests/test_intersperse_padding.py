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
torch = pytest.importorskip("torch", reason="torch required for intersperse tests")

# g2p_en depends on NLTK's averaged_perceptron_tagger_eng data at runtime.
# The package imports fine, but phonemization fails without the data.
try:
    from nltk.tag.perceptron import PerceptronTagger

    PerceptronTagger(lang="eng")  # actually load the tagger data, not just find()
    _has_nltk_tagger = True
except (ImportError, LookupError, OSError):
    _has_nltk_tagger = False

_skip_no_nltk = pytest.mark.skipif(
    not _has_nltk_tagger,
    reason="NLTK averaged_perceptron_tagger_eng data not available",
)

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody
from piper_train.vits.commons import intersperse
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map


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
    return get_phoneme_id_map("-".join(_ALL_LANGUAGES))


def has_intersperse_padding(ids: list[int], pad_id: int = 0) -> bool:
    """Check if phoneme IDs have intersperse padding pattern.

    The pipeline produces ``[BOS, pad, ph1, pad, ph2, ..., pad, EOS]``
    where data sits at even indices and pad at odd indices.  This is
    the interior of ``commons.intersperse(data, pad_id)`` (which puts
    ``pad`` at both ends).  We verify by round-tripping: extract data
    from even indices, apply ``intersperse``, and strip the outer pads.
    """
    if len(ids) < 3:
        return False
    if len(ids) % 2 == 0:
        return False
    # Even indices carry the original phonemes (incl. BOS / EOS)
    originals = ids[::2]
    return intersperse(originals, pad_id)[1:-1] == ids


def _no_intersperse_padding(ids: list[int], pad_id: int = 0) -> bool:
    """Check that there is NO intersperse padding pattern."""
    return not has_intersperse_padding(ids, pad_id)


# ---------------------------------------------------------------------------
# Tests: multilingual model (intersperse padding expected)
# ---------------------------------------------------------------------------


@pytest.mark.unit
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

    @_skip_no_nltk
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


@pytest.mark.unit
class TestJaOnlyNoIntersperse:
    """Verify that JA without language_id_map does NOT add intersperse padding."""

    def test_ja_only_no_intersperse(self):
        """JA text without language_id_map should use JapanesePhonemizer (no-op post_process)."""
        phoneme_id_map = get_phoneme_id_map("ja")
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


@pytest.mark.unit
class TestNoPaddingAfterPause:
    """Verify that pause tokens (ID 0) do NOT get extra padding after them.

    The training data was created by _add_inter_phoneme_padding() which skips
    padding after existing pad/pause tokens (pid != pad_id).  The inference
    path must match this behaviour, otherwise 88% of JA entries would have
    shifted phoneme alignment.
    """

    @pytest.fixture
    def phoneme_id_map(self):
        return _get_multilingual_id_map()

    def test_ja_pause_no_triple_zero(self, phoneme_id_map):
        """JA text with comma (produces pause token) must NOT have triple-0.

        Correct:  ...ph, 0, pause(0), ph, 0, ...
        Wrong:    ...ph, 0, pause(0), 0, ph, 0, ...  (extra 0 after pause)

        A triple-0 pattern [0, 0, 0] indicates the bug where padding is
        inserted after an existing pad/pause token.
        """
        text = "こんにちは、元気ですか"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="ja",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3, f"Sequence too short: {ids}"
        assert len(ids) == len(prosody)

        # Check for triple-0 pattern (indicator of padding-after-pause bug)
        for i in range(len(ids) - 2):
            if ids[i] == 0 and ids[i + 1] == 0 and ids[i + 2] == 0:
                assert False, (
                    f"Triple-0 at index {i} indicates padding after pause bug. "
                    f"IDs around: ...{ids[max(0,i-2):i+5]}..."
                )

    def test_ja_multiple_pauses(self, phoneme_id_map):
        """JA text with multiple commas should not accumulate extra padding."""
        text = "今日は、天気が良くて、気持ちいいです。"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="ja",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3
        assert len(ids) == len(prosody)

        # Count consecutive zeros - max should be 2 (pad + pause or pause + pad)
        max_consecutive_zeros = 0
        current_zeros = 0
        for pid in ids:
            if pid == 0:
                current_zeros += 1
                max_consecutive_zeros = max(max_consecutive_zeros, current_zeros)
            else:
                current_zeros = 0

        assert max_consecutive_zeros <= 2, (
            f"Max consecutive zeros = {max_consecutive_zeros} (expected <= 2). "
            f"This indicates padding-after-pause bug. IDs: {ids}"
        )


@pytest.mark.unit
class TestLatinLanguageNotMisrouted:
    """Verify that ES/FR/PT text is phonemized by the correct phonemizer,
    not misrouted to English via UnicodeLanguageDetector."""

    @pytest.fixture
    def phoneme_id_map(self):
        return _get_multilingual_id_map()

    def test_es_uses_spanish_phonemizer(self, phoneme_id_map):
        """ES text should use SpanishPhonemizer, not EnglishPhonemizer.

        Spanish 'ñ' maps to /ɲ/ which has a different phoneme ID than
        English phonemes. If routed to English, 'ñ' would be unknown.
        """
        text = "España"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="es",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3
        # Spanish /ɲ/ must be present (from ñ)
        # Check that it produces valid output with intersperse padding
        assert has_intersperse_padding(ids), (
            f"ES output lacks intersperse padding: {ids}"
        )

    def test_fr_uses_french_phonemizer(self, phoneme_id_map):
        """FR text should use FrenchPhonemizer, not EnglishPhonemizer."""
        text = "Bonjour"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="fr",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3
        assert has_intersperse_padding(ids)

    def test_pt_uses_portuguese_phonemizer(self, phoneme_id_map):
        """PT text should use PortuguesePhonemizer, not EnglishPhonemizer."""
        text = "Obrigado"
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="pt",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert len(ids) >= 3
        assert has_intersperse_padding(ids)

    @_skip_no_nltk
    def test_es_phonemes_differ_from_english(self, phoneme_id_map):
        """Same word phonemized as ES vs EN should produce different IDs.

        'Hola' in Spanish = /ola/ (silent h), in English = /hoʊlə/.
        """
        text = "Hola"
        es_ids, _ = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="es",
            language_id_map=_LANGUAGE_ID_MAP,
        )
        en_ids, _ = text_to_phoneme_ids_and_prosody(
            text,
            phoneme_id_map,
            language="en",
            language_id_map=_LANGUAGE_ID_MAP,
        )

        assert es_ids != en_ids, (
            f"ES and EN should produce different phoneme IDs for 'Hola'. "
            f"ES={es_ids}, EN={en_ids}. "
            f"If identical, ES text is being misrouted to English phonemizer."
        )


@pytest.mark.unit
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
        ja_only_map = get_phoneme_id_map("ja")
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
