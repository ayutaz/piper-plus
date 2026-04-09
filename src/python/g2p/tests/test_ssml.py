"""Tests for piper_plus_g2p.ssml — SSML basic tag parser."""

import pytest

from piper_plus_g2p.ssml import _MAX_SSML_SIZE, BreakStrength, SSMLParser, SSMLSegment

# =====================================================================
# is_ssml()
# =====================================================================


class TestIsSSML:
    """Detection of SSML vs plain text."""

    def test_speak_tag_detected(self):
        assert SSMLParser.is_ssml("<speak>Hello</speak>") is True

    def test_speak_tag_with_attributes(self):
        assert SSMLParser.is_ssml('<speak version="1.0">Hi</speak>') is True

    def test_speak_tag_with_leading_whitespace(self):
        assert SSMLParser.is_ssml("  \n<speak>Hello</speak>") is True

    def test_plain_text_not_detected(self):
        assert SSMLParser.is_ssml("Hello, world!") is False

    def test_other_xml_not_detected(self):
        assert SSMLParser.is_ssml("<html><body>Hi</body></html>") is False

    def test_empty_string(self):
        assert SSMLParser.is_ssml("") is False

    def test_speak_substring_not_detected(self):
        """'speak' appearing in normal text should not trigger."""
        assert SSMLParser.is_ssml("I want to speak clearly.") is False

    def test_speak_in_middle_not_detected(self):
        assert SSMLParser.is_ssml("Hello <speak>world</speak>") is False


# =====================================================================
# _parse_break_time()
# =====================================================================


class TestParseBreakTime:
    """Parsing of break time attributes."""

    @pytest.mark.parametrize(
        "input_str, expected_ms",
        [
            ("500ms", 500),
            ("1s", 1000),
            ("0.5s", 500),
            ("250.5ms", 250),
            ("0ms", 0),
            ("0s", 0),
            ("  500ms  ", 500),
            ("abc", 0),
            ("300", 300),
        ],
        ids=[
            "milliseconds",
            "seconds",
            "fractional_seconds",
            "fractional_milliseconds",
            "zero_ms",
            "zero_s",
            "whitespace_handling",
            "invalid_returns_zero",
            "bare_number_treated_as_ms",
        ],
    )
    def test_parse_break_time(self, input_str, expected_ms):
        assert SSMLParser._parse_break_time(input_str) == expected_ms


# =====================================================================
# _parse_rate()
# =====================================================================


class TestParseRate:
    """Parsing of prosody rate attributes."""

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            ("slow", 1.25),
            ("fast", 0.8),
            ("medium", 1.0),
            ("x-slow", 1.5),
            ("x-fast", 0.6),
            ("100%", pytest.approx(1.0)),
            ("120%", pytest.approx(100.0 / 120.0)),
            ("50%", pytest.approx(2.0)),
            ("200%", pytest.approx(0.5)),
            ("0%", 1.0),
            ("-50%", 1.0),
            ("banana", 1.0),
            ("SLOW", 1.25),
            ("Fast", 0.8),
        ],
        ids=[
            "named_slow",
            "named_fast",
            "named_medium",
            "named_x_slow",
            "named_x_fast",
            "percentage_100",
            "percentage_120",
            "percentage_50",
            "percentage_200",
            "zero_percentage_returns_default",
            "negative_percentage_returns_default",
            "invalid_returns_default",
            "case_insensitive_upper",
            "case_insensitive_mixed",
        ],
    )
    def test_parse_rate(self, input_str, expected):
        assert SSMLParser._parse_rate(input_str) == expected


# =====================================================================
# BreakStrength enum
# =====================================================================


class TestBreakStrength:
    """BreakStrength enum consistency with parser lookup."""

    def test_all_strengths_in_lookup(self):
        for bs in BreakStrength:
            assert bs.value in SSMLParser.BREAK_STRENGTH_MS

    @pytest.mark.parametrize(
        "strength, expected_ms",
        [
            ("none", 0),
            ("x-strong", 1000),
        ],
        ids=["none_is_zero", "x_strong_is_1000"],
    )
    def test_strength_value(self, strength, expected_ms):
        assert SSMLParser.BREAK_STRENGTH_MS[strength] == expected_ms


# =====================================================================
# parse() — break tags
# =====================================================================


