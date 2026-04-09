"""Tests for multilingual auto-promotion in text_to_phoneme_ids_and_prosody().

Prevents regression of the Japanese padding bug:
- JapanesePhonemizer.post_process_ids() is a no-op (BOS/EOS/padding handled
  inline during phonemization).
- When a multilingual model (language_id_map with >1 language) receives
  language="ja", the function must auto-promote to MultilingualPhonemizer
  so that intersperse padding (ID 0 between adjacent phoneme IDs) is applied.
- JA-only models (no language_id_map) must NOT be affected.

Also covers:
  #38 ONNX export output must be 3D [batch, 1, time] (not 4D with extra unsqueeze)
"""

from pathlib import Path

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
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

    key = "-".join(languages)
    # Single non-JA languages (e.g. "en") don't have standalone built-in maps;
    # use the full multilingual map instead.
    try:
        return get_phoneme_id_map(key)
    except ValueError:
        return get_phoneme_id_map("multilingual")


def _get_ja_only_id_map():
    """Build a JA-only phoneme_id_map (no multilingual promotion)."""
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

    return get_phoneme_id_map("ja")


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


@pytest.mark.unit
class TestResolveSpeakerId:
    """Verify that resolve_speaker_id() handles speaker_id/has_sid combinations."""

    @pytest.mark.parametrize(
        "speaker_id, has_sid, expected_list, expected_dtype",
        [
            pytest.param(None, True, [0], "int64", id="default-sid-when-has-sid"),
            pytest.param(5, True, [5], "int64", id="explicit-sid-preserved"),
            pytest.param(None, False, None, None, id="none-when-no-sid-input"),
        ],
    )
    def test_resolve_speaker_id(
        self, speaker_id, has_sid, expected_list, expected_dtype
    ):
        """resolve_speaker_id returns correct ndarray or None."""
        from piper_train.infer_onnx import resolve_speaker_id

        sid = resolve_speaker_id(speaker_id=speaker_id, has_sid=has_sid)

        if expected_list is None:
            assert sid is None, "sid must remain None when has_sid=False"
        else:
            assert sid is not None, "sid must not be None when has_sid=True"
            assert sid.tolist() == expected_list, (
                f"sid should be {expected_list}, got {sid.tolist()}"
            )
            assert sid.dtype.name == expected_dtype


# ---------------------------------------------------------------------------
# ONNX output shape regression test (#38)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # src/python/tests -> repo root
_SHIPPED_MODEL = _REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"


@pytest.mark.unit
class TestOnnxOutputShape:
    """Verify ONNX model output is 3D [batch, 1, time].

    Regression test for #38: an earlier version of the export wrapped the
    decoder output with an extra unsqueeze, producing 4D [batch, 1, 1, time].
    The correct shape is [batch, 1, time] -- batch dim, single audio channel,
    and variable-length time axis.
    """

    def test_onnx_output_is_3d(self):
        """ONNX model 'output' must be 3-dimensional [batch, 1, time]."""
        ort = pytest.importorskip(
            "onnxruntime", reason="onnxruntime required for ONNX output shape test"
        )

        if not _SHIPPED_MODEL.exists():
            pytest.skip(
                f"Shipped test model not found: {_SHIPPED_MODEL}"
            )

        import numpy as np

        session = ort.InferenceSession(str(_SHIPPED_MODEL))

        # Build minimal inputs by inspecting the model
        input_names = {inp.name for inp in session.get_inputs()}

        # A short phoneme_ids sequence (BOS + a few IDs + EOS)
        phoneme_ids = np.array([[1, 0, 10, 0, 11, 0, 2]], dtype=np.int64)
        phoneme_lengths = np.array([phoneme_ids.shape[1]], dtype=np.int64)
        scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

        args = {
            "input": phoneme_ids,
            "input_lengths": phoneme_lengths,
            "scales": scales,
        }

        if "sid" in input_names:
            args["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            args["lid"] = np.array([0], dtype=np.int64)
        if "prosody_features" in input_names:
            num_phonemes = phoneme_ids.shape[1]
            args["prosody_features"] = np.zeros(
                (1, num_phonemes, 3), dtype=np.int64
            )

        outputs = session.run(None, args)
        audio_output = outputs[0]

        assert audio_output.ndim == 3, (
            f"ONNX 'output' must be 3D [batch, 1, time], "
            f"got {audio_output.ndim}D with shape {audio_output.shape}. "
            f"This is a regression: an extra unsqueeze was removed."
        )
        assert audio_output.shape[0] == 1, (
            f"Batch dimension should be 1, got {audio_output.shape[0]}"
        )
        assert audio_output.shape[1] == 1, (
            f"Channel dimension should be 1, got {audio_output.shape[1]}"
        )
        assert audio_output.shape[2] > 0, (
            f"Time dimension should be > 0, got {audio_output.shape[2]}"
        )
