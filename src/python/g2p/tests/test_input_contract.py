"""Every language strips control characters before phonemizing.

Contract: docs/spec/input-sanitize-contract.toml (runtime ``python-g2p``).
Cases: tests/fixtures/g2p/input_sanitize_cases.json, read by every runtime.

Regression focus: #934 (2026-11) added C1 stripping to ``_sanitize_input``,
but only ja / en (and sv's ``phonemize``) called it. zh / ko / es / fr / pt,
sv's ``phonemize_with_prosody`` and ``MultilingualPhonemizer`` passed
control characters through: a NUL inside "hola" split the word in two.
The parameters come from the registry, so a new language without a word in
the fixture fails here instead of slipping through untested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus_g2p import available_languages, get_phonemizer
from piper_plus_g2p.base import Phonemizer
from piper_plus_g2p.custom_dict import CustomDictionary
from piper_plus_g2p.multilingual import MultilingualPhonemizer

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "g2p"
    / "input_sanitize_cases.json"
)
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
# Two set-ups: with en, Latin text goes to the en phonemizer (which already
# stripped); without en, it goes to es, which did not.
MULTILINGUAL = (["ja", "en", "zh", "es", "fr", "pt"], ["es", "zh"])
METHODS = ("phonemize", "phonemize_with_prosody")
LANGUAGES = [*available_languages(), "multilingual"]
ONLY_CONTROLS = "\u0000\u0001\u007f\u0085"


def _phonemizers(language: str) -> list[Phonemizer]:
    if language == "multilingual":
        return [MultilingualPhonemizer(langs) for langs in MULTILINGUAL]
    return [get_phonemizer(language)]


def _call(phonemizer: Phonemizer, method: str, text):
    """Run one entry point; skip when an optional backend is not installed."""
    try:
        return getattr(phonemizer, method)(text)
    except (ImportError, LookupError) as exc:  # g2p_en / g2pk2 / NLTK data
        pytest.skip(f"optional dependency missing: {exc}")


@pytest.mark.parametrize("case", CASES["strip_cases"], ids=lambda c: c["name"])
def test_strip_cases(case):
    assert get_phonemizer("es")._sanitize_input(case["input"]) == case["expected"]


@pytest.mark.parametrize("language", available_languages())
def test_every_registered_language_has_word_case(language):
    have = {c["language"] for c in CASES["word_cases"]}
    assert language in have, (
        f"add a '{language}' word to word_cases in {FIXTURE.name} "
        "(and to languages in docs/spec/input-sanitize-contract.toml)"
    )


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize(
    "case",
    CASES["word_cases"],
    ids=lambda c: f"{c['language']}-{c['clean']}-{c['control']}",
)
def test_dirty_word_reads_like_clean(case, method):
    if case["language"] not in LANGUAGES:
        pytest.skip(f"{case['language']} is not registered here")
    for phonemizer in _phonemizers(case["language"]):
        assert _call(phonemizer, method, case["dirty"]) == _call(
            phonemizer, method, case["clean"]
        )


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_only_controls_give_empty(language, method):
    empty = {"phonemize": [], "phonemize_with_prosody": ([], [])}[method]
    for phonemizer in _phonemizers(language):
        assert _call(phonemizer, method, ONLY_CONTROLS) == empty


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_non_str_is_rejected(language, method):
    for phonemizer in _phonemizers(language):
        with pytest.raises(TypeError):
            getattr(phonemizer, method)(123)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_too_long_is_rejected(language, method):
    too_long = "x" * (Phonemizer.MAX_INPUT_LENGTH + 1)
    for phonemizer in _phonemizers(language):
        with pytest.raises(ValueError, match="too long"):
            getattr(phonemizer, method)(too_long)


def test_zh_embedded_english_is_sanitized():
    zh = get_phonemizer("zh")
    assert zh.phonemize_embedded_english("G\u0000PS") == (
        zh.phonemize_embedded_english("GPS")
    )


@pytest.mark.parametrize("method", METHODS)
def test_ja_custom_dict_sees_sanitized_text(method):
    from piper_plus_g2p.japanese import JapanesePhonemizer  # noqa: PLC0415

    words = CustomDictionary(load_defaults=False)
    words.add_word("ABC", "ネコ")
    ja = JapanesePhonemizer(custom_dict=words)
    # The dictionary is applied after stripping, so it matches "ABC".
    assert getattr(ja, method)("A\u0000BC") == getattr(ja, method)("ネコ")
