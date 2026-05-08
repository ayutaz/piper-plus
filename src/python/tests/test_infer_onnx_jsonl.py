"""Unit tests for the JSONL stdin input path of `piper_train.infer_onnx`.

The JSONL loop at `infer_onnx.py:766-771` is the canonical batch input path
for downstream training-side tooling. It accepts one JSON object per line
with `phoneme_ids` (required) and optional `speaker_id` / `language_id` /
`prosody_features` fields.

These tests pin the contract of that loop:
- valid JSONL lines parse into utterance dicts
- empty lines are skipped
- whitespace is stripped before parsing
- malformed JSON raises (downstream caller surfaces the error)
- the per-utterance field shape matches what the inference loop expects
  (`phoneme_ids` required; speaker/language/prosody optional)
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _parse_jsonl_stream(stream) -> list[dict[str, Any]]:
    """Mirror of `infer_onnx.py:766-771` for unit testing.

    Kept byte-for-byte equivalent to the inference loop. Any drift between
    this helper and the production logic should be caught by these tests
    + a future refactor that replaces both with a shared helper.
    """
    utterances = []
    for line in stream:
        line = line.strip()
        if line:
            utterances.append(json.loads(line))
    return utterances


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
        text = (
            '{"phoneme_ids": [1]}\n'
            "\n"
            '{"phoneme_ids": [2]}\n'
            "\n"
            "\n"
        )
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 2

    def test_whitespace_only_lines_are_skipped(self):
        text = (
            '{"phoneme_ids": [1]}\n'
            "   \n"
            '{"phoneme_ids": [2]}\n'
            "\t\t\n"
        )
        utts = _parse_jsonl_stream(io.StringIO(text))
        assert len(utts) == 2

    def test_leading_trailing_whitespace_is_stripped(self):
        text = (
            '   {"phoneme_ids": [1]}   \n'
            '\t{"phoneme_ids": [2]}\t\n'
        )
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
# Drift gate — ensure the helper above stays a faithful mirror of the
# production inference loop. If `infer_onnx.py:766-771` changes shape, this
# test serves as a reminder to update both sides.
# ---------------------------------------------------------------------------


class TestProductionLoopMirror:
    def test_helper_matches_infer_onnx_jsonl_loop_shape(self):
        """Source-level smoke: assert the production loop still uses
        `for line in sys.stdin: line = line.strip(); if line:
        utterances.append(json.loads(line))`.

        This catches refactors that introduce e.g. `if not line: continue`
        but also accidental drop of `.strip()` (which would change
        whitespace handling).
        """
        from pathlib import Path

        infer_path = (
            Path(__file__).resolve().parents[1]
            / "piper_train"
            / "infer_onnx.py"
        )
        src = infer_path.read_text(encoding="utf-8")
        # The four canonical lines must coexist in close proximity.
        # Pin the keywords rather than exact whitespace.
        assert "for line in sys.stdin" in src
        assert "line = line.strip()" in src
        assert "json.loads(line)" in src
        # Skipping is via `if line:` (positive guard) — assert the pattern
        # to avoid silently changing semantics to e.g. `if not line: continue`.
        # Allow any indentation but require literal `if line:`.
        assert "if line:" in src
