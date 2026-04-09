using PiperPlus.Core.Ssml;

namespace PiperPlus.Core.Tests.Ssml;

// =====================================================================
// IsSsml()
// =====================================================================

public class SsmlParserIsSsmlTests
{
    [Fact]
    public void SpeakTag_Detected()
    {
        Assert.True(SsmlParser.IsSsml("<speak>Hello</speak>"));
    }

    [Fact]
    public void SpeakTag_WithAttributes_Detected()
    {
        Assert.True(SsmlParser.IsSsml("<speak version=\"1.0\">Hi</speak>"));
    }

    [Fact]
    public void SpeakTag_WithLeadingWhitespace_Detected()
    {
        Assert.True(SsmlParser.IsSsml("  \n<speak>Hello</speak>"));
    }

    [Fact]
    public void PlainText_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml("Hello, world!"));
    }

    [Fact]
    public void OtherXml_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml("<html><body>Hi</body></html>"));
    }

    [Fact]
    public void EmptyString_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml(""));
    }

    [Fact]
    public void NullString_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml(null!));
    }

    [Fact]
    public void SpeakSubstring_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml("I want to speak clearly."));
    }

    [Fact]
    public void SpeakInMiddle_NotDetected()
    {
        Assert.False(SsmlParser.IsSsml("Hello <speak>world</speak>"));
    }
}

// =====================================================================
// ParseBreakTime()
// =====================================================================

public class SsmlParserBreakTimeTests
{
    [Fact]
    public void Milliseconds()
    {
        Assert.Equal(500, SsmlParser.ParseBreakTime("500ms"));
    }

    [Fact]
    public void Seconds()
    {
        Assert.Equal(1000, SsmlParser.ParseBreakTime("1s"));
    }

    [Fact]
    public void FractionalSeconds()
    {
        Assert.Equal(500, SsmlParser.ParseBreakTime("0.5s"));
    }

    [Fact]
    public void FractionalMilliseconds()
    {
        Assert.Equal(250, SsmlParser.ParseBreakTime("250.5ms"));
    }

    [Fact]
    public void ZeroMs()
    {
        Assert.Equal(0, SsmlParser.ParseBreakTime("0ms"));
    }

    [Fact]
    public void ZeroS()
    {
        Assert.Equal(0, SsmlParser.ParseBreakTime("0s"));
    }

    [Fact]
    public void WhitespaceHandling()
    {
        Assert.Equal(500, SsmlParser.ParseBreakTime("  500ms  "));
    }

    [Fact]
    public void InvalidReturnsZero()
    {
        Assert.Equal(0, SsmlParser.ParseBreakTime("abc"));
    }

    [Fact]
    public void BareNumber_TreatedAsMs()
    {
        Assert.Equal(300, SsmlParser.ParseBreakTime("300"));
    }
}

// =====================================================================
// ParseRate()
// =====================================================================

public class SsmlParserRateTests
{
    [Fact]
    public void NamedSlow()
    {
        Assert.Equal(1.25f, SsmlParser.ParseRate("slow"));
    }

    [Fact]
    public void NamedFast()
    {
        Assert.Equal(0.8f, SsmlParser.ParseRate("fast"));
    }

    [Fact]
    public void NamedMedium()
    {
        Assert.Equal(1.0f, SsmlParser.ParseRate("medium"));
    }

    [Fact]
    public void NamedXSlow()
    {
        Assert.Equal(1.5f, SsmlParser.ParseRate("x-slow"));
    }

    [Fact]
    public void NamedXFast()
    {
        Assert.Equal(0.6f, SsmlParser.ParseRate("x-fast"));
    }

    [Fact]
    public void Percentage100()
    {
        Assert.Equal(1.0f, SsmlParser.ParseRate("100%"), precision: 3);
    }

    [Fact]
    public void Percentage120()
    {
        // 120% speaking rate -> length_scale = 100/120 ~ 0.833
        Assert.Equal(100.0f / 120.0f, SsmlParser.ParseRate("120%"), precision: 3);
    }

    [Fact]
    public void Percentage50()
    {
        // 50% speaking rate -> length_scale = 2.0 (slower)
        Assert.Equal(2.0f, SsmlParser.ParseRate("50%"), precision: 3);
    }

    [Fact]
    public void Percentage200()
    {
        // 200% speaking rate -> length_scale = 0.5 (faster)
        Assert.Equal(0.5f, SsmlParser.ParseRate("200%"), precision: 3);
    }

    [Fact]
    public void ZeroPercentage_ReturnsDefault()
    {
        Assert.Equal(1.0f, SsmlParser.ParseRate("0%"));
    }

    [Fact]
    public void NegativePercentage_ReturnsDefault()
    {
        Assert.Equal(1.0f, SsmlParser.ParseRate("-50%"));
    }

    [Fact]
    public void Invalid_ReturnsDefault()
    {
        Assert.Equal(1.0f, SsmlParser.ParseRate("banana"));
    }

