"""Tests for ZH-EN code-switching: embedded English -> Mandarin pinyin.

Covers Issue #384: English acronyms / loanwords inserted into Chinese
context should be pronounced as Mandarin pinyin, not as US English.
"""

import json
from pathlib import Path

import pytest

from tests.conftest import requires_en, requires_zh


@requires_zh
class TestEmbeddedEnglishUnit:
    """Unit tests for ChinesePhonemizer.phonemize_embedded_english()."""

    def test_acronym_gps(self):
        """Uppercase acronym hits the acronym table."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_embedded_english("GPS")
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        # Tone markers must be present (we go through pinyin -> IPA)
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) > 0, f"Expected tone markers in {tokens}"

    def test_acronym_case_insensitive(self):
        """Acronym lookup is case-insensitive (gps == GPS)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        upper, _ = p.phonemize_embedded_english("GPS")
        lower, _ = p.phonemize_embedded_english("gps")
        assert upper == lower

    def test_loanword_python_case_sensitive(self):
        """Case-sensitive loanword 'Python' uses the loanword entry."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, _ = p.phonemize_embedded_english("Python")
        assert len(tokens) > 0
        # Python -> [pai4, sen1] should produce two tone markers
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) == 2, f"Expected 2 tones for Python, got {tone_tokens}"

    def test_loanword_chatgpt(self):
        """Loanword 'ChatGPT' is a single entry (5 syllables)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, _ = p.phonemize_embedded_english("ChatGPT")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # ChatGPT entry has 5 pinyin syllables -> 5 tone markers
        assert len(tone_tokens) == 5, f"Expected 5 tones for ChatGPT, got {tone_tokens}"

    def test_letter_fallback_for_unknown(self):
        """Unknown tokens fall back to per-letter conversion."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        # "ZZ" is not in any dictionary -> letter fallback Z+Z
        tokens, _ = p.phonemize_embedded_english("ZZ")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # Z = ['zi4'] -> 1 syllable each, 2 total
        assert len(tone_tokens) == 2, f"Expected 2 tones for ZZ, got {tone_tokens}"

    def test_empty_input(self):
        """Empty string returns empty token list."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_embedded_english("")
        assert tokens == []
        assert prosody == []

    def test_punctuation_only(self):
        """Punctuation-only string is dropped."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, _ = p.phonemize_embedded_english("...")
        assert tokens == []

    def test_no_pua_in_output_clean_ipa(self):
        """Training-side output is clean IPA (no PUA codepoints)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, _ = p.phonemize_embedded_english("GPS")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_module_function_matches_class(self):
        """Module-level phonemize_embedded_english matches class method."""
        from piper_plus_g2p.chinese import (
            ChinesePhonemizer,
            phonemize_embedded_english,
        )

        cls_tokens, _ = ChinesePhonemizer().phonemize_embedded_english("API")
        fn_tokens, _ = phonemize_embedded_english("API")
        assert cls_tokens == fn_tokens


