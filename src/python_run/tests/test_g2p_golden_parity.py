"""Golden parity of the piper-plus runtime G2P with the training-side Python.

``tests/fixtures/g2p/phoneme_test_cases_golden.json`` holds the phonemes the
training-side ``piper_plus_g2p.MultilingualPhonemizer`` produces with the case
language as the Latin default. The runtime package (PyPI ``piper-plus``) has
its own phonemizers under ``piper_plus.phonemize``. ``PiperVoice.phonemize``
and ``PiperVoice.synthesize*`` split the text into sentences and phonemize each
one with the phonemizer from ``PiperVoice._phonemize_one_factory(language_id)``;
this test compares that phonemizer's output with the golden, so it is the
phoneme sequence that reaches the model for a one-sentence input. Sentence
splitting is a separate cross-runtime contract (text-splitter-contract.toml)
and is not compared here. No ONNX model is needed: the voice is built from a
config only.

Cases known to differ are listed in ``tests/fixtures/g2p/known_divergences.json``
for the ``python_run`` runtime. A difference that is not listed fails, and so
does a listed case that now matches, so the list shrinks as the linked issues
are fixed. English words that must never phonemize to nothing are listed in
``tests/fixtures/g2p/english_no_drop_words.json`` and follow the same rule.
Every failure is collected and reported at once, and a run that compares no
case fails.

Multi-codepoint phonemes (rr, tʃ, tone3) are one PUA character here
(``pua.json``) and spelled out in the golden; that representation difference is
not a divergence. Only the golden side is mapped, so output that forgets the
PUA encoding still fails. Unlike the C++ and Rust tests, Chinese punctuation
and word boundaries are compared as well: this runtime drops CJK punctuation
like the training side does.

Japanese needs the OpenJTalk dictionary and Korean is absent from the golden
(and from the trained models), so both are left out. Nothing else is skipped:
a missing fixture or phonemizer dependency fails the test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from piper_plus.config import PhonemeType, PiperConfig
from piper_plus.voice import PiperVoice


RUNTIME = "python_run"
LANGUAGES = ("en", "es", "fr", "pt", "sv", "zh")

# Language ids of the multilingual dataset
# (piper_train.tools.prepare_multilingual_dataset.LANGUAGE_ID_MAP). Swedish is
# included so a Swedish request reaches the phonemizer.
LANGUAGE_ID_MAP = {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5, "sv": 6}

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "g2p"
GOLDEN = FIXTURE_DIR / "phoneme_test_cases_golden.json"
DIVERGENCES = FIXTURE_DIR / "known_divergences.json"
NO_DROP = FIXTURE_DIR / "english_no_drop_words.json"
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"

NOT_SPOKEN = frozenset({" ", ".", ",", "!", "?", ";", ":", "'", '"', "-"})

pytestmark = pytest.mark.unit


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _lists_runtime(entry: dict) -> bool:
    return RUNTIME in (entry.get("runtimes") or [])


def _pua_table() -> dict[str, str]:
    return {
        e["token"]: chr(int(e["codepoint"], 16))
        for e in _load_json(PUA_JSON)["entries"]
    }


def _split_phonemes(s: str) -> list[str]:
    """Tokens are joined with one space; a word boundary " " is three spaces."""
    tokens: list[str] = []
    if not s:
        return tokens
    empty_parts = 0
    for part in s.split(" "):
        if part:
            empty_parts = 0
            tokens.append(part)
        else:
            empty_parts += 1
            if empty_parts == 2:
                empty_parts = 0
                tokens.append(" ")
    return tokens


@pytest.fixture(scope="module")
def voice() -> PiperVoice:
    config = PiperConfig(
        num_symbols=256,
        num_speakers=1,
        sample_rate=22050,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={"_": [0], "^": [1], "$": [2]},
        phoneme_type=PhonemeType.MULTILINGUAL,
        num_languages=len(LANGUAGE_ID_MAP),
        language_id_map=LANGUAGE_ID_MAP,
    )
    # Phonemization never touches the ONNX session.
    return PiperVoice(session=None, config=config)  # type: ignore[arg-type]


def _phonemize(voice: PiperVoice, text: str, lang: str) -> list[str]:
    return voice._phonemize_one_factory(LANGUAGE_ID_MAP[lang])(text)


def test_language_id_reaches_the_phonemizer(voice: PiperVoice) -> None:
    """A Latin-script language id reads Latin text with that language's rules."""
    text = "¿Cómo estás?"
    spanish = voice.phonemize(text, language_id=LANGUAGE_ID_MAP["es"])
    assert spanish == [_phonemize(voice, text, "es")]
    assert spanish != voice.phonemize(text)
    assert "?" in spanish[0]