    [Fact]
    public void CaseInsensitive()
    {
        Assert.Equal(1.25f, SsmlParser.ParseRate("SLOW"));
        Assert.Equal(0.8f, SsmlParser.ParseRate("Fast"));
    }
}

// =====================================================================
// Parse() -- break tags
// =====================================================================

public class SsmlParserBreakTests
{
    [Fact]
    public void BreakTimeMs()
    {
        var ssml = "<speak>Hello<break time=\"500ms\"/>world</speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        var breaks = segments.Where(s => s.BreakMs > 0).Select(s => s.BreakMs).ToList();
        Assert.Contains("Hello", texts);
        Assert.Contains("world", texts);
        Assert.Contains(500, breaks);
    }

    [Fact]
    public void BreakTimeSeconds()
    {
        var ssml = "<speak>A<break time=\"2s\"/>B</speak>";
        var segments = SsmlParser.Parse(ssml);
        var breaks = segments.Where(s => s.BreakMs > 0).Select(s => s.BreakMs).ToList();
        Assert.Contains(2000, breaks);
    }

    [Fact]
    public void BreakStrength()
    {
        var ssml = "<speak>A<break strength=\"strong\"/>B</speak>";
        var segments = SsmlParser.Parse(ssml);
        var breaks = segments.Where(s => s.BreakMs > 0).Select(s => s.BreakMs).ToList();
        Assert.Contains(700, breaks);
    }

    [Fact]
    public void BreakNoAttributes_DefaultsToMedium()
    {
        var ssml = "<speak>A<break/>B</speak>";
        var segments = SsmlParser.Parse(ssml);
        var breaks = segments.Where(s => s.BreakMs > 0).Select(s => s.BreakMs).ToList();
        Assert.Contains(400, breaks);
    }

    [Fact]
    public void StandaloneBreak()
    {
        var ssml = "<speak><break time=\"1s\"/></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Contains(segments, s => s.BreakMs == 1000);
    }
}

// =====================================================================
// Parse() -- prosody rate
// =====================================================================

public class SsmlParserProsodyRateTests
{
    [Fact]
    public void ProsodyRateSlow()
    {
        var ssml = "<speak><prosody rate=\"slow\">Hello</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Single(segments);
        Assert.Equal("Hello", segments[0].Text);
        Assert.Equal(1.25f, segments[0].Rate);
    }

    [Fact]
    public void ProsodyRateFast()
    {
        var ssml = "<speak><prosody rate=\"fast\">Quick</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Equal(0.8f, segments[0].Rate);
    }

    [Fact]
    public void ProsodyRatePercentage()
    {
        var ssml = "<speak><prosody rate=\"150%\">Faster</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Equal(100.0f / 150.0f, segments[0].Rate, precision: 3);
    }

    [Fact]
    public void DefaultRateWhenAbsent()
    {
        var ssml = "<speak>Normal text</speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Equal(1.0f, segments[0].Rate);
    }

    [Fact]
    public void ProsodyWithoutRateAttr_UsesDefault()
    {
        var ssml = "<speak><prosody>Text</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Equal(1.0f, segments[0].Rate);
    }
}

// =====================================================================
// Parse() -- nested tags
// =====================================================================

public class SsmlParserNestedTests
{
    [Fact]
    public void BreakInsideProsody()
    {
        var ssml = "<speak><prosody rate=\"slow\">Before<break time=\"300ms\"/>After</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("Before", texts);
        Assert.Contains("After", texts);
        var breakSegs = segments.Where(s => s.BreakMs > 0).ToList();
        Assert.Single(breakSegs);
        Assert.Equal(300, breakSegs[0].BreakMs);
    }

    [Fact]
    public void MultipleProsodySections()
    {
        var ssml = "<speak><prosody rate=\"slow\">Slow</prosody><prosody rate=\"fast\">Fast</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        var slowSegs = segments.Where(s => s.Rate == 1.25f).ToList();
        var fastSegs = segments.Where(s => s.Rate == 0.8f).ToList();
        Assert.True(slowSegs.Count >= 1);
        Assert.True(fastSegs.Count >= 1);
        Assert.Equal("Slow", slowSegs[0].Text);
        Assert.Equal("Fast", fastSegs[0].Text);
    }
}

// =====================================================================
// Parse() -- combined break + prosody
// =====================================================================

public class SsmlParserCombinedTests
{
    [Fact]
    public void BreakBetweenProsody()
    {
        var ssml = "<speak><prosody rate=\"slow\">Slow</prosody><break time=\"500ms\"/><prosody rate=\"fast\">Fast</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("Slow", texts);
        Assert.Contains("Fast", texts);
        Assert.Contains(segments, s => s.BreakMs == 500);
    }

    [Fact]
    public void ComplexMixed()
    {
        var ssml = "<speak>Hello <break time=\"200ms\"/><prosody rate=\"fast\">Quick part</prosody><break time=\"1s\"/>End</speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("Hello", texts);
        Assert.Contains("Quick part", texts);
        Assert.Contains("End", texts);
    }
}