class TestParseBreak:
    """Parsing <break> tags."""

    def test_break_time_ms(self):
        ssml = '<speak>Hello<break time="500ms"/>world</speak>'
        segments = SSMLParser.parse(ssml)
        # Expect: "Hello", break 500ms, "world"
        texts = [s.text for s in segments if s.text]
        breaks = [s.break_ms for s in segments if s.break_ms > 0]
        assert "Hello" in texts
        assert "world" in texts
        assert 500 in breaks

    def test_break_time_seconds(self):
        ssml = '<speak>A<break time="2s"/>B</speak>'
        segments = SSMLParser.parse(ssml)
        breaks = [s.break_ms for s in segments if s.break_ms > 0]
        assert 2000 in breaks

    def test_break_strength(self):
        ssml = '<speak>A<break strength="strong"/>B</speak>'
        segments = SSMLParser.parse(ssml)
        breaks = [s.break_ms for s in segments if s.break_ms > 0]
        assert 700 in breaks

    def test_break_no_attributes_defaults_to_medium(self):
        ssml = "<speak>A<break/>B</speak>"
        segments = SSMLParser.parse(ssml)
        breaks = [s.break_ms for s in segments if s.break_ms > 0]
        assert 400 in breaks

    def test_standalone_break(self):
        """A break with no surrounding text."""
        ssml = '<speak><break time="1s"/></speak>'
        segments = SSMLParser.parse(ssml)
        assert any(s.break_ms == 1000 for s in segments)


# =====================================================================
# parse() — prosody rate
# =====================================================================


class TestParseProsodyRate:
    """Parsing <prosody rate="..."> tags."""

    @pytest.mark.parametrize(
        "ssml, expected_text, expected_rate",
        [
            ('<speak><prosody rate="slow">Hello</prosody></speak>', "Hello", 1.25),
            ('<speak><prosody rate="fast">Quick</prosody></speak>', "Quick", 0.8),
            (
                '<speak><prosody rate="150%">Faster</prosody></speak>',
                "Faster",
                pytest.approx(100.0 / 150.0),
            ),
            ("<speak>Normal text</speak>", "Normal text", 1.0),
            ("<speak><prosody>Text</prosody></speak>", "Text", 1.0),
        ],
        ids=[
            "rate_slow",
            "rate_fast",
            "rate_percentage_150",
            "default_when_absent",
            "prosody_without_rate_attr",
        ],
    )
    def test_prosody_rate(self, ssml, expected_text, expected_rate):
        segments = SSMLParser.parse(ssml)
        assert segments[0].text == expected_text
        assert segments[0].rate == expected_rate


# =====================================================================
# parse() — nested tags
# =====================================================================


class TestParseNested:
    """Nested SSML tags."""

    def test_break_inside_prosody(self):
        ssml = (
            "<speak>"
            '<prosody rate="slow">'
            'Before<break time="300ms"/>After'
            "</prosody>"
            "</speak>"
        )
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "Before" in texts
        assert "After" in texts
        # Break should have the parent prosody's rate
        break_segs = [s for s in segments if s.break_ms > 0]
        assert len(break_segs) == 1
        assert break_segs[0].break_ms == 300

    def test_multiple_prosody_sections(self):
        ssml = (
            "<speak>"
            '<prosody rate="slow">Slow</prosody>'
            '<prosody rate="fast">Fast</prosody>'
            "</speak>"
        )
        segments = SSMLParser.parse(ssml)
        slow_segs = [s for s in segments if s.rate == 1.25]
        fast_segs = [s for s in segments if s.rate == 0.8]
        assert len(slow_segs) >= 1
        assert len(fast_segs) >= 1
        assert slow_segs[0].text == "Slow"
        assert fast_segs[0].text == "Fast"


# =====================================================================
# parse() — combined break + prosody
# =====================================================================


class TestParseCombined:
    """Combined break and prosody scenarios."""

    def test_break_between_prosody(self):
        ssml = (
            "<speak>"
            '<prosody rate="slow">Slow</prosody>'
            '<break time="500ms"/>'
            '<prosody rate="fast">Fast</prosody>'
            "</speak>"
        )
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "Slow" in texts
        assert "Fast" in texts
        break_segs = [s for s in segments if s.break_ms > 0]
        assert any(s.break_ms == 500 for s in break_segs)

    def test_complex_mixed(self):
        ssml = (
            "<speak>"
            "Hello "
            '<break time="200ms"/>'
            '<prosody rate="fast">Quick part</prosody>'
            '<break time="1s"/>'
            "End"
            "</speak>"
        )
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "Hello" in texts
        assert "Quick part" in texts
        assert "End" in texts


# =====================================================================
# parse() — XML error fallback
# =====================================================================