@requires_zh
class TestCustomDictionaryOverride:
    """Tests for the zh_en_loanword_dict_paths override mechanism."""

    def test_override_acronym(self, tmp_path: Path):
        """User dict overrides a default acronym entry."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        # Override GPS to a different (valid) pinyin sequence
        override = {
            "version": 1,
            "acronyms": {
                "GPS": ["jia1", "ba1", "guo2"],  # arbitrary 3-syllable override
            },
        }
        p_path = tmp_path / "override.json"
        p_path.write_text(json.dumps(override), encoding="utf-8")

        default = ChinesePhonemizer()
        custom = ChinesePhonemizer(zh_en_loanword_dict_paths=str(p_path))

        default_tokens, _ = default.phonemize_embedded_english("GPS")
        custom_tokens, _ = custom.phonemize_embedded_english("GPS")
        assert default_tokens != custom_tokens
        # Custom override has 3 syllables -> 3 tones
        custom_tones = [t for t in custom_tokens if t.startswith("tone")]
        assert len(custom_tones) == 3

    def test_override_new_acronym(self, tmp_path: Path):
        """User dict adds a brand-new acronym not in the default table."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        override = {
            "version": 1,
            "acronyms": {
                "MYORG": ["wo3", "men5", "gong1", "si1"],
            },
        }
        p_path = tmp_path / "myorg.json"
        p_path.write_text(json.dumps(override), encoding="utf-8")

        custom = ChinesePhonemizer(zh_en_loanword_dict_paths=str(p_path))
        tokens, _ = custom.phonemize_embedded_english("MYORG")
        tones = [t for t in tokens if t.startswith("tone")]
        assert len(tones) == 4

    def test_override_does_not_leak(self, tmp_path: Path):
        """Different ChinesePhonemizer instances have isolated overrides."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        override = {"version": 1, "acronyms": {"GPS": ["ai4"]}}
        p_path = tmp_path / "iso.json"
        p_path.write_text(json.dumps(override), encoding="utf-8")

        a = ChinesePhonemizer(zh_en_loanword_dict_paths=str(p_path))
        b = ChinesePhonemizer()  # no override

        a_tokens, _ = a.phonemize_embedded_english("GPS")
        b_tokens, _ = b.phonemize_embedded_english("GPS")
        # b uses the default (multi-syllable), a uses override (1 syllable)
        a_tones = [t for t in a_tokens if t.startswith("tone")]
        b_tones = [t for t in b_tokens if t.startswith("tone")]
        assert len(a_tones) == 1
        assert len(b_tones) > 1


@requires_zh
class TestMultilingualDispatch:
    """Tests for MultilingualPhonemizer dispatching to embedded English."""

    @requires_en
    def test_pure_english_uses_english_phonemizer(self):
        """Pure English text (no zh context) goes to EnglishPhonemizer."""
        from piper_plus_g2p.chinese import ChinesePhonemizer
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        zh_only = ChinesePhonemizer()

        ml_tokens, _ = p.phonemize_with_prosody("Hello world")
        zh_tokens, _ = zh_only.phonemize_embedded_english("Hello world")

        # The two paths should produce DIFFERENT outputs because pure English
        # is NOT routed through embedded-english (no adjacent zh segment)
        assert ml_tokens != zh_tokens
        # No tone markers from EN path
        assert not any(t.startswith("tone") for t in ml_tokens)

    def test_zh_en_zh_pattern_dispatched(self):
        """[zh, en, zh] pattern: en segment is dispatched to embedded path."""
        from piper_plus_g2p.registry import get_phonemizer

        # Using only zh-en avoids requiring the EN dependency
        p = get_phonemizer("zh-en")
        # 让我用 ChatGPT 写代码 -- ChatGPT is between zh segments
        text = "让我用 ChatGPT 写代码"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        # Embedded English -> tone markers should be present in ChatGPT region
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # zh segments alone produce tones, plus ChatGPT (5) -> at least 5+
        assert len(tone_tokens) >= 5

    def test_zh_then_en_pattern_dispatched(self):
        """[zh, en] pattern (en at end): still dispatched."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        # 请打开 GPS  (issue example)
        text = "请打开 GPS"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        # GPS = 4 pinyin syllables, plus zh segment tones
        assert len(tone_tokens) >= 4

    def test_en_then_zh_pattern_dispatched(self):
        """[en, zh] pattern (en at start): still dispatched."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        # GPS 在哪里  (GPS 在哪里)
        text = "GPS 在哪里"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) >= 4

    def test_pure_zh_unaffected(self):
        """Pure Chinese text behaves unchanged (regression)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        zh_only = ChinesePhonemizer()

        ml_tokens, _ = p.phonemize_with_prosody("今天天气很好")
        zh_tokens, _ = zh_only.phonemize_with_prosody("今天天气很好")
        assert ml_tokens == zh_tokens

    @requires_en
    def test_pure_english_in_zh_en_uses_english(self):
        """Pure English (no zh segment present) does NOT use embedded path."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        # No Chinese context at all -> EnglishPhonemizer should be used
        tokens, _ = p.phonemize_with_prosody("Hello world")
        assert len(tokens) > 0
        # English phonemes should NOT include tone markers
        assert not any(t.startswith("tone") for t in tokens)


@requires_zh
class TestIssueExampleCases:
    """End-to-end tests for the three example sentences in Issue #384."""

    def test_issue_example_gps(self):
        """请打开 GPS -- expected pinyin-IPA path."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        tokens, prosody = p.phonemize_with_prosody("请打开 GPS")
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        # GPS adds 4 syllables -> 4 extra tone markers vs the zh-only path
        from piper_plus_g2p.chinese import ChinesePhonemizer

        zh_only_tokens, _ = ChinesePhonemizer().phonemize_with_prosody("请打开")
        zh_only_tones = sum(1 for t in zh_only_tokens if t.startswith("tone"))
        ml_tones = sum(1 for t in tokens if t.startswith("tone"))
        assert ml_tones - zh_only_tones == 4

    def test_issue_example_python(self):
        """我喜欢用 Python 写代码."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        text = "我喜欢用 Python 写代码"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        # Python -> [pai4, sen1] = 2 tones added
        from piper_plus_g2p.chinese import ChinesePhonemizer

        zh_only_tokens, _ = ChinesePhonemizer().phonemize_with_prosody(
            "我喜欢用 写代码"
        )
        zh_only_tones = sum(1 for t in zh_only_tokens if t.startswith("tone"))
        ml_tones = sum(1 for t in tokens if t.startswith("tone"))
        assert ml_tones - zh_only_tones == 2

    def test_issue_example_chatgpt(self):
        """让我用 ChatGPT 写代码."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        text = "让我用 ChatGPT 写代码"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        from piper_plus_g2p.chinese import ChinesePhonemizer

        zh_only_tokens, _ = ChinesePhonemizer().phonemize_with_prosody("让我用 写代码")
        zh_only_tones = sum(1 for t in zh_only_tokens if t.startswith("tone"))
        ml_tones = sum(1 for t in tokens if t.startswith("tone"))
        # ChatGPT -> 5 syllables
        assert ml_tones - zh_only_tones == 5


@requires_zh
class TestLookupPriority:
    """The 3-tier priority: case-sensitive loanwords > acronyms > letter_fallback."""

    def test_loanword_beats_acronym(self, tmp_path: Path):
        """A case-sensitive loanword entry takes priority over an uppercase acronym."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        # Default: GPS is a 4-syllable acronym. Override registers GPS as a
        # 2-syllable case-sensitive loanword. Loanword must win.
        override = {
            "version": 1,
            "loanwords": {"GPS": ["ka1", "la2"]},
        }
        path = tmp_path / "loanword_wins.json"
        path.write_text(json.dumps(override), encoding="utf-8")

        p = ChinesePhonemizer(zh_en_loanword_dict_paths=str(path))
        tokens, _ = p.phonemize_embedded_english("GPS")
        tones = [t for t in tokens if t.startswith("tone")]
        assert len(tones) == 2, (
            f"Loanword override should win (2 syllables), got {tones}"
        )

    def test_acronym_beats_letter_fallback(self, tmp_path: Path):
        """An acronym entry takes priority over per-letter fallback."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        # 'AB' is not in the default dictionary. Letter fallback would yield
        # A + B = 2 syllables. Override registers AB as a 1-syllable acronym;
        # the acronym must win.
        override = {
            "version": 1,
            "acronyms": {"AB": ["ma1"]},
        }
        path = tmp_path / "acronym_wins.json"
        path.write_text(json.dumps(override), encoding="utf-8")

        p = ChinesePhonemizer(zh_en_loanword_dict_paths=str(path))
        tokens, _ = p.phonemize_embedded_english("AB")
        tones = [t for t in tokens if t.startswith("tone")]
        assert len(tones) == 1, (
            f"Acronym should win over letter fallback (1 syllable), got {tones}"
        )

    def test_loanword_case_sensitivity(self):
        """'Python' (loanword) and 'PYTHON' (uppercase) take different paths."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        # 'Python' -> case-sensitive loanword (2 syllables: pai4, sen1)
        py_tokens, _ = p.phonemize_embedded_english("Python")
        py_tones = [t for t in py_tokens if t.startswith("tone")]
        assert len(py_tones) == 2

        # 'PYTHON' -> not a loanword (case-sensitive miss), not in acronyms,
        # falls through to letter_fallback. P,Y,T,H,O,N letters all map to
        # at least 1 syllable each (H = 2 syllables).
        upper_tokens, _ = p.phonemize_embedded_english("PYTHON")
        upper_tones = [t for t in upper_tokens if t.startswith("tone")]
        assert len(upper_tones) > len(py_tones), (
            f"PYTHON via letter_fallback should produce more tones than "
            f"Python via loanword. py={py_tones}, upper={upper_tones}"
        )


