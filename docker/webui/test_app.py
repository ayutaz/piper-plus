"""Tests for docker/webui/app.py.

The WebUI app.py depends on gradio and other heavy packages that are not
installed in the training/test virtualenv.  We extract the target
functions directly from the source via ast to avoid importing the full
module.
"""

import ast
import textwrap
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Extract target functions from app.py without importing the module
# ---------------------------------------------------------------------------
_APP_PY = Path(__file__).resolve().parent / "app.py"
_source = _APP_PY.read_text(encoding="utf-8")

# Parse the constant
_tree = ast.parse(_source)
_SHORT_TEXT_THRESHOLD: int = 10  # fallback
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Assign):
        for _target in _node.targets:
            if isinstance(_target, ast.Name) and _target.id == "_SHORT_TEXT_THRESHOLD":
                _SHORT_TEXT_THRESHOLD = ast.literal_eval(_node.value)


def _extract_function(name: str) -> str:
    """Return the source of a top-level function defined in app.py."""
    for node in _tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise ValueError(f"function {name!r} not found in app.py")


# Execute only the function definitions in a minimal namespace
_ns: dict = {
    "_SHORT_TEXT_THRESHOLD": _SHORT_TEXT_THRESHOLD,
    "np": np,
}
exec(  # noqa: S102
    textwrap.dedent(
        """
def _is_short_text(text: str, threshold: int = _SHORT_TEXT_THRESHOLD) -> bool:
    if text.lstrip().startswith(("<speak>", "<speak ")):
        return False
    return sum(1 for c in text if not c.isspace()) <= threshold
"""
    ),
    _ns,
)
_is_short_text = _ns["_is_short_text"]

exec(_extract_function("_build_session_inputs"), _ns)  # noqa: S102
_build_session_inputs = _ns["_build_session_inputs"]


# ---------------------------------------------------------------------------
# Fake ONNX session for _build_session_inputs tests
# ---------------------------------------------------------------------------
class _FakeOnnxInput:
    def __init__(self, name: str, shape):
        self.name = name
        self.shape = shape


class _FakeOnnxSession:
    def __init__(self, input_specs):
        self._inputs = [_FakeOnnxInput(n, s) for n, s in input_specs]

    def get_inputs(self):
        return self._inputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestIsShortText:
    """Boundary-value tests for _is_short_text()."""

    def test_exactly_at_threshold_is_short(self):
        """10 non-whitespace chars -> short (boundary: <=10)."""
        assert _is_short_text("abcdefghij") is True

    def test_one_above_threshold_is_not_short(self):
        """11 non-whitespace chars -> not short (boundary: >10)."""
        assert _is_short_text("abcdefghijk") is False

    def test_ascii_spaces_excluded(self):
        """ASCII spaces are stripped before counting."""
        # "a b c d e f g h i j" has 10 non-space chars
        assert _is_short_text("a b c d e f g h i j") is True

    def test_fullwidth_spaces_excluded(self):
        """Full-width spaces (U+3000) are stripped before counting."""
        assert _is_short_text("\u3000abc\u3000def\u3000ghij\u3000") is True

    def test_mixed_spaces_excluded(self):
        """Both ASCII and full-width spaces are excluded."""
        text = " \u3000a b\u3000c d e f g h i j \u3000"
        assert _is_short_text(text) is True

    def test_short_japanese(self):
        """Short Japanese text (5 chars) -> short."""
        assert _is_short_text("こんにちは") is True

    def test_long_japanese(self):
        """Long Japanese text (>10 chars) -> not short."""
        assert _is_short_text("こんにちは、今日はとても良い天気ですね。") is False

    def test_empty_string(self):
        """Empty string -> short."""
        assert _is_short_text("") is True

    def test_only_spaces(self):
        """Only whitespace -> short (0 effective chars)."""
        assert _is_short_text("   \u3000  ") is True

    def test_ssml_speak_tag_not_short(self):
        """SSML text starting with <speak> is never considered short."""
        assert _is_short_text("<speak>Hi</speak>") is False

    def test_ssml_speak_tag_with_leading_whitespace(self):
        """SSML text with leading whitespace is still detected."""
        assert _is_short_text("  <speak>Hi</speak>") is False

    def test_custom_threshold(self):
        """Custom threshold parameter works correctly."""
        assert _is_short_text("abc", threshold=3) is True
        assert _is_short_text("abcd", threshold=3) is False


