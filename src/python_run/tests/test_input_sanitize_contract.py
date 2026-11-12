"""The Python runtime strips control characters before reading a text.

Contract: docs/spec/input-sanitize-contract.toml (runtime ``python-runtime``).
Cases: tests/fixtures/g2p/input_sanitize_cases.json, read by every runtime.

Regression focus: #934 (2026-11) stripped control characters in the G2P
package only. ``PiperVoice`` reads text with its own phonemizers
(``piper_plus.phonemize``), so a NUL inside "hola" still split the word in
two there, a NUL after "?" became a sentence of its own (an extra chunk of
BOS/EOS audio), and a text made long by control characters lost the
short-text padding. ``PiperPlus`` split the raw text into sentences before
its G2P stripped it, so a NUL after "." hid the sentence boundary there.
Every public entry point below reads a dirty text the way it reads the clean
one.
"""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import pytest

from piper_plus.text_sanitize import strip_control_chars

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "g2p" / "input_sanitize_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
MODEL = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"

# The languages of the test model (its language_id_map). pt-PT reads with the
# pt id; ko and sv are not in the model.
MODEL_LANGUAGES = {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5, "pt-PT": 5}
ONLY_CONTROLS = next(
    c["input"] for c in CASES["strip_cases"] if c["name"] == "only_controls"
)


def _cases(*, synth: bool) -> list[dict]:
    """word_cases the model can read, and the pipeline cases.

    Synthesis is slower, so the synthesizing entry points read one case per
    language and control kind (the NUL inside a word, and each space-like
    control), plus every pipeline case.
    """
    out = []
    for case in CASES["word_cases"]:
        language = case["language"]
        if language not in MODEL_LANGUAGES and language != "multilingual":
            continue
        if synth and case["control"] not in ("U+0000", "U+000C"):
            continue
        out.append(case)
    return out + CASES["pipeline_cases"]


def _id(case: dict) -> str:
    return f"{case.get('name') or case['language']}-{case['clean']}-{case.get('control', '')}"


@pytest.fixture(scope="module")
def voice():
    if not MODEL.exists():
        pytest.skip(f"{MODEL.name} not available locally")
    pytest.importorskip("pyopenjtalk")
    from piper_plus.voice import PiperVoice

    return PiperVoice.load(str(MODEL))


@pytest.fixture(scope="module")
def tts():
    if not MODEL.exists():
        pytest.skip(f"{MODEL.name} not available locally")
    pytest.importorskip("piper_plus_g2p")
    from piper_plus.api.api import PiperPlus

    return PiperPlus(str(MODEL), device="cpu", download=False, noise_scale_w=0.0)


def _lid(case: dict) -> int | None:
    return MODEL_LANGUAGES.get(case["language"])


# ---------------------------------------------------------------- entry points
# Each reads a text and returns what can be compared: phonemes, or the
# length of the audio (noise_w = 0 makes the durations deterministic).


def _phonemize(voice, text, lid):
    return voice.phonemize(text, language_id=lid)


def _stream_raw(voice, text, lid):
    return [
        len(chunk)
        for chunk in voice.synthesize_stream_raw(text, noise_w=0.0, language_id=lid)
    ]


def _synthesize(voice, text, lid):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        voice.synthesize(text, wav, noise_w=0.0, language_id=lid)
    with wave.open(io.BytesIO(buf.getvalue()), "rb") as wav:
        return wav.getnframes()


def _with_timing(voice, text, lid):
    wav_bytes, timing = voice.synthesize_with_timing(
        text, noise_w=0.0, language_id=lid
    )
    phonemes = None if timing is None else [p.phoneme for p in timing.phonemes]
    return len(wav_bytes), phonemes


VOICE_SYNTH = {
    "synthesize_stream_raw": _stream_raw,
    "synthesize": _synthesize,
    "synthesize_with_timing": _with_timing,
}

TTS_ENTRIES = {
    "PiperPlus.synthesize": lambda tts, text: len(tts.synthesize(text).audio),
    "PiperPlus.synthesize_stream": lambda tts, text: [
        len(r.audio) for r in tts.synthesize_stream(text)
    ],
}


# ----------------------------------------------------------------------- tests


@pytest.mark.parametrize("case", CASES["strip_cases"], ids=lambda c: c["name"])
def test_strip_cases(case):
    assert strip_control_chars(case["input"]) == case["expected"]


def test_strip_is_idempotent():
    for case in CASES["strip_cases"]:
        once = strip_control_chars(case["input"])
        assert strip_control_chars(once) == once


@pytest.mark.parametrize("case", _cases(synth=False), ids=_id)
def test_phonemize_reads_dirty_like_clean(voice, case):
    lid = _lid(case)
    assert _phonemize(voice, case["dirty"], lid) == _phonemize(voice, case["clean"], lid)


@pytest.mark.parametrize("case", _cases(synth=False), ids=_id)
def test_multilingual_phonemizer_reads_dirty_like_clean(case):
    pytest.importorskip("pyopenjtalk")
    from piper_plus.phonemize.multilingual import MultilingualPhonemizer

    m = MultilingualPhonemizer(["ja", "en", "zh", "es", "fr", "pt"])
    assert m.phonemize(case["dirty"]) == m.phonemize(case["clean"])


@pytest.mark.parametrize("entry", VOICE_SYNTH)
@pytest.mark.parametrize("case", _cases(synth=True), ids=_id)
def test_voice_synthesis_reads_dirty_like_clean(voice, entry, case):
    read = VOICE_SYNTH[entry]
    lid = _lid(case)
    assert read(voice, case["dirty"], lid) == read(voice, case["clean"], lid)


@pytest.mark.parametrize("entry", TTS_ENTRIES)
@pytest.mark.parametrize("case", _cases(synth=True), ids=_id)
def test_piper_plus_reads_dirty_like_clean(tts, entry, case):
    read = TTS_ENTRIES[entry]
    assert read(tts, case["dirty"]) == read(tts, case["clean"])


def test_only_controls_read_as_empty_text(voice):
    assert voice.phonemize(ONLY_CONTROLS) == []
    assert _stream_raw(voice, ONLY_CONTROLS, None) == []


def test_piper_plus_reads_only_controls_as_empty_text(tts):
    # The word cases cannot show PiperPlus.synthesize stripping: its G2P
    # strips again. A text of control characters only gave BOS/EOS audio.
    assert len(tts.synthesize(ONLY_CONTROLS).audio) == 0
    assert list(tts.synthesize_stream(ONLY_CONTROLS)) == []


def test_short_text_padding_counts_stripped_text(voice):
    # "hola" gets the short-text padding (Strategy C). Twenty NULs made the
    # raw text longer than the short-text limit, so the padding was lost.
    dirty = "ho" + "\u0000" * 20 + "la"
    lid = MODEL_LANGUAGES["es"]
    assert _stream_raw(voice, dirty, lid) == _stream_raw(voice, "hola", lid)
