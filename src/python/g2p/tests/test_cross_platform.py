"""Cross-platform G2P consistency tests.

Validates Python piper-g2p output against the shared fixture
``tests/fixtures/g2p/phoneme_test_cases.json``, which is the single
source of truth for Python, Rust, and JS runtimes.

Fixture-driven assertions ensure that all three platforms produce
identical (or structurally compatible) results for the same inputs.
"""

import json
from pathlib import Path

import pytest

from tests.conftest import requires_en, requires_ja, requires_ko, requires_zh

FIXTURE_PATH = (
    Path(__file__).parents[4] / "tests" / "fixtures" / "g2p" / "phoneme_test_cases.json"
)

# Question-type EOS markers emitted by the Japanese phonemizer
_JA_QUESTION_MARKERS = frozenset({"?", "?!", "?.", "?~"})

# Tone tokens emitted by the Chinese phonemizer
_ZH_TONE_TOKENS = frozenset({"tone1", "tone2", "tone3", "tone4", "tone5"})


@pytest.fixture(scope="module")
def fixtures():
    """Load the shared cross-platform phoneme test fixture."""
    assert FIXTURE_PATH.exists(), (
        f"Fixture file not found: {FIXTURE_PATH}\n"
        "Run from the repository root or check that "
        "tests/fixtures/g2p/phoneme_test_cases.json exists."
    )
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _cases_for_language(fixtures, lang):
    """Return test_cases entries matching *lang*."""
    return [c for c in fixtures["test_cases"] if c["language"] == lang]


# =====================================================================
# PUA mapping consistency
# =====================================================================


class TestPUAMapConsistency:
    """Verify PUA mapping table matches the fixture expectations."""

    def test_pua_map_count(self, fixtures):
        """FIXED_PUA_MAPPING entry count matches fixture pua_map_count."""
        from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING

        assert len(FIXED_PUA_MAPPING) == fixtures["pua_map_count"]

    def test_pua_spot_checks(self, fixtures):
        """PUA spot-check codepoints match fixture expectations."""
        from piper_plus_g2p.encode.pua import map_token

        for check in fixtures["pua_spot_checks"]:
            result = map_token(check["token"])
            expected_cp = int(check["codepoint"], 16)
            assert ord(result) == expected_cp, (
                f"PUA mismatch for {check['token']!r}: "
                f"got U+{ord(result):04X}, expected U+{expected_cp:04X} "
                f"({check['description']})"
            )


# =====================================================================
# Encode (BOS/EOS/padding) consistency
# =====================================================================


class TestEncodeConsistency:
    """Verify PiperEncoder BOS/EOS/padding insertion against fixture."""

    @pytest.fixture(autouse=True)
    def _setup_encoder(self):
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        self._id_map = get_phoneme_id_map("ja")
        self._encoder = PiperEncoder(self._id_map)

    def test_encode_bos_eos(self, fixtures):
        """Each encode_test_case has BOS at start and EOS at end."""
        bos_id = self._id_map["^"][0]
        eos_id = self._id_map["$"][0]

        for case in fixtures["encode_test_cases"]:
            ids = self._encoder.encode(case["tokens"])

            if case.get("expected_has_bos"):
                assert ids[0] == bos_id, (
                    f"Missing BOS for {case['description']}: "
                    f"first id={ids[0]}, expected {bos_id}"
                )
            if case.get("expected_has_eos"):
                assert ids[-1] == eos_id, (
                    f"Missing EOS for {case['description']}: "
                    f"last id={ids[-1]}, expected {eos_id}"
                )

    def test_encode_min_length(self, fixtures):
        """Encoded output length meets fixture expected_min_length."""
        for case in fixtures["encode_test_cases"]:
            ids = self._encoder.encode(case["tokens"])
            expected_min = case["expected_min_length"]
            assert len(ids) >= expected_min, (
                f"Encoded length {len(ids)} < {expected_min} for {case['description']}"
            )

    def test_encode_first_token(self, fixtures):
        """First token symbol matches fixture expected_first_token."""
        for case in fixtures["encode_test_cases"]:
            if "expected_first_token" not in case:
                continue
            ids = self._encoder.encode(case["tokens"])
            expected_symbol = case["expected_first_token"]
            expected_id = self._id_map[expected_symbol][0]
            assert ids[0] == expected_id, (
                f"First token mismatch for {case['description']}: "
                f"got id={ids[0]}, expected id={expected_id} "
                f"(symbol {expected_symbol!r})"
            )


