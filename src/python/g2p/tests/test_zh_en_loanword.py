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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