// =====================================================================
// Parse() -- XML error fallback
// =====================================================================

public class SsmlParserFallbackTests
{
    [Fact]
    public void UnclosedTag_Fallback()
    {
        var ssml = "<speak>Hello <break";
        var segments = SsmlParser.Parse(ssml);
        Assert.True(segments.Count >= 1);
        var fullText = string.Join(" ", segments.Select(s => s.Text));
        Assert.Contains("Hello", fullText);
    }

    [Fact]
    public void InvalidXml_ReturnsStrippedText()
    {
        var ssml = "<speak>Some text <invalid></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.True(segments.Count >= 1);
        var fullText = string.Join(" ", segments.Select(s => s.Text));
        Assert.True(fullText.Contains("Some text") || fullText.Contains("text"));
    }
}

// =====================================================================
// Parse() -- plain text (non-SSML)
// =====================================================================

public class SsmlParserPlainTextTests
{
    [Fact]
    public void PlainText_Passthrough()
    {
        var text = "Hello, world!";
        var segments = SsmlParser.Parse(text);
        Assert.Single(segments);
        Assert.Equal(text, segments[0].Text);
        Assert.Equal(0, segments[0].BreakMs);
        Assert.Equal(1.0f, segments[0].Rate);
    }

    [Fact]
    public void EmptyString()
    {
        var segments = SsmlParser.Parse("");
        Assert.Single(segments);
        Assert.Equal("", segments[0].Text);
    }
}

// =====================================================================
// Parse() -- Japanese text
// =====================================================================

public class SsmlParserJapaneseTests
{
    [Fact]
    public void JapaneseInSpeak()
    {
        var ssml = "<speak>\u3053\u3093\u306b\u3061\u306f\u3001\u4e16\u754c\u3002</speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Single(segments);
        Assert.Contains("\u3053\u3093\u306b\u3061\u306f", segments[0].Text);
    }

    [Fact]
    public void JapaneseWithBreak()
    {
        var ssml = "<speak>\u304a\u306f\u3088\u3046<break time=\"500ms\"/>\u3054\u3056\u3044\u307e\u3059</speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("\u304a\u306f\u3088\u3046", texts);
        Assert.Contains("\u3054\u3056\u3044\u307e\u3059", texts);
    }

    [Fact]
    public void JapaneseWithProsody()
    {
        var ssml = "<speak><prosody rate=\"slow\">\u3086\u3063\u304f\u308a\u8a71\u3057\u307e\u3059</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        Assert.Equal("\u3086\u3063\u304f\u308a\u8a71\u3057\u307e\u3059", segments[0].Text);
        Assert.Equal(1.25f, segments[0].Rate);
    }

    [Fact]
    public void MixedJapaneseEnglish()
    {
        var ssml = "<speak>\u3053\u3093\u306b\u3061\u306f<break time=\"300ms\"/><prosody rate=\"fast\">Hello world</prosody></speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("\u3053\u3093\u306b\u3061\u306f", texts);
        Assert.Contains("Hello world", texts);
    }
}

// =====================================================================
// Parse() -- unknown tags (graceful degradation)
// =====================================================================

public class SsmlParserUnknownTagTests
{
    [Fact]
    public void UnknownTag_TextExtracted()
    {
        var ssml = "<speak><emphasis>Important</emphasis></speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("Important", texts);
    }

    [Fact]
    public void NestedUnknownTags_TextExtracted()
    {
        var ssml = "<speak><say-as interpret-as=\"date\">2026-04-08</say-as></speak>";
        var segments = SsmlParser.Parse(ssml);
        var texts = segments.Where(s => !string.IsNullOrEmpty(s.Text)).Select(s => s.Text).ToList();
        Assert.Contains("2026-04-08", texts);
    }
}

// =====================================================================
// SsmlSegment record
// =====================================================================

public class SsmlSegmentTests
{
    [Fact]
    public void Defaults()
    {
        var seg = new SsmlSegment("hello");
        Assert.Equal("hello", seg.Text);
        Assert.Equal(0, seg.BreakMs);
        Assert.Equal(1.0f, seg.Rate);
    }

    [Fact]
    public void CustomValues()
    {
        var seg = new SsmlSegment("test", BreakMs: 500, Rate: 0.8f);
        Assert.Equal(500, seg.BreakMs);
        Assert.Equal(0.8f, seg.Rate);
    }

    [Fact]
    public void Equality()
    {
        var a = new SsmlSegment("hi", BreakMs: 100, Rate: 1.0f);
        var b = new SsmlSegment("hi", BreakMs: 100, Rate: 1.0f);
        Assert.Equal(a, b);
    }

    [Fact]
    public void SilenceSegment()
    {
        var seg = new SsmlSegment("", BreakMs: 1000);
        Assert.Equal("", seg.Text);
        Assert.Equal(1000, seg.BreakMs);
    }
}