# =====================================================================
# Language detection consistency
# =====================================================================


class TestDetectConsistency:
    """Verify UnicodeLanguageDetector results against fixture detect_test_cases."""

    def test_detect_cases(self, fixtures):
        """Language detection matches fixture expectations."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        # Build a detector with all languages referenced in the fixture
        all_langs = sorted(
            {c["expected_language"] for c in fixtures["detect_test_cases"]}
        )
        detector = UnicodeLanguageDetector(all_langs, default_latin_language="en")

        for case in fixtures["detect_test_cases"]:
            text = case["input"]
            expected_lang = case["expected_language"]
            context_has_kana = detector.has_kana(text)

            # Detect the dominant language by majority vote over
            # non-neutral characters, mirroring how the segmenter works.
            lang_votes: dict[str, int] = {}
            for ch in text:
                lang = detector.detect_char(ch, context_has_kana=context_has_kana)
                if lang is not None:
                    lang_votes[lang] = lang_votes.get(lang, 0) + 1

            detected = None if not lang_votes else max(lang_votes, key=lang_votes.get)

            assert detected == expected_lang, (
                f"Detection mismatch for {case['description']}: "
                f"got {detected!r}, expected {expected_lang!r} "
                f"(votes: {lang_votes})"
            )


# =====================================================================
# Per-language phonemize consistency
# =====================================================================


@requires_ja
class TestJAPhonemeFixtures:
    """Japanese phonemize results match fixture structural expectations."""

    def test_ja_token_count_min(self, fixtures):
        """JA phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ja")
        for case in _cases_for_language(fixtures, "ja"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"JA token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_ja_contains(self, fixtures):
        """JA phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ja")
        for case in _cases_for_language(fixtures, "ja"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"JA output missing {expected!r} for {case['input']!r}: {tokens}"
                )

    def test_ja_question_marker(self, fixtures):
        """JA question sentences produce an interrogative EOS marker."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ja")
        for case in _cases_for_language(fixtures, "ja"):
            if not case.get("expected_has_question_marker"):
                continue
            tokens = p.phonemize(case["input"])
            has_marker = bool(set(tokens) & _JA_QUESTION_MARKERS)
            assert has_marker, (
                f"JA output missing question marker for {case['input']!r}: {tokens}"
            )


@requires_en
class TestENPhonemeFixtures:
    """English phonemize results match fixture structural expectations."""

    def test_en_token_count_min(self, fixtures):
        """EN phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("en")
        for case in _cases_for_language(fixtures, "en"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"EN token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_en_contains(self, fixtures):
        """EN phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("en")
        for case in _cases_for_language(fixtures, "en"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"EN output missing {expected!r} for {case['input']!r}: {tokens}"
                )


@requires_zh
class TestZHPhonemeFixtures:
    """Chinese phonemize results match fixture structural expectations."""

    def test_zh_token_count_min(self, fixtures):
        """ZH phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("zh")
        for case in _cases_for_language(fixtures, "zh"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"ZH token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_zh_tone_markers(self, fixtures):
        """ZH phonemize output contains tone markers when expected."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("zh")
        for case in _cases_for_language(fixtures, "zh"):
            if not case.get("expected_contains_any_tone"):
                continue
            tokens = p.phonemize(case["input"])
            has_tone = bool(set(tokens) & _ZH_TONE_TOKENS)
            assert has_tone, (
                f"ZH output missing tone marker for {case['input']!r}: {tokens}"
            )


