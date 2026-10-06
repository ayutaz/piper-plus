"""Regression tests for model PUA maps in synthesis and phoneme timing."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from piper_plus_g2p.base import ProsodyInfo
from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import inference  # noqa: E402


TOKENS = ["sh", "ch", "N_n", "N_uvular"]


@pytest.fixture
def phonemizer(monkeypatch):
    prosody = [ProsodyInfo(1, 2, 3), None, ProsodyInfo(4, 5, 6), None]
    fake = SimpleNamespace(phonemize_with_prosody=lambda _text: (TOKENS, prosody))
    monkeypatch.setattr(inference, "get_phonemizer", lambda _language: fake)


@pytest.fixture(params=["pua", "legacy"])
def id_map(request):
    return {
        (chr(FIXED_PUA_MAPPING[token]) if request.param == "pua" else token): [i]
        for i, token in enumerate(TOKENS, start=10)
    }


def test_synthesis_keeps_all_tokens_and_aligned_prosody(phonemizer, id_map, caplog):
    ids, prosody = inference.text_to_phoneme_ids_and_prosody("音声", id_map)
    assert ids == [10, 11, 12, 13]
    assert prosody == [
        {"a1": 1, "a2": 2, "a3": 3},
        None,
        {"a1": 4, "a2": 5, "a3": 6},
        None,
    ]
    assert "Unknown phoneme" not in caplog.text


def test_timing_keeps_tokens_ids_and_prosody(phonemizer, id_map, caplog):
    engine = object.__new__(inference.PiperInferenceEngine)
    engine.phoneme_id_map = id_map
    engine.has_durations = True
    engine.has_sid = engine.has_lid = engine.has_speaker_embedding = False
    engine.has_prosody = True
    engine.hop_length = 256
    engine.sample_rate = 22050
    engine.model = MagicMock()
    engine.model.get_outputs.return_value = [SimpleNamespace(name="durations")]
    engine.model.run.return_value = [np.array([[1, 2, 3, 4]])]
    result = engine.synthesize_with_timing("音声")
    assert [p["phoneme"] for p in result["phonemes"]] == TOKENS
    inputs = engine.model.run.call_args.args[1]
    assert inputs["input"].tolist() == [[10, 11, 12, 13]]
    assert inputs["prosody_features"].tolist() == [
        [[1, 2, 3], [0, 0, 0], [4, 5, 6], [0, 0, 0]]
    ]
    assert "Unknown phoneme" not in caplog.text


def test_explicit_legacy_ids_take_precedence(phonemizer):
    mapping = {token: [i] for i, token in enumerate(TOKENS, start=10)}
    mapping.update({chr(FIXED_PUA_MAPPING[token]): [99] for token in TOKENS})
    ids, _ = inference.text_to_phoneme_ids_and_prosody("音声", mapping)
    assert ids == [10, 11, 12, 13]
