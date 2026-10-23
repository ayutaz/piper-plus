"""Tests for the Swedish runtime phonemizer (``piper_plus.phonemize.swedish``).

Issue #830: the runtime package had no Swedish phonemizer, so a Swedish
request was read by the English G2P. The runtime now carries a port of the
training-side rules (``piper_plus_g2p.swedish``), like French / Spanish /
Portuguese, and these tests pin the two together.

The two sides differ in their final wrapping only:

* Training side ``phonemize_swedish`` returns the bare IPA token list
  (no BOS/EOS, no PUA mapping).
* Runtime side ``phonemize_swedish`` wraps the same tokens with
  ``["^"] + ... + ["$"]`` and runs ``map_sequence`` (PUA assignment).

The parity tests compare the runtime's pre-wrap output
(``_phonemize_swedish_raw``) with PUA codepoints reverse-mapped via
``CHAR2TOKEN``, so only the G2P rules are compared.

The file also checks that every language the runtime multilingual
phonemizer can hand to ``_get_phonemize_func`` has a phonemizer, and that
``PiperVoice`` reads Swedish text with the Swedish rules when a model's
``language_id_map`` has ``sv``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus.config import PhonemeType, PiperConfig
from piper_plus.phonemize.multilingual import (
    _LATIN_SEGMENT_LANGUAGES,
    MultilingualPhonemizer,
    UnicodeLanguageDetector,
    _get_phonemize_func,
    _segment_text_multilingual,
)
from piper_plus.phonemize.swedish import (
    _phonemize_swedish_raw as runtime_phonemize_swedish_raw,
    phonemize_swedish as runtime_phonemize_swedish,
)
from piper_plus.phonemize.token_mapper import CHAR2TOKEN, map_sequence
from piper_plus.voice import PiperVoice
from piper_plus_g2p.swedish import SwedishPhonemizer


pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "g2p"
SV_GOLDEN = FIXTURE_DIR / "sv_golden.json"
GOLDEN = FIXTURE_DIR / "phoneme_test_cases_golden.json"
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"

# Language ids of the multilingual dataset
# (piper_train.tools.prepare_multilingual_dataset.LANGUAGE_ID_MAP; the runtime
# package does not depend on piper_train, so the map is spelled out here as in
# test_g2p_golden_parity.py).
LANGUAGE_ID_MAP = {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5, "sv": 6}
# The released 6-language models have no Swedish id.
SIX_LANG_ID_MAP = {k: v for k, v in LANGUAGE_ID_MAP.items() if k != "sv"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_ipa_tokens(text: str) -> list[str]:
    """Runtime IPA tokens with PUA codepoints reversed (training-side form)."""
    return [CHAR2TOKEN.get(tok, tok) for tok in runtime_phonemize_swedish_raw(text)]


def _sv_golden_cases() -> list[dict]:
    return _load_json(SV_GOLDEN)["cases"]


def _multilingual_golden_sv_cases() -> list[dict]:
    return [c for c in _load_json(GOLDEN)["test_cases"] if c["language"] == "sv"]


def _split_phonemes(s: str) -> list[str]:
    """Tokens are joined with one space; a word boundary " " is three spaces."""
    tokens: list[str] = []
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


def _pua_table() -> dict[str, str]:
    return {
        e["token"]: chr(int(e["codepoint"], 16))
        for e in _load_json(PUA_JSON)["entries"]
    }


def _voice(language_id_map: dict[str, int]) -> PiperVoice:
    config = PiperConfig(
        num_symbols=256,
        num_speakers=1,
        sample_rate=22050,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={"_": [0], "^": [1], "$": [2]},
        phoneme_type=PhonemeType.MULTILINGUAL,
        num_languages=len(language_id_map),
        language_id_map=language_id_map,
    )
    # Phonemization never touches the ONNX session.
    return PiperVoice(session=None, config=config)  # type: ignore[arg-type]


# Hand-written cases that exercise each rule family of the training side, on
# top of every case in sv_golden.json and the multilingual golden.
EXTRA_PARITY_CASES: list[str] = [
    # Soft / hard k and g, with stem heuristics
    "kille kissa kiosk",
    "leker söker tänker",
    "köpa kära göra gäst",
    "flyger ligger väger dag",
    "agera reagera arrangerade",
    # sk / sj / stj / skj / tj / kj / ch / sch / sh / ph / th
    "skön skola skjorta stjärna",
    "tjugo kjol choklad schack show",
    "kristus och människa marskalk",
    "photo theater",
    # gn / ng / nk / ck / initial gj lj dj hj
    "gnaga regn ring tänka backe",
    "gjorde ljus djur hjälp",
    # c / x / q / w / z
    "cirkus cykel café",
    "sex quiz wasa zebra",
    # Vowel quantity: geminate, cluster, r + C, final m, O_LONG_AS_OO
    "mat matt hat hatt",
    "barn bord kort",
    "hem rum dröm ström",
    "son mor bror god jord ko tro",
    # Function words (no stress, short vowels)
    "jag och du är inte här",
    # Loanword suffixes
    "station mission version",
    "garage bagage mage hage",
    "frisör museum akvarium",
    # Stress-attracting suffixes and unstressed prefixes
    "universitet bageri studera",
    "betala förstå gestalt",
    "polis musik regional",
    # Retroflex assimilation and cascades
    "bord barn fors karl",
    "först kvarts norrland",
    # Unstressed suffix shapes
    "flickorna pojkarna läsande",
    # Upper case, NFC / NFD input, accents
    "STOCKHOLM Göteborg",
    "Malmö",
    "idé café allé",
    # Punctuation and spacing
    "Hej! Hur mår du? Bra, tack.",
    "ja;nej:kanske...",
    "",
    "   ",
    "123 abc",
]


def _parity_texts() -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for text in (
        [c["text"] for c in _sv_golden_cases()]
        + [c["input"] for c in _multilingual_golden_sv_cases()]
        + EXTRA_PARITY_CASES
    ):
        if text not in seen:
            seen.add(text)
            texts.append(text)
    return texts


class TestSwedishTrainingParity:
    """The runtime port must agree with ``piper_plus_g2p.swedish`` exactly."""

    @pytest.mark.parametrize("text", _parity_texts())
    def test_runtime_matches_training(self, text: str) -> None:
        training = SwedishPhonemizer().phonemize_with_prosody(text)[0]
        assert _runtime_ipa_tokens(text) == training

    @pytest.mark.parametrize(
        "case", _sv_golden_cases(), ids=lambda c: c["text"] or "<empty>"
    )
    def test_runtime_matches_sv_golden_fixture(self, case: dict) -> None:
        assert _runtime_ipa_tokens(case["text"]) == case["expected_phonemes"]

    def test_fixtures_are_not_empty(self) -> None:
        assert len(_sv_golden_cases()) > 0
        assert len(_multilingual_golden_sv_cases()) == 51


class TestSwedishRuntimeWrapping:
    def test_runtime_wraps_with_bos_eos(self) -> None:
        tokens = runtime_phonemize_swedish("hej")
        assert tokens[0] == "^"
        assert tokens[-1] == "$"

    def test_runtime_inner_tokens_are_pua_mapped(self) -> None:
        tokens = runtime_phonemize_swedish("God morgon Sverige.")
        training = SwedishPhonemizer().phonemize_with_prosody("God morgon Sverige.")[0]
        assert tokens[1:-1] == map_sequence(training)
        # Long vowels are multi-codepoint tokens and must be PUA characters.
        assert all(len(tok) == 1 for tok in tokens)

    def test_known_words(self) -> None:
        assert _runtime_ipa_tokens("sjö") == ["ˈ", "ɧ", "øː"]
        # r + C: the vowel stays long and r merges into the retroflex.
        assert _runtime_ipa_tokens("barn") == ["ˈ", "b", "ɑː", "ɳ"]


class TestPhonemizeFuncCoverage:
    """Every language the runtime can segment into has a phonemizer.

    A language that the segmenter can emit but ``_get_phonemize_func`` does
    not know raises ``ValueError`` in the middle of synthesis (Issue #830:
    ``sv`` was in ``_LATIN_SEGMENT_LANGUAGES`` and in the Swedish per-word LID
    but had no phonemizer).
    """

    @staticmethod
    def _voice_languages() -> set[str]:
        langs: set[str] = set()
        for id_map in (LANGUAGE_ID_MAP, SIX_LANG_ID_MAP):
            langs.update(_voice(id_map)._multilingual_languages())
        return langs

    @staticmethod
    def _detector_languages(languages: list[str]) -> set[str]:
        """Languages the segmenter returns for text in every script."""
        text = "こんにちは 漢字 한국어 Hello och så Ａｂｃ ｱｲｳ 123。"
        found: set[str] = set()
        for default in [lang for lang in languages if lang in _LATIN_SEGMENT_LANGUAGES]:
            det = UnicodeLanguageDetector(languages, default_latin_language=default)
            found.update(lang for lang, _ in _segment_text_multilingual(text, det))
            # Text with no script characters falls back to the default.
            found.update(lang for lang, _ in _segment_text_multilingual("123", det))
        return found

    def _all_reachable_languages(self) -> set[str]:
        voice_langs = self._voice_languages()
        return (
            set(_LATIN_SEGMENT_LANGUAGES)
            | voice_langs
            | self._detector_languages(sorted(voice_langs))
            | set(LANGUAGE_ID_MAP)
        )

    def test_reachable_set_includes_swedish(self) -> None:
        langs = self._all_reachable_languages()
        assert {"sv", "pt-PT", "en", "ja", "zh"} <= langs

    def test_every_reachable_language_has_a_phonemizer(self) -> None:
        missing = []
        for lang in sorted(self._all_reachable_languages()):
            try:
                func = _get_phonemize_func(lang)
            except ValueError as exc:
                missing.append(f"{lang}: {exc}")
                continue
            assert callable(func), lang
        assert not missing, missing

    def test_swedish_dispatches_to_swedish_phonemizer(self) -> None:
        assert _get_phonemize_func("sv") is runtime_phonemize_swedish

    def test_swedish_function_word_in_english_text_does_not_raise(self) -> None:
        mp = MultilingualPhonemizer(
            languages=["ja", "en", "zh", "es", "fr", "pt", "sv"],
            default_latin_language="en",
        )
        tokens = mp.phonemize("Hello och goodbye")
        assert tokens


class TestPiperVoiceSwedish:
    def test_voice_with_sv_id_offers_swedish(self) -> None:
        assert "sv" in _voice(LANGUAGE_ID_MAP)._multilingual_languages()

    def test_voice_without_sv_id_keeps_six_languages(self) -> None:
        # Released 6-language models must not start routing Latin words to the
        # Swedish rules (the per-word LID turns on once sv is a language).
        assert _voice(SIX_LANG_ID_MAP)._multilingual_languages() == [
            "ja",
            "en",
            "zh",
            "es",
            "fr",
            "pt",
        ]

    def test_swedish_language_id_uses_swedish_rules(self) -> None:
        voice = _voice(LANGUAGE_ID_MAP)
        text = "God morgon Sverige."
        got = voice.phonemize(text, language_id=LANGUAGE_ID_MAP["sv"])
        expected = runtime_phonemize_swedish(text)[1:-1]
        assert got == [expected]
        assert got != voice.phonemize(text, language_id=LANGUAGE_ID_MAP["en"])

    @pytest.mark.parametrize(
        "case", _multilingual_golden_sv_cases(), ids=lambda c: c["input"]
    )
    def test_voice_matches_multilingual_golden(self, case: dict) -> None:
        """Every sv case of phoneme_test_cases_golden.json, via PiperVoice."""
        pua = _pua_table()
        expected = [pua.get(t, t) for t in _split_phonemes(case["expected_phonemes"])]
        voice = _voice(LANGUAGE_ID_MAP)
        got = voice._phonemize_one_factory(LANGUAGE_ID_MAP["sv"])(case["input"])
        assert got == expected