@requires_zh
class TestPunctuationHandling:
    """Punctuation around English tokens must not corrupt the lookup."""

    def test_trailing_punctuation_ignored(self):
        """'GPS', 'GPS,', 'GPS.', 'GPS!' all yield the same phonemes."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        bare, _ = p.phonemize_embedded_english("GPS")
        comma, _ = p.phonemize_embedded_english("GPS,")
        period, _ = p.phonemize_embedded_english("GPS.")
        bang, _ = p.phonemize_embedded_english("GPS!")
        assert bare == comma == period == bang

    def test_punctuation_in_multilingual_dispatch(self):
        """Trailing punctuation in dispatched segment doesn't change the path."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        a_tokens, _ = p.phonemize_with_prosody("请打开 GPS")
        b_tokens, _ = p.phonemize_with_prosody("请打开 GPS。")

        a_tones = sum(1 for t in a_tokens if t.startswith("tone"))
        b_tones = sum(1 for t in b_tokens if t.startswith("tone"))
        assert a_tones == b_tones, (
            f"Punctuation should not affect tone count: {a_tones} vs {b_tones}"
        )


@requires_zh
class TestMultipleEmbeddedSegments:
    """Multiple English tokens interleaved with Chinese -- all must be embedded."""

    def test_two_embedded_en_segments(self):
        """让我用 ChatGPT 和 Python 写代码 -- both EN tokens dispatched."""
        from piper_plus_g2p.chinese import ChinesePhonemizer
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        full_tokens, _ = p.phonemize_with_prosody("让我用 ChatGPT 和 Python 写代码")
        # Compare against pure ZH baseline (without the EN tokens)
        baseline_tokens, _ = ChinesePhonemizer().phonemize_with_prosody(
            "让我用 和 写代码"
        )

        full_tones = sum(1 for t in full_tokens if t.startswith("tone"))
        base_tones = sum(1 for t in baseline_tokens if t.startswith("tone"))
        # ChatGPT = 5 syllables, Python = 2 syllables -> +7 tones
        assert full_tones - base_tones == 7, (
            f"Expected +7 tones (ChatGPT=5 + Python=2), got {full_tones - base_tones}"
        )