class TestSSMLSizeLimit:
    """SSML input size limit to mitigate XML DoS."""

    def test_oversized_ssml_raises(self):
        ssml = "<speak>" + "A" * (_MAX_SSML_SIZE + 1) + "</speak>"
        with pytest.raises(ValueError, match="SSML input too large"):
            SSMLParser.parse(ssml)

    def test_within_limit_parses_ok(self):
        ssml = "<speak>" + "A" * 100 + "</speak>"
        segments = SSMLParser.parse(ssml)
        assert len(segments) >= 1
        assert "A" in segments[0].text

    def test_plain_text_skips_size_check(self):
        """Plain text (non-SSML) should not be subject to the size limit."""
        text = "A" * (_MAX_SSML_SIZE + 1)
        segments = SSMLParser.parse(text)
        assert len(segments) == 1
        assert segments[0].text == text


class TestXMLErrorFallback:
    """Graceful fallback on malformed XML."""

    def test_unclosed_tag_fallback(self):
        ssml = "<speak>Hello <break"
        segments = SSMLParser.parse(ssml)
        # Should not crash; returns content as plain text
        assert len(segments) >= 1
        full_text = " ".join(s.text for s in segments)
        assert "Hello" in full_text

    def test_invalid_xml_returns_stripped_text(self):
        ssml = "<speak>Some text <invalid></speak>"
        segments = SSMLParser.parse(ssml)
        assert len(segments) >= 1
        full_text = " ".join(s.text for s in segments)
        assert "Some text" in full_text or "text" in full_text


# =====================================================================
# parse() — plain text (non-SSML)
# =====================================================================


class TestPlainText:
    """Non-SSML input handling."""

    def test_plain_text_passthrough(self):
        text = "Hello, world!"
        segments = SSMLParser.parse(text)
        assert len(segments) == 1
        assert segments[0].text == text
        assert segments[0].break_ms == 0
        assert segments[0].rate == 1.0

    def test_empty_string(self):
        segments = SSMLParser.parse("")
        assert len(segments) == 1
        assert segments[0].text == ""


# =====================================================================
# parse() — Japanese text
# =====================================================================


class TestJapaneseSSML:
    """SSML containing Japanese text."""

    def test_japanese_in_speak(self):
        ssml = "<speak>こんにちは、世界。</speak>"
        segments = SSMLParser.parse(ssml)
        assert len(segments) == 1
        assert "こんにちは" in segments[0].text

    def test_japanese_with_break(self):
        ssml = '<speak>おはよう<break time="500ms"/>ございます</speak>'
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "おはよう" in texts
        assert "ございます" in texts

    def test_japanese_with_prosody(self):
        ssml = '<speak><prosody rate="slow">ゆっくり話します</prosody></speak>'
        segments = SSMLParser.parse(ssml)
        assert segments[0].text == "ゆっくり話します"
        assert segments[0].rate == 1.25

    def test_mixed_japanese_english(self):
        ssml = (
            "<speak>"
            "こんにちは"
            '<break time="300ms"/>'
            '<prosody rate="fast">Hello world</prosody>'
            "</speak>"
        )
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "こんにちは" in texts
        assert "Hello world" in texts


# =====================================================================
# parse() — unknown tags (graceful degradation)
# =====================================================================


class TestUnknownTags:
    """Unknown SSML tags should have their text extracted."""

    def test_unknown_tag_text_extracted(self):
        ssml = "<speak><emphasis>Important</emphasis></speak>"
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "Important" in texts

    def test_nested_unknown_tags(self):
        ssml = "<speak><say-as interpret-as='date'>2026-04-08</say-as></speak>"
        segments = SSMLParser.parse(ssml)
        texts = [s.text for s in segments if s.text]
        assert "2026-04-08" in texts


# =====================================================================
# SSMLSegment dataclass
# =====================================================================


class TestSSMLSegment:
    """SSMLSegment dataclass basics."""

    def test_defaults(self):
        seg = SSMLSegment(text="hello")
        assert seg.text == "hello"
        assert seg.break_ms == 0
        assert seg.rate == 1.0

    def test_custom_values(self):
        seg = SSMLSegment(text="test", break_ms=500, rate=0.8)
        assert seg.break_ms == 500
        assert seg.rate == 0.8

    def test_equality(self):
        a = SSMLSegment(text="hi", break_ms=100, rate=1.0)
        b = SSMLSegment(text="hi", break_ms=100, rate=1.0)
        assert a == b

    def test_silence_segment(self):
        """Silence-only segment has empty text and nonzero break."""
        seg = SSMLSegment(text="", break_ms=1000)
        assert seg.text == ""
        assert seg.break_ms == 1000
