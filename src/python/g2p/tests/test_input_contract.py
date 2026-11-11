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
from tests.conftest import _has_g2p_en, _has_g2pk2, _has_pyopenjtalk, _has_pypinyin

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
ONLY_CONTROLS = next(
    c["input"] for c in CASES["strip_cases"] if c["name"] == "only_controls"
)


# Optional backends, checked the same way as the per-language test files.
BACKENDS = {
    "ja": _has_pyopenjtalk,
    "en": _has_g2p_en,
    "zh": _has_pypinyin,
    "ko": _has_g2pk2,
}


def _phonemizers(language: str) -> list[Phonemizer]:
    """Every phonemizer to test for *language*; skip when a backend is missing."""
    needs = MULTILINGUAL[0] if language == "multilingual" else [language]
    missing = [lang for lang in needs if not BACKENDS.get(lang, lambda: True)()]
    if missing:
        pytest.skip(f"optional backend missing for {missing}")
    if language == "multilingual":
        return [MultilingualPhonemizer(langs) for langs in MULTILINGUAL]
    return [get_phonemizer(language)]


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
        read = getattr(phonemizer, method)
        assert read(case["dirty"]) == read(case["clean"])


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_only_controls_give_empty(language, method):
    empty = {"phonemize": [], "phonemize_with_prosody": ([], [])}[method]
    for phonemizer in _phonemizers(language):
        assert getattr(phonemizer, method)(ONLY_CONTROLS) == empty


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_non_str_is_rejected(language, method):
    for phonemizer in _phonemizers(language):
        with pytest.raises(TypeError):
            getattr(phonemizer, method)(123)


# The entry points that had the length limit before stripping was added to
# every language. Stripping adds no limit: PiperPlus.synthesize, infer_onnx
# and /api/phoneme-timing pass the whole text, and a limit would reject texts
# that read today.
LIMITED = (
    {("ja", m) for m in METHODS} | {("en", m) for m in METHODS} | {("sv", "phonemize")}
)


@pytest.mark.parametrize(("language", "method"), sorted(LIMITED), ids=str)
def test_too_long_is_rejected_where_it_was(language, method):
    too_long = "x" * (Phonemizer.MAX_INPUT_LENGTH + 1)
    for phonemizer in _phonemizers(language):
        with pytest.raises(ValueError, match="too long"):
            getattr(phonemizer, method)(too_long)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_stripping_adds_no_length_limit(language, method):
    if (language, method) in LIMITED:
        pytest.skip("limited before stripping was added")
    if language == "multilingual":
        # Latin text to es, which has no limit (en, in the other set-up, has one).
        phonemizers = [p for p in _phonemizers(language) if "en" not in p.languages]
        text = "hola " * 2001
    else:
        phonemizers = _phonemizers(language)
        word = next(
            c["clean"] for c in CASES["word_cases"] if c["language"] == language
        )
        text = f"{word} " * (Phonemizer.MAX_INPUT_LENGTH // len(word) + 1)
    assert len(text) > Phonemizer.MAX_INPUT_LENGTH
    for phonemizer in phonemizers:
        getattr(phonemizer, method)(text)  # does not raise


def test_zh_embedded_english_is_sanitized():
    (zh,) = _phonemizers("zh")
    assert zh.phonemize_embedded_english("G\u0000PS") == (
        zh.phonemize_embedded_english("GPS")
    )


@pytest.mark.parametrize("method", METHODS)
def test_ja_custom_dict_sees_sanitized_text(method):
    _phonemizers("ja")  # skip without pyopenjtalk
    from piper_plus_g2p.japanese import JapanesePhonemizer  # noqa: PLC0415

    words = CustomDictionary(load_defaults=False)
    words.add_word("ABC", "ネコ")
    ja = JapanesePhonemizer(custom_dict=words)
    # The dictionary is applied after stripping, so it matches "ABC".
    assert getattr(ja, method)("A\u0000BC") == getattr(ja, method)("ネコ")