@requires_zh
class TestUnknownTokenWithDigits:
    """Digits in unknown tokens are silently dropped (no fallback entry)."""

    def test_digits_dropped_in_letter_fallback(self):
        """'Z2Z9' yields the same phonemes as 'ZZ' (digits dropped)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        no_digit, _ = p.phonemize_embedded_english("ZZ")
        with_digits, _ = p.phonemize_embedded_english("Z2Z9")
        assert no_digit == with_digits, (
            f"Digits should be dropped: ZZ={no_digit}, Z2Z9={with_digits}"
        )

    def test_registered_acronym_with_digits(self):
        """An acronym pre-registered with digits (MP3) hits the table directly."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        # MP3 is in the default acronym table -> 4 pinyin syllables
        tokens, _ = p.phonemize_embedded_english("MP3")
        tones = [t for t in tokens if t.startswith("tone")]
        assert len(tones) == 4, f"MP3 acronym should be 4 syllables, got {tones}"


@requires_zh
class TestProsodyAlignment:
    """Prosody arrays must always match the phoneme array length."""

    def test_embedded_english_prosody_alignment(self):
        """Every supported input produces matching prosody and phoneme arrays."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        cases = [
            "GPS",
            "Python",
            "ChatGPT",
            "ZZ",
            "GPS,",
            "GPS.",
            "MP3",
            "Z2Z9",
            "AB CD",
        ]
        for text in cases:
            tokens, prosody = p.phonemize_embedded_english(text)
            assert len(tokens) == len(prosody), (
                f"Length mismatch for {text!r}: "
                f"{len(tokens)} tokens vs {len(prosody)} prosody"
            )

    def test_dispatch_prosody_alignment(self):
        """Multilingual dispatch path keeps prosody alignment for embedded EN."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        cases = [
            "请打开 GPS",
            "我喜欢用 Python 写代码",
            "让我用 ChatGPT 写代码",
            "让我用 ChatGPT 和 Python 写代码",
            "请打开 GPS, 然后呢",
            "GPS 在哪里",
            "今天天气很好",  # pure zh regression
        ]
        for text in cases:
            tokens, prosody = p.phonemize_with_prosody(text)
            assert len(tokens) == len(prosody), (
                f"Length mismatch for {text!r}: "
                f"{len(tokens)} tokens vs {len(prosody)} prosody"
            )


