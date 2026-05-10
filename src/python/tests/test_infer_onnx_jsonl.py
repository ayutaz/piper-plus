"""Unit tests for the JSONL stdin input path of `piper_train.infer_onnx`.

These tests pin the contract of the JSONL loop:
- valid JSONL lines parse into utterance dicts
- empty lines are skipped
- whitespace is stripped before parsing
- malformed JSON raises (downstream caller surfaces the error)
- the per-utterance field shape matches what the inference loop expects
  (`phoneme_ids` required; speaker/language/prosody optional)

Each test invokes the production helper ``piper_train.infer_onnx.parse_jsonl_stream``
directly. Drift between the spec and the production loop is caught immediately
because the test exercises the canonical implementation, not a fixture-side copy.
"""

from __future__ import annotations

import io
import json  # noqa: F401  -- referenced by test_invalid_json_raises_decode_error

import pytest

from piper_train.infer_onnx import parse_jsonl_stream as _parse_jsonl_stream


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestJsonlBasicParsing:
    def test_single_utterance_with_required_field_only(self):
        text = '{"phoneme_ids": [1, 2, 3]}\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 1
        assert utts[0]["phoneme_ids"] == [1, 2, 3]

    def test_single_utterance_with_speaker_id(self):
        text = '{"phoneme_ids": [1, 2, 3], "speaker_id": 5}\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert utts[0]["phoneme_ids"] == [1, 2, 3]
        assert utts[0]["speaker_id"] == 5

    def test_multiple_utterances(self):
        text = (
            '{"phoneme_ids": [1, 2]}\n'
            '{"phoneme_ids": [3, 4]}\n'
            '{"phoneme_ids": [5, 6]}\n'
        )
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 3
        assert [u["phoneme_ids"] for u in utts] == [[1, 2], [3, 4], [5, 6]]

    def test_with_language_id(self):
        text = '{"phoneme_ids": [1, 2, 3], "speaker_id": 0, "language_id": 2}\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert utts[0]["language_id"] == 2

    def test_with_prosody_features(self):
        # prosody_features: list parallel to phoneme_ids (None for special tokens)
        text = (
            '{"phoneme_ids": [1, 2, 3], '
            '"prosody_features": [null, {"a1": -2, "a2": 1, "a3": 0}, null]}\n'
        )
        utts = _parse_jsonl_stream(io.StringIO(text))
        prosody = utts[0]["prosody_features"]
        assert prosody[0] is None
        assert prosody[1] == {"a1": -2, "a2": 1, "a3": 0}
        assert prosody[2] is None


# ---------------------------------------------------------------------------
# Stripping / skip behavior (drift gate against `line.strip()` + `if line`)
# ---------------------------------------------------------------------------


class TestJsonlSkipBehavior:
    def test_empty_lines_are_skipped(self):
        text = '{"phoneme_ids": [1]}\n\n{"phoneme_ids": [2]}\n\n\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 2

    def test_whitespace_only_lines_are_skipped(self):
        text = '{"phoneme_ids": [1]}\n   \n{"phoneme_ids": [2]}\n\t\t\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 2

    def test_leading_trailing_whitespace_is_stripped(self):
        text = '   {"phoneme_ids": [1]}   \n\t{"phoneme_ids": [2]}\t\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 2

    def test_empty_stream_yields_no_utterances(self):
        utts = _parse_jsonl_stream(io.StringIO(""))
        assert utts == []

    def test_only_blank_lines_yields_no_utterances(self):
        utts = _parse_jsonl_stream(io.StringIO("\n\n   \n"))
        assert utts == []


# ---------------------------------------------------------------------------
# Malformed input behavior — caller-visible errors
# ---------------------------------------------------------------------------


class TestJsonlMalformed:
    def test_invalid_json_raises_decode_error(self):
        text = "not a json object\n"
        with pytest.raises(json.JSONDecodeError):
            _parse_jsonl_stream(io.StringIO(text))

    def test_missing_phoneme_ids_does_not_raise_at_parse_time(self):
        # Parser doesn't validate fields — it just parses JSON. The inference
        # loop downstream reads `utt["phoneme_ids"]` and would KeyError, but
        # that's outside the parser contract.
        text = '{"speaker_id": 0}\n'
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert utts == [{"speaker_id": 0}]
        # Downstream behavior contract:
        with pytest.raises(KeyError):
            _ = utts[0]["phoneme_ids"]


# ---------------------------------------------------------------------------
# Drift gate — superseded by direct invocation of `parse_jsonl_stream`.
# Each test in this file now imports the canonical production helper, so
# any refactor of the loop is caught immediately by the unit tests
# themselves rather than by source-level regex grep.
# ---------------------------------------------------------------------------
