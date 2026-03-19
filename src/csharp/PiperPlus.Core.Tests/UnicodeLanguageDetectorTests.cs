using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

public sealed class UnicodeLanguageDetectorTests
{
    private static UnicodeLanguageDetector MakeDetector(
        params string[] langs)
        => new(langs, defaultLatinLanguage: "en");

    // ================================================================
    // 1. Kana_DetectsJapanese
    // ================================================================

    [Fact]
    public void Kana_DetectsJapanese()
    {
        var detector = MakeDetector("ja", "en");

        // Hiragana
        Assert.Equal("ja", detector.DetectChar('\u3072', contextHasKana: false)); // ひ
        // Katakana
        Assert.Equal("ja", detector.DetectChar('\u30AB', contextHasKana: false)); // カ
    }

    // ================================================================
    // 2. CJK_WithKanaContext_DetectsJapanese
    // ================================================================

    [Fact]
    public void CJK_WithKanaContext_DetectsJapanese()
    {
        var detector = MakeDetector("ja", "en", "zh");

        // CJK ideograph with kana context -> Japanese
        Assert.Equal("ja", detector.DetectChar('\u6F22', contextHasKana: true)); // 漢
    }

    // ================================================================
    // 3. CJK_WithoutKanaContext_DetectsChinese
    // ================================================================

    [Fact]
    public void CJK_WithoutKanaContext_DetectsChinese()
    {
        var detector = MakeDetector("ja", "en", "zh");

        // CJK ideograph without kana context -> Chinese
        Assert.Equal("zh", detector.DetectChar('\u6F22', contextHasKana: false)); // 漢
    }

    // ================================================================
    // 4. Hangul_DetectsKorean
    // ================================================================

    [Fact]
    public void Hangul_DetectsKorean()
    {
        var detector = MakeDetector("ja", "en", "ko");

        // Hangul syllable -> Korean
        Assert.Equal("ko", detector.DetectChar('\uD55C', contextHasKana: false)); // 한
    }

    // ================================================================
    // 5. Latin_DetectsDefaultLatin
    // ================================================================

    [Fact]
    public void Latin_DetectsDefaultLatin()
    {
        var detector = MakeDetector("ja", "en");

        // Basic Latin letter -> default Latin language ("en")
        Assert.Equal("en", detector.DetectChar('H', contextHasKana: false));
    }

    // ================================================================
    // 6. Space_ReturnsNull
    // ================================================================

    [Fact]
    public void Space_ReturnsNull()
    {
        var detector = MakeDetector("ja", "en");

        // Space is neutral -> null
        Assert.Null(detector.DetectChar(' ', contextHasKana: false));
    }

    // ================================================================
    // 7. Digit_ReturnsNull
    // ================================================================

    [Fact]
    public void Digit_ReturnsNull()
    {
        var detector = MakeDetector("ja", "en");

        // Digit is neutral -> null
        Assert.Null(detector.DetectChar('1', contextHasKana: false));
    }

    // ================================================================
    // 8. FullwidthLatin_DetectsLatin
    // ================================================================

    [Fact]
    public void FullwidthLatin_DetectsLatin()
    {
        var detector = MakeDetector("ja", "en");

        // Fullwidth Latin A (U+FF21) -> default Latin, NOT "ja"
        Assert.Equal("en", detector.DetectChar('\uFF21', contextHasKana: false));
    }

    // ================================================================
    // 9. JapanesePunctuation_DetectsJapanese
    // ================================================================

    [Fact]
    public void JapanesePunctuation_DetectsJapanese()
    {
        var detector = MakeDetector("ja", "en");

        // CJK ideographic full stop (U+3002) -> Japanese
        Assert.Equal("ja", detector.DetectChar('\u3002', contextHasKana: false));
    }

    // ================================================================
    // 10. SegmentText_MixedJaEn
    // ================================================================

    [Fact]
    public void SegmentText_MixedJaEn()
    {
        var detector = MakeDetector("ja", "en");

        var segments = detector.SegmentText("\u3053\u3093\u306B\u3061\u306Fhello");
        // "こんにちはhello" -> [("ja", "こんにちは"), ("en", "hello")]

        Assert.Equal(2, segments.Count);
        Assert.Equal("ja", segments[0].Lang);
        Assert.Equal("\u3053\u3093\u306B\u3061\u306F", segments[0].Text); // こんにちは
        Assert.Equal("en", segments[1].Lang);
        Assert.Equal("hello", segments[1].Text);
    }

    // ================================================================
    // 11. SegmentText_NeutralAbsorbed
    // ================================================================

    [Fact]
    public void SegmentText_NeutralAbsorbed()
    {
        var detector = MakeDetector("ja", "en");

        // Space is neutral and should be absorbed into the preceding segment
        var segments = detector.SegmentText("hello world");

        Assert.Single(segments);
        Assert.Equal("en", segments[0].Lang);
        Assert.Equal("hello world", segments[0].Text);
    }

    // ================================================================
    // 12. SegmentText_EmptyReturnsEmpty
    // ================================================================

    [Fact]
    public void SegmentText_EmptyReturnsEmpty()
    {
        var detector = MakeDetector("ja", "en");

        var segments = detector.SegmentText("");

        Assert.Empty(segments);
    }

    // ================================================================
    // 13. SegmentText_PunctOnlyFallback
    // ================================================================

    [Fact]
    public void SegmentText_PunctOnlyFallback()
    {
        var detector = MakeDetector("ja", "en");

        // No language-specific characters -> fallback to default language
        var segments = detector.SegmentText("123!");

        Assert.Single(segments);
        Assert.Equal("en", segments[0].Lang);
        Assert.Equal("123!", segments[0].Text);
    }

    // ================================================================
    // 14. HasKana_True
    // ================================================================

    [Fact]
    public void HasKana_True()
    {
        var detector = MakeDetector("ja", "en");

        // "漢字とひらがな" contains hiragana -> true
        Assert.True(detector.HasKana("\u6F22\u5B57\u3068\u3072\u3089\u304C\u306A"));
    }

    // ================================================================
    // 15. HasKana_False
    // ================================================================

    [Fact]
    public void HasKana_False()
    {
        var detector = MakeDetector("ja", "en");

        // Pure CJK ideographs only: "漢字" (U+6F22 U+5B57) -- no kana present
        Assert.False(detector.HasKana("\u6F22\u5B57"));
    }
}