@requires_zh
class TestDataIntegrity:
    """Validate the bundled zh_en_loanword.json against the spec."""

    def _load_data(self):
        from piper_plus_g2p.chinese import _DEFAULT_LOANWORD_DATA_PATH

        with open(_DEFAULT_LOANWORD_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_minimum_acronyms(self):
        """Issue requires at least 50 acronyms."""
        data = self._load_data()
        assert len(data["acronyms"]) >= 50

    def test_minimum_loanwords(self):
        """Issue requires at least 30 loanwords."""
        data = self._load_data()
        assert len(data["loanwords"]) >= 30

    def test_letter_fallback_complete(self):
        """All 26 A-Z letters are covered in letter_fallback."""
        data = self._load_data()
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert ch in data["letter_fallback"], f"Missing letter {ch}"

    def test_all_pinyin_have_valid_tone(self):
        """Every pinyin syllable ends with a digit 1-5."""
        data = self._load_data()
        for section in ("acronyms", "loanwords", "letter_fallback"):
            for token, syllables in data[section].items():
                for syl in syllables:
                    assert syl, f"Empty syllable in {section}/{token}"
                    assert syl[-1].isdigit(), (
                        f"Syllable {syl!r} in {section}/{token} missing tone"
                    )
                    assert 1 <= int(syl[-1]) <= 5, (
                        f"Syllable {syl!r} in {section}/{token} has invalid tone"
                    )


@requires_zh
class TestSchemaValidation:
    """``_load_loanword_data`` validates the JSON schema and rejects malformed input."""

    def test_string_value_rejected(self, tmp_path: Path):
        """A string instead of list[str] for a loanword raises ValueError."""
        from piper_plus_g2p.chinese import _load_loanword_data

        bad = {"version": 1, "loanwords": {"GPS": "ji4-pi4"}}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=r"loanwords\.GPS"):
            _load_loanword_data(path)

    def test_non_string_inside_list_rejected(self, tmp_path: Path):
        """A non-string element inside the list raises ValueError."""
        from piper_plus_g2p.chinese import _load_loanword_data

        bad = {"version": 1, "acronyms": {"GPS": ["ji4", 123]}}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=r"acronyms\.GPS"):
            _load_loanword_data(path)

    def test_section_not_mapping_rejected(self, tmp_path: Path):
        """A section that is not a dict raises ValueError."""
        from piper_plus_g2p.chinese import _load_loanword_data

        bad = {"version": 1, "letter_fallback": ["A", "B"]}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=r"letter_fallback.*mapping"):
            _load_loanword_data(path)

    def test_top_level_not_mapping_rejected(self, tmp_path: Path):
        """A top-level JSON that is not an object raises ValueError.

        Covers the loader / ``scripts/check_loanword_consistency.py`` parity:
        both must reject malformed top-level shapes (list, primitive) with a
        clear ``ValueError`` rather than the bare ``AttributeError`` raised by
        ``data.get(...)`` on a non-dict.
        """
        from piper_plus_g2p.chinese import _load_loanword_data

        for bad in ([1, 2, 3], "not-a-mapping", 42, None):
            path = tmp_path / "bad.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with pytest.raises(ValueError, match=r"top-level JSON must be"):
                _load_loanword_data(path)

    def test_valid_json_accepted(self, tmp_path: Path):
        """A well-formed JSON loads without error."""
        from piper_plus_g2p.chinese import _load_loanword_data

        good = {
            "version": 1,
            "acronyms": {"AB": ["ma1"]},
            "loanwords": {"Foo": ["fu1"]},
            "letter_fallback": {"Q": ["kiu1"]},
        }
        path = tmp_path / "good.json"
        path.write_text(json.dumps(good), encoding="utf-8")
        data = _load_loanword_data(path)
        assert data["acronyms"]["AB"] == ["ma1"]
        assert data["loanwords"]["Foo"] == ["fu1"]

    def test_loader_accepts_schema_v2_future_fields(self, tmp_path: Path):
        """YELLOW-5 forward-compat: future ``schema_version: 2`` files with
        unknown top-level fields (e.g. ``metadata``, ``tone_overrides``) must
        load successfully — known sections are kept, unknown fields ignored.

        This is the Python-side counterpart of the Rust/Go/C#/WASM/C++
        ``Loader_AcceptsUnknownFieldsInSchemaV2`` tests; the loader must not
        require ``version`` either (so a future rename to ``schema_version``
        does not break clients).
        """
        from piper_plus_g2p.chinese import _load_loanword_data

        future = {
            "schema_version": 2,
            "metadata": {"experimental": True},
            "acronyms": {"GPS": ["ji4", "pi4", "ai1", "si4"]},
            "loanwords": {"Python": ["pai4", "se1"]},
            "letter_fallback": {"A": ["ei1"]},
            "tone_overrides": {"GPS": "high"},
        }
        path = tmp_path / "future_v2.json"
        path.write_text(json.dumps(future), encoding="utf-8")
        data = _load_loanword_data(path)
        # Known sections roundtrip exactly.
        assert data["acronyms"]["GPS"] == ["ji4", "pi4", "ai1", "si4"]
        assert data["loanwords"]["Python"] == ["pai4", "se1"]
        assert data["letter_fallback"]["A"] == ["ei1"]
        # Unknown top-level fields are silently dropped (not surfaced).
        assert "metadata" not in data
        assert "tone_overrides" not in data
        assert "schema_version" not in data