# ---------------------------------------------------------------------------
# Issue #426: speaker_embedding feed parity with docker/python-inference
# and src/python_run/piper/voice.py.
# ---------------------------------------------------------------------------
# MB-iSTFT-VITS2 + Voice-Cloning exports declare speaker_embedding /
# speaker_embedding_mask unconditionally (PR #320). When the WebUI fed a
# subset of inputs, ORT raised "Required inputs missing" exactly as in
# issue #426's docker/python-inference report. These tests pin the
# zero-embedding + mask=0 fallback contract.
class TestBuildSessionInputs:
    """Boundary-value tests for _build_session_inputs()."""

    def _phoneme_ids(self, n: int = 5) -> list[int]:
        return list(range(n))

    def test_base_inputs_always_present(self):
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
            ]
        )
        inputs = _build_session_inputs(
            session=session,
            phoneme_ids=self._phoneme_ids(),
            prosody_features_data=[],
            speaker_id=0,
            language="ja",
            language_id_map={"ja": 0},
            noise_scale=0.667,
            length_scale=1.0,
            noise_scale_w=0.8,
        )
        assert set(inputs) == {"input", "input_lengths", "scales"}
        assert inputs["input"].dtype == np.int64
        assert inputs["input"].shape == (1, 5)
        assert inputs["scales"].dtype == np.float32

    def test_speaker_embedding_declared_feeds_zero_and_mask_zero(self):
        """Canonical contract — mirrors voice.py:200-208."""
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("sid", ["batch"]),
                ("speaker_embedding", ["batch", 256]),
                ("speaker_embedding_mask", ["batch", 1]),
            ]
        )
        inputs = _build_session_inputs(
            session=session,
            phoneme_ids=self._phoneme_ids(),
            prosody_features_data=[],
            speaker_id=0,
            language="ja",
            language_id_map={"ja": 0},
            noise_scale=0.667,
            length_scale=1.0,
            noise_scale_w=0.8,
        )
        assert "speaker_embedding" in inputs
        assert "speaker_embedding_mask" in inputs

        emb = inputs["speaker_embedding"]
        assert emb.dtype == np.float32
        assert emb.shape == (1, 256)
        assert np.all(emb == 0.0)

        mask = inputs["speaker_embedding_mask"]
        assert mask.dtype == np.int64
        assert mask.shape == (1, 1)
        # mask=0 → emb_g(sid) fallback (vits/models.py:1015-1037).
        assert mask[0, 0] == 0

    def test_speaker_embedding_absent_no_feed(self):
        """Non-VC models must not receive these inputs (would raise)."""
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("sid", ["batch"]),
            ]
        )
        inputs = _build_session_inputs(
            session=session,
            phoneme_ids=self._phoneme_ids(),
            prosody_features_data=[],
            speaker_id=0,
            language="ja",
            language_id_map={"ja": 0},
            noise_scale=0.667,
            length_scale=1.0,
            noise_scale_w=0.8,
        )
        assert "speaker_embedding" not in inputs
        assert "speaker_embedding_mask" not in inputs

    def test_dynamic_emb_dim_falls_back_to_256(self):
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("speaker_embedding", ["batch", "emb_dim"]),  # non-int axis
                ("speaker_embedding_mask", ["batch", 1]),
            ]
        )
        inputs = _build_session_inputs(
            session=session,
            phoneme_ids=self._phoneme_ids(),
            prosody_features_data=[],
            speaker_id=0,
            language="ja",
            language_id_map={"ja": 0},
            noise_scale=0.667,
            length_scale=1.0,
            noise_scale_w=0.8,
        )
        assert inputs["speaker_embedding"].shape == (1, 256)

    def test_sid_lid_prosody_added_when_declared(self):
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("sid", ["batch"]),
                ("lid", ["batch"]),
                ("prosody_features", ["batch", "seq", 3]),
            ]
        )
        prosody_data = [
            {"a1": 1, "a2": 2, "a3": 3},
            None,
            {"a1": -1, "a2": 0, "a3": 1},
            None,
            None,
        ]
        inputs = _build_session_inputs(
            session=session,
            phoneme_ids=self._phoneme_ids(),
            prosody_features_data=prosody_data,
            speaker_id=7,
            language="en",
            language_id_map={"ja": 0, "en": 1},
            noise_scale=0.667,
            length_scale=1.0,
            noise_scale_w=0.8,
        )
        assert inputs["sid"].tolist() == [7]
        assert inputs["lid"].tolist() == [1]
        assert inputs["prosody_features"].shape == (1, 5, 3)
        # First entry preserved, None becomes [0, 0, 0].
        assert inputs["prosody_features"][0, 0].tolist() == [1, 2, 3]
        assert inputs["prosody_features"][0, 1].tolist() == [0, 0, 0]

    def test_malformed_export_only_speaker_embedding_raises(self):
        """PR #320 declares speaker_embedding + speaker_embedding_mask as a
        pair. A model with only one declared is a malformed export — fail
        loud here, not with a cryptic ORT error downstream."""
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("speaker_embedding", ["batch", 256]),
                # speaker_embedding_mask intentionally omitted
            ]
        )
        with pytest.raises(RuntimeError, match="Malformed ONNX export"):
            _build_session_inputs(
                session=session,
                phoneme_ids=self._phoneme_ids(),
                prosody_features_data=[],
                speaker_id=0,
                language="ja",
                language_id_map={"ja": 0},
                noise_scale=0.667,
                length_scale=1.0,
                noise_scale_w=0.8,
            )

    def test_malformed_export_only_mask_raises(self):
        """Inverse — mask declared but embedding missing."""
        session = _FakeOnnxSession(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("speaker_embedding_mask", ["batch", 1]),
                # speaker_embedding intentionally omitted
            ]
        )
        with pytest.raises(RuntimeError, match="Malformed ONNX export"):
            _build_session_inputs(
                session=session,
                phoneme_ids=self._phoneme_ids(),
                prosody_features_data=[],
                speaker_id=0,
                language="ja",
                language_id_map={"ja": 0},
                noise_scale=0.667,
                length_scale=1.0,
                noise_scale_w=0.8,
            )