class TestESPhonemeFixtures:
    """Spanish phonemize results match fixture expectations
    (rule-based, deterministic)."""

    def test_es_exact_tokens(self, fixtures):
        """ES deterministic output matches fixture expected_tokens exactly."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("es")
        for case in _cases_for_language(fixtures, "es"):
            if "expected_tokens" not in case:
                continue
            tokens = p.phonemize(case["input"])
            assert tokens == case["expected_tokens"], (
                f"ES exact mismatch for {case['input']!r}: "
                f"got {tokens}, expected {case['expected_tokens']}"
            )

    def test_es_token_count_min(self, fixtures):
        """ES phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("es")
        for case in _cases_for_language(fixtures, "es"):
            if "expected_token_count_min" not in case:
                continue
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"ES token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_es_contains(self, fixtures):
        """ES phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("es")
        for case in _cases_for_language(fixtures, "es"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"ES output missing {expected!r} for {case['input']!r}: {tokens}"
                )


class TestFRPhonemeFixtures:
    """French phonemize results match fixture structural expectations."""

    def test_fr_token_count_min(self, fixtures):
        """FR phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("fr")
        for case in _cases_for_language(fixtures, "fr"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"FR token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_fr_contains(self, fixtures):
        """FR phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("fr")
        for case in _cases_for_language(fixtures, "fr"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"FR output missing {expected!r} for {case['input']!r}: {tokens}"
                )


class TestPTPhonemeFixtures:
    """Portuguese phonemize results match fixture structural expectations."""

    def test_pt_token_count_min(self, fixtures):
        """PT phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("pt")
        for case in _cases_for_language(fixtures, "pt"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"PT token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_pt_contains(self, fixtures):
        """PT phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("pt")
        for case in _cases_for_language(fixtures, "pt"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"PT output missing {expected!r} for {case['input']!r}: {tokens}"
                )


@requires_ko
class TestKOPhonemeFixtures:
    """Korean phonemize results match fixture structural expectations."""

    def test_ko_token_count_min(self, fixtures):
        """KO phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ko")
        for case in _cases_for_language(fixtures, "ko"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"KO token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_ko_contains(self, fixtures):
        """KO phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ko")
        for case in _cases_for_language(fixtures, "ko"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"KO output missing {expected!r} for {case['input']!r}: {tokens}"
                )


class TestSVPhonemeFixtures:
    """Swedish phonemize results match fixture structural expectations.

    Swedish uses a rule-based phonemizer with no external dependencies,
    so no skip decorator is needed.
    """

    def test_sv_token_count_min(self, fixtures):
        """SV phonemize output meets minimum token count."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("sv")
        for case in _cases_for_language(fixtures, "sv"):
            tokens = p.phonemize(case["input"])
            expected_min = case["expected_token_count_min"]
            assert len(tokens) >= expected_min, (
                f"SV token count {len(tokens)} < {expected_min} "
                f"for {case['input']!r}: {tokens}"
            )

    def test_sv_contains(self, fixtures):
        """SV phonemize output contains expected tokens."""
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("sv")
        for case in _cases_for_language(fixtures, "sv"):
            if "expected_contains" not in case:
                continue
            tokens = p.phonemize(case["input"])
            for expected in case["expected_contains"]:
                assert expected in tokens, (
                    f"SV output missing {expected!r} for {case['input']!r}: {tokens}"
                )


# =====================================================================
# Fixture schema sanity
# =====================================================================


class TestFixtureSanity:
    """Guard-rail checks on the fixture file itself."""

    def test_fixture_version(self, fixtures):
        """Fixture version is 1 (current schema)."""
        assert fixtures["version"] == 1

    def test_all_languages_covered(self, fixtures):
        """Fixture covers all 8 expected languages
        (ja/en/zh/ko/es/fr/pt/sv)."""
        test_langs = {c["language"] for c in fixtures["test_cases"]}
        detect_langs = {c["expected_language"] for c in fixtures["detect_test_cases"]}
        all_langs = test_langs | detect_langs
        # phoneme test_cases cover all 8 languages
        assert {"ja", "en", "zh", "ko", "es", "fr", "pt", "sv"} <= test_langs
        assert "ko" in detect_langs
        assert len(all_langs) == 8

    def test_pua_spot_check_count(self, fixtures):
        """Fixture contains at least 5 PUA spot checks."""
        assert len(fixtures["pua_spot_checks"]) >= 5

    def test_encode_test_case_count(self, fixtures):
        """Fixture contains at least 3 encode test cases."""
        assert len(fixtures["encode_test_cases"]) >= 3