@requires_zh
class TestDispatchDefaultBehavior:
    """Python's MultilingualPhonemizer ZH-EN dispatch is always-on by design.

    Other runtimes (Rust, Go, C#, WASM, C++) expose ``set_zh_en_dispatch(bool)``
    as an opt-out, but Python intentionally has no toggle: it is the
    source-of-truth that defines the canonical loanword-path IPA output. If a
    future PR adds a Python opt-out, both tests below must be updated to also
    cover the disabled state.
    """

    def test_dispatch_always_on_by_default(self):
        """[zh, en] with `GPS` routes through the loanword path (default behavior)."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        # If dispatch were disabled, "GPS" would be passed to the en path and
        # would NOT produce tone markers. With dispatch ON it must.
        tokens, _ = p.phonemize_with_prosody("请打开 GPS")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) >= 4, (
            "Default dispatch behavior: GPS in zh context must produce "
            "Mandarin tone markers (4 syllables = 4 tones)"
        )

    def test_dispatch_no_optout_api_exposed(self):
        """``MultilingualPhonemizer`` intentionally has no dispatch toggle API.

        This pins the API surface so future PRs that add
        ``set_zh_en_dispatch`` / ``is_zh_en_dispatch_enabled`` know to also
        update the multi-runtime parity contract.
        """
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        assert not hasattr(MultilingualPhonemizer, "set_zh_en_dispatch"), (
            "Python is source-of-truth; dispatch is always-on by design. If "
            "you are adding this method, also extend the parity contract in "
            "docs/spec/zh-en-loanword-runtime-rollout.md and update this test."
        )
        assert not hasattr(MultilingualPhonemizer, "is_zh_en_dispatch_enabled"), (
            "Python is source-of-truth; dispatch is always-on by design."
        )


@requires_zh
class TestFixtureMatrixConsumer:
    """Cross-runtime fixture matrix consumer (Python source-of-truth side).

    ``tests/fixtures/g2p/zh_en_loanword_matrix.json`` is mirrored into each
    runtime's test tree and locks the per-input token-count contract. Without
    a Python consumer, the fixture risks rotting (no one ever loaded it). This
    class is the canonical reference: the Python implementation must produce
    the exact ``expected_token_count`` for every concrete-input case.
    """

    def _load_matrix(self) -> dict:
        repo_root = Path(__file__).resolve().parents[4]
        matrix_path = (
            repo_root / "tests" / "fixtures" / "g2p" / "zh_en_loanword_matrix.json"
        )
        if not matrix_path.exists():
            pytest.skip(f"Matrix fixture not found: {matrix_path}")
        with open(matrix_path, encoding="utf-8") as f:
            return json.load(f)

    def test_matrix_loads_and_well_formed(self):
        """Matrix file exists, is valid JSON, and every case has a name."""
        data = self._load_matrix()
        assert "cases" in data, "matrix must have a `cases` array"
        assert isinstance(data["cases"], list)
        assert len(data["cases"]) > 0, "matrix must contain at least one case"
        for case in data["cases"]:
            assert "name" in case, f"case missing `name`: {case}"

    def test_matrix_strict_token_counts(self):
        """Every case with ``expected_token_count`` must match exactly.

        This is the strictest contract — drift here means the Python
        source-of-truth has changed and all 6 mirror runtimes need to be
        re-validated.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        data = self._load_matrix()
        for case in data["cases"]:
            if "input" not in case or "expected_token_count" not in case:
                continue
            tokens, _ = p.phonemize_embedded_english(case["input"])
            actual = len(tokens)
            expected = case["expected_token_count"]
            assert actual == expected, (
                f"{case['name']!r}: input {case['input']!r} expected "
                f"{expected} tokens, got {actual}: {tokens}"
            )

    def test_matrix_equivalence_cases(self):
        """``expected_token_count_equiv`` cases must produce the SAME tokens."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        data = self._load_matrix()
        cache: dict[str, list[str]] = {}

        def tokens_for(text: str) -> list[str]:
            if text not in cache:
                cache[text] = p.phonemize_embedded_english(text)[0]
            return cache[text]

        for case in data["cases"]:
            equiv = case.get("expected_token_count_equiv")
            if equiv is None or "input" not in case:
                continue
            actual = tokens_for(case["input"])
            ref = tokens_for(equiv)
            assert actual == ref, (
                f"{case['name']!r}: tokens for {case['input']!r} should equal "
                f"tokens for {equiv!r}. Got {actual} vs {ref}"
            )

    def test_matrix_differs_cases(self):
        """``expected_token_count_differs_from`` cases must NOT match."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        data = self._load_matrix()
        for case in data["cases"]:
            differs = case.get("expected_token_count_differs_from")
            if differs is None or "input" not in case:
                continue
            actual_tokens, _ = p.phonemize_embedded_english(case["input"])
            ref_tokens, _ = p.phonemize_embedded_english(differs)
            assert len(actual_tokens) != len(ref_tokens), (
                f"{case['name']!r}: token count for {case['input']!r} "
                f"({len(actual_tokens)}) must differ from {differs!r} "
                f"({len(ref_tokens)})"
            )

    def test_matrix_relation_2x_of_input_z(self):
        """``letter_fallback_zz_doubles_z``: ZZ must produce 2x the tokens of Z."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        data = self._load_matrix()
        target_name = "letter_fallback_zz_doubles_z"
        z_case = next(
            (c for c in data["cases"] if c.get("name") == target_name),
            None,
        )
        if z_case is None:
            pytest.skip("letter_fallback_zz_doubles_z case not present in matrix")
        zz_tokens, _ = p.phonemize_embedded_english("ZZ")
        z_tokens, _ = p.phonemize_embedded_english("Z")
        assert len(zz_tokens) == 2 * len(z_tokens), (
            f"ZZ ({len(zz_tokens)}) must be exactly 2x Z ({len(z_tokens)}) "
            f"per letter-fallback contract"
        )

    def test_matrix_schema_v2_loader_case(self):
        """``schema_v2_forward_compat_loader`` case: the embedded JSON loads."""
        from piper_plus_g2p.chinese import _load_loanword_data

        data = self._load_matrix()
        target_name = "schema_v2_forward_compat_loader"
        case = next(
            (c for c in data["cases"] if c.get("name") == target_name),
            None,
        )
        if case is None:
            pytest.skip("schema_v2_forward_compat_loader case not present in matrix")
        json_data = case.get("input_json")
        assert json_data is not None, "case must include `input_json`"
        # Write to a temp file and feed through the real loader.
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(json_data, f)
            tmp_path = f.name
        try:
            loaded = _load_loanword_data(Path(tmp_path))
            # Known sections must round-trip
            for section in ("acronyms", "loanwords", "letter_fallback"):
                if section in json_data:
                    assert loaded[section] == json_data[section]
        finally:
            Path(tmp_path).unlink(missing_ok=True)


@requires_zh
class TestRuntimeBundleSync:
    """The runtime-side JSON copy must stay in sync with the training-side source."""

    def test_runtime_copy_matches_source(self):
        """src/python_run/piper/phonemize/data/zh_en_loanword.json
        must match src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
        byte-for-byte. The runtime wheel ships its own copy because the
        training-side g2p package is not a runtime dependency.
        """
        from piper_plus_g2p.chinese import _DEFAULT_LOANWORD_DATA_PATH

        repo_root = Path(__file__).resolve().parents[4]
        runtime_copy = (
            repo_root
            / "src"
            / "python_run"
            / "piper"
            / "phonemize"
            / "data"
            / "zh_en_loanword.json"
        )
        if not runtime_copy.exists():
            pytest.skip(f"Runtime copy not present at {runtime_copy}")
        src_bytes = Path(_DEFAULT_LOANWORD_DATA_PATH).read_bytes()
        rt_bytes = runtime_copy.read_bytes()
        assert src_bytes == rt_bytes, (
            "Runtime zh_en_loanword.json is out of sync with the training-side "
            "source. Re-run `cp src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json "
            "src/python_run/piper/phonemize/data/zh_en_loanword.json`."
        )


@requires_zh
class TestEnZhEnPattern:
    """The previously-untested [en, zh, en] pattern (English -> Chinese -> English).

    Both English segments must be dispatched through the embedded loanword
    path because they sit adjacent to a Chinese segment. This pins the
    multi-segment dispatch behaviour beyond the simpler [zh, en] /
    [en, zh] / [zh, en, zh] cases already covered.
    """

    def test_en_zh_en_pattern(self):
        """[en, zh, en] = ``GPS 中国 OK`` -- both EN segments dispatched."""
        from piper_plus_g2p.chinese import ChinesePhonemizer
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        full_tokens, _ = p.phonemize_with_prosody("GPS 中国 OK")

        baseline_tokens, _ = ChinesePhonemizer().phonemize_with_prosody("中国")
        full_tones = sum(1 for t in full_tokens if t.startswith("tone"))
        base_tones = sum(1 for t in baseline_tokens if t.startswith("tone"))

        # GPS = 4 syllables, OK = 2 syllables -> +6 tones over the zh baseline
        assert full_tones - base_tones == 6, (
            f"Expected +6 tones (GPS=4 + OK=2), got {full_tones - base_tones}"
        )

        # And both EN segments must produce mandarin tones (i.e. no path
        # leaked through to EnglishPhonemizer for either segment).
        # GPS first 4 tones: 4,4,1,4; OK last 2 tones: 1,4
        tones = [t for t in full_tokens if t.startswith("tone")]
        # Leading 4 tones come from GPS
        assert tones[:4] == ["tone4", "tone4", "tone1", "tone4"], tones[:4]
        # Trailing 2 tones come from OK
        assert tones[-2:] == ["tone1", "tone4"], tones[-2:]

    def test_en_zh_alternating_4_segments(self):
        """4-segment alternation: en zh en zh en (GPS 中 OK 国 USB)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("zh-en")
        full_tokens, _ = p.phonemize_with_prosody("GPS 中 OK 国 USB")

        baseline_tokens, _ = ChinesePhonemizer().phonemize_with_prosody("中 国")
        full_tones = sum(1 for t in full_tokens if t.startswith("tone"))
        base_tones = sum(1 for t in baseline_tokens if t.startswith("tone"))

        # GPS=4, OK=2, USB=3 (uppercase letters U=iou1, S=ai1+si4=2, B=pi4)
        # -> default acronym table: USB = ['iou1', 'ai1', 'si4', 'pi4']? Let's
        # trust the contract: the dispatched extra tones must be exactly
        # 4 + 2 + N (where N matches the USB acronym entry length).
        # We assert the floor: at least +6 from GPS+OK.
        assert full_tones - base_tones >= 6, (
            f"Expected +6 or more tones from 3 EN segments, got "
            f"{full_tones - base_tones}"
        )