@pytest.mark.parametrize("language_id", [None, LANGUAGE_ID_MAP["zh"], 99])
def test_other_language_ids_read_latin_text_as_english(
    voice: PiperVoice, language_id: int | None
) -> None:
    text = "Hello world"
    assert voice.phonemize(text, language_id=language_id) == [
        _phonemize(voice, text, "en")
    ]


def test_synthesize_stream_raw_phonemizes_with_language_id() -> None:
    from unittest.mock import MagicMock

    voice = MagicMock(spec=PiperVoice)
    voice._split_sentences = MagicMock(return_value=["hola"])
    voice._phonemize_one_factory = MagicMock(return_value=lambda s: ["a"])
    voice.config = MagicMock(sample_rate=22050)
    voice._stream_phonemes_to_audio = lambda phonemes, *a, **kw: (b"" for _ in phonemes)

    list(PiperVoice.synthesize_stream_raw(voice, "hola", language_id=3))

    voice._phonemize_one_factory.assert_called_once_with(3)


def test_matches_python_golden_except_listed_divergences(voice: PiperVoice) -> None:
    pua = _pua_table()
    registry = _load_json(DIVERGENCES)
    golden = _load_json(GOLDEN)
    known = {
        (e["language"], e["input"])
        for e in registry["divergences"]
        if _lists_runtime(e)
    }

    verified = 0
    known_count = 0
    failures: list[str] = []
    for case in golden["test_cases"]:
        lang = case["language"]
        text = case["input"]
        if lang not in LANGUAGES:
            continue
        golden_phonemes = case["expected_phonemes"]
        expected = [pua.get(t, t) for t in _split_phonemes(golden_phonemes)]
        try:
            actual: list[str] | None = _phonemize(voice, text, lang)
            error = ""
        except Exception as exc:  # noqa: BLE001 - reported as a mismatch
            actual = None
            error = f"(phonemize failed: {type(exc).__name__}: {exc})"
        matches = actual == expected
        verified += 1

        label = f"[{lang}] {text!r}"
        listed = (lang, text) in known
        if matches and listed:
            failures.append(
                f"{label} now matches; remove it from known_divergences.json"
            )
        elif not matches and listed:
            known_count += 1
        elif not matches:
            got = error or " ".join(actual or [])
            failures.append(
                f"{label}\n  expected: {golden_phonemes}\n  actual:   {got}"
            )

    assert verified > 0, "no golden case compared"
    assert not failures, (
        f"{len(failures)} failure(s), {known_count} known, {verified} cases:\n"
        + "\n".join(failures)
    )


def test_english_words_are_not_dropped(voice: PiperVoice) -> None:
    word_list = _load_json(NO_DROP)
    known_drops = {e["word"] for e in word_list["known_drops"] if _lists_runtime(e)}

    checked = 0
    failures: list[str] = []
    for word in word_list["words"]:
        try:
            tokens = _phonemize(voice, word, "en")
            got = repr(" ".join(tokens))
        except Exception as exc:  # noqa: BLE001 - a crash is a drop
            tokens = []
            got = f"(phonemize failed: {type(exc).__name__}: {exc})"
        spoken = any(t not in NOT_SPOKEN for t in tokens)
        checked += 1
        listed = word in known_drops
        if spoken and listed:
            failures.append(f"{word!r} is now spoken; remove it from known_drops")
        elif not spoken and not listed:
            failures.append(f"{word!r} produced no phoneme: {got}")

    assert checked > 0, "english_no_drop_words.json has no words"
    assert not failures, "\n".join(failures)


def test_mapping_twice_keeps_the_reverse_map() -> None:
    """``MultilingualPhonemizer`` maps tokens the language phonemizer already
    mapped; that must not overwrite the PUA reverse map (``ɛ̃`` -> itself)."""
    from piper_plus.phonemize.token_mapper import CHAR2TOKEN, map_sequence

    once = map_sequence(["ɛ̃"])
    assert map_sequence(once) == once
    assert CHAR2TOKEN[once[0]] == "ɛ̃"