@requires_zh
class TestErhuaInteraction:
    """Pin behaviour at the intersection of erhua (儿化音) and tone sandhi.

    The current implementation applies tone sandhi to runs of T3 syllables
    in the original pypinyin output (before erhua splitting). 儿 itself is
    T2 in pypinyin's output, so it breaks T3 chains and erhua doesn't
    interact with sandhi in the way one might naively assume. These tests
    pin the resulting (snapshot) behaviour.
    """

    def test_erhua_with_t3_sandhi(self):
        """``我们儿`` -- 我=T3, 们=T5 (neutral), 儿=T2.

        The T5 of 们 breaks the T3 chain, so 我's T3 is preserved (no
        sandhi). The 儿 attaches as standalone T2 erhua syllable.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("我们儿")
        # 我 = uo+tone3, 们 = m+ən+tone5, 儿 = ɚ+tone2
        assert tokens == [
            "uo", "tone3",
            "m", "ən", "tone5",
            "ɚ", "tone2",
        ], tokens

    def test_erhua_at_word_boundary(self):
        """``这儿好`` -- 这=T4, 儿=T2, 好=T3.

        No T3 chain is formed (only the trailing 好 is T3), so no sandhi
        applies. Erhua 儿 keeps its lexical T2.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("这儿好")
        # 这 = tʂ+ɤ+tone4, 儿 = ɚ+tone2, 好 = x+aʊ+tone3
        assert tokens == [
            "tʂ", "ɤ", "tone4",
            "ɚ", "tone2",
            "x", "aʊ", "tone3",
        ], tokens


@requires_zh
class TestUnknownUnicodeInEn:
    """The ``_RE_TOKEN_SPLIT = re.compile(r"[A-Za-z0-9]+")`` tokenizer
    drops any non-alphanumeric character (registered marks, plus signs,
    hyphens, emoji, etc.) inside the EN segment. Pin this drop behaviour
    so future tokenizer changes do not silently introduce them into the
    pinyin lookup.
    """

    def test_en_segment_with_register_mark(self):
        """``GPS®`` -- ® drops, GPS still hits the acronym table."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        baseline, _ = p.phonemize_embedded_english("GPS")
        with_mark, _ = p.phonemize_embedded_english("GPS®")
        assert baseline == with_mark, (
            f"® should be dropped: baseline={baseline}, with_mark={with_mark}"
        )

    def test_en_segment_with_plus(self):
        """``GPS+`` -- ``+`` drops, GPS hits."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        baseline, _ = p.phonemize_embedded_english("GPS")
        with_plus, _ = p.phonemize_embedded_english("GPS+")
        assert baseline == with_plus, (
            f"+ should be dropped: baseline={baseline}, with_plus={with_plus}"
        )

    def test_en_segment_with_hyphen(self):
        """``GPS-2`` -- the hyphen splits into [``GPS``, ``2``]; the
        digit-only token ``2`` then runs through letter_fallback character
        by character. Since ``2`` is not in the A-Z fallback table (which
        only covers letters), the digit is silently dropped, giving the
        same result as bare ``GPS``.
        """
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        baseline, _ = p.phonemize_embedded_english("GPS")
        with_hyphen, _ = p.phonemize_embedded_english("GPS-2")
        assert baseline == with_hyphen, (
            f"Hyphen and bare digit should be dropped: "
            f"baseline={baseline}, with_hyphen={with_hyphen}"
        )

    def test_en_segment_with_emoji(self):
        """``GPS👍`` -- emoji drops, GPS hits."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        baseline, _ = p.phonemize_embedded_english("GPS")
        with_emoji, _ = p.phonemize_embedded_english("GPS👍")
        assert baseline == with_emoji, (
            f"Emoji should be dropped: baseline={baseline}, with_emoji={with_emoji}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
