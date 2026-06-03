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
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

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
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "zh");

        // CJK ideograph with kana context -> Japanese
        Assert.Equal("ja", detector.DetectChar('\u6F22', contextHasKana: true)); // 漢
    }

    // ================================================================
    // 3. CJK_WithoutKanaContext_DetectsChinese
    // ================================================================
    [Fact]
    public void CJK_WithoutKanaContext_DetectsChinese()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "zh");

        // CJK ideograph without kana context -> Chinese
        Assert.Equal("zh", detector.DetectChar('\u6F22', contextHasKana: false)); // 漢
    }

    // ================================================================
    // 4. Hangul_DetectsKorean
    // ================================================================
    [Fact]
    public void Hangul_DetectsKorean()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "ko");

        // Hangul syllable -> Korean
        Assert.Equal("ko", detector.DetectChar('\uD55C', contextHasKana: false)); // 한
    }

    // ================================================================
    // 5. Latin_DetectsDefaultLatin
    // ================================================================
    [Fact]
    public void Latin_DetectsDefaultLatin()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Basic Latin letter -> default Latin language ("en")
        Assert.Equal("en", detector.DetectChar('H', contextHasKana: false));
    }

    // ================================================================
    // 6. Space_ReturnsNull
    // ================================================================
    [Fact]
    public void Space_ReturnsNull()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Space is neutral -> null
        Assert.Null(detector.DetectChar(' ', contextHasKana: false));
    }

    // ================================================================
    // 7. Digit_ReturnsNull
    // ================================================================
    [Fact]
    public void Digit_ReturnsNull()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Digit is neutral -> null
        Assert.Null(detector.DetectChar('1', contextHasKana: false));
    }

    // ================================================================
    // 8. FullwidthLatin_DetectsLatin
    // ================================================================
    [Fact]
    public void FullwidthLatin_DetectsLatin()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Fullwidth Latin A (U+FF21) -> default Latin, NOT "ja"
        Assert.Equal("en", detector.DetectChar('\uFF21', contextHasKana: false));
    }

    // ================================================================
    // 9. JapanesePunctuation_DetectsJapanese
    // ================================================================
    [Fact]
    public void JapanesePunctuation_DetectsJapanese()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // CJK ideographic full stop (U+3002) -> Japanese
        Assert.Equal("ja", detector.DetectChar('\u3002', contextHasKana: false));
    }

    // ================================================================
    // 10. SegmentText_MixedJaEn
    // ================================================================
    [Fact]
    public void SegmentText_MixedJaEn()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        List<(string Lang, string Text)> segments = detector.SegmentText("\u3053\u3093\u306B\u3061\u306Fhello");

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
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Space is neutral and should be absorbed into the preceding segment
        List<(string Lang, string Text)> segments = detector.SegmentText("hello world");

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
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        List<(string Lang, string Text)> segments = detector.SegmentText(string.Empty);

        Assert.Empty(segments);
    }

    // ================================================================
    // 13. SegmentText_PunctOnlyFallback
    // ================================================================
    [Fact]
    public void SegmentText_PunctOnlyFallback()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // No language-specific characters -> fallback to default language
        List<(string Lang, string Text)> segments = detector.SegmentText("123!");

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
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // "漢字とひらがな" contains hiragana -> true
        Assert.True(detector.HasKana("\u6F22\u5B57\u3068\u3072\u3089\u304C\u306A"));
    }

    // ================================================================
    // 15. HasKana_False
    // ================================================================
    [Fact]
    public void HasKana_False()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // Pure CJK ideographs only: "漢字" (U+6F22 U+5B57) -- no kana present
        Assert.False(detector.HasKana("\u6F22\u5B57"));
    }

    // ================================================================
    // 16. CjkExtensionA_Detected
    // ================================================================

    /// <summary>
    /// CJK Extension A character (U+3400) should be detected as CJK.
    /// Without kana context and with both ja+zh, it should map to "zh".
    /// </summary>
    [Fact]
    public void CjkExtensionA_Detected()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "zh");

        // U+3400 is the first code point in CJK Unified Ideographs Extension A
        Assert.Equal("zh", detector.DetectChar('\u3400', contextHasKana: false));

        // With kana context -> Japanese
        Assert.Equal("ja", detector.DetectChar('\u3400', contextHasKana: true));
    }

    // ================================================================
    // 17. CjkCompatibility_Detected
    // ================================================================

    /// <summary>
    /// CJK Compatibility Ideograph (U+F900) should be detected as CJK.
    /// Without kana context and with both ja+zh, it should map to "zh".
    /// </summary>
    [Fact]
    public void CjkCompatibility_Detected()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "zh");

        // U+F900 is the first code point in CJK Compatibility Ideographs
        Assert.Equal("zh", detector.DetectChar('\uF900', contextHasKana: false));

        // With kana context -> Japanese
        Assert.Equal("ja", detector.DetectChar('\uF900', contextHasKana: true));
    }

    // ================================================================
    // 18. MultiplicationSign_NotLatin
    // ================================================================

    /// <summary>
    /// U+00D7 (×) multiplication sign falls between Latin ranges and must
    /// be excluded from Latin detection -- should return null (neutral).
    /// </summary>
    [Fact]
    public void MultiplicationSign_NotLatin()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        Assert.Null(detector.DetectChar('\u00D7', contextHasKana: false));
    }

    // ================================================================
    // 19. DivisionSign_NotLatin
    // ================================================================

    /// <summary>
    /// U+00F7 (÷) division sign falls between Latin ranges and must
    /// be excluded from Latin detection -- should return null (neutral).
    /// </summary>
    [Fact]
    public void DivisionSign_NotLatin()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        Assert.Null(detector.DetectChar('\u00F7', contextHasKana: false));
    }

    // ================================================================
    // 20. HangulJamo_Detected
    // ================================================================

    /// <summary>
    /// Hangul Jamo character (U+1100, ᄀ) should be detected as Korean.
    /// This tests the Jamo range (U+1100-11FF) as opposed to the Hangul
    /// Syllables range tested by <see cref="Hangul_DetectsKorean"/>.
    /// </summary>
    [Fact]
    public void HangulJamo_Detected()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en", "ko");

        // U+1100 is Hangul Choseong Kiyeok (ᄀ)
        Assert.Equal("ko", detector.DetectChar('\u1100', contextHasKana: false));
    }

    // ================================================================
    // 21. LatinWithDiacritics_Detected
    // ================================================================

    /// <summary>
    /// Latin Extended character U+00C0 (À) should be detected as Latin,
    /// mapping to the default Latin language ("en").
    /// </summary>
    [Fact]
    public void LatinWithDiacritics_Detected()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        // U+00C0 is Latin Capital Letter A With Grave (À)
        Assert.Equal("en", detector.DetectChar('\u00C0', contextHasKana: false));
    }

    // ================================================================
    // 22. ThreeLanguageSegmentation
    // ================================================================

    /// <summary>
    /// "hello こんにちは world" should produce 3 segments:
    /// EN("hello "), JA("こんにちは "), EN("world").
    /// The trailing spaces are absorbed into the preceding segment.
    /// </summary>
    [Fact]
    public void ThreeLanguageSegmentation()
    {
        UnicodeLanguageDetector detector = MakeDetector("ja", "en");

        List<(string Lang, string Text)> segments = detector.SegmentText("hello \u3053\u3093\u306B\u3061\u306F world");

        Assert.Equal(3, segments.Count);
        Assert.Equal("en", segments[0].Lang);
        Assert.Equal("ja", segments[1].Lang);
        Assert.Equal("en", segments[2].Lang);

        // Verify text content: neutral chars absorbed into preceding segment
        Assert.Equal("hello ", segments[0].Text);
        Assert.Equal("\u3053\u3093\u306B\u3061\u306F ", segments[1].Text); // こんにちは + space
        Assert.Equal("world", segments[2].Text);
    }

    // ================================================================
    // Swedish per-word LID — CONSERVATIVE policy (Issue #539)
    // ================================================================

    /// <summary>
    /// Build a detector with sv present alongside en so the per-word
    /// post-pass runs. The detector loads BOTH function_words (46,
    /// lowercased) AND strong_chars (a-ring U+00E5 / U+00C5) from
    /// sv_function_words.json. Strong indicators (sufficient): a-ring char
    /// OR an exact function-word match. Weak chars a-diaeresis (U+00E4) /
    /// o-diaeresis (U+00F6) are NOT sufficient alone (shared with German).
    /// </summary>
    private static UnicodeLanguageDetector MakeSvDetector()
        => new(new[] { "en", "sv" }, defaultLatinLanguage: "en");

    /// <summary>Does any segment of <paramref name="text"/> classify as Swedish?</summary>
    private static bool ContainsSwedish(UnicodeLanguageDetector det, string text)
    {
        foreach ((string lang, string _) in det.SegmentText(text))
        {
            if (lang == "sv")
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>Strong-char (a-ring) path: "så" stays Swedish.</summary>
    [Fact]
    public void Swedish_StrongChar_Sa_IsSwedish()
    {
        Assert.True(ContainsSwedish(MakeSvDetector(), "så"));
    }

    /// <summary>Strong-char (a-ring) path: "från" stays Swedish.</summary>
    [Fact]
    public void Swedish_StrongChar_Fran_IsSwedish()
    {
        Assert.True(ContainsSwedish(MakeSvDetector(), "från"));
    }

    /// <summary>
    /// Function-word path: exact matches stay Swedish even when the word
    /// contains only weak chars (för/när/är) or no special chars (och/jag).
    /// "är" is the new 46th word added in this change.
    /// </summary>
    [Theory]
    [InlineData("och")]
    [InlineData("jag")]
    [InlineData("inte")]
    [InlineData("för")]
    [InlineData("när")]
    [InlineData("är")]
    public void Swedish_FunctionWord_IsSwedish(string word)
    {
        Assert.True(ContainsSwedish(MakeSvDetector(), word));
    }

    /// <summary>
    /// CONSERVATIVE FLIP: "Mädchen" (German) — a-diaeresis is weak and not
    /// a function word, so it must NOT be Swedish. (Was sv under the OLD
    /// lenient policy where ä/ö counted as strong.)
    /// </summary>
    [Fact]
    public void Swedish_Madchen_IsNotSwedish()
    {
        Assert.False(ContainsSwedish(MakeSvDetector(), "Mädchen"));
    }

    /// <summary>
    /// CONSERVATIVE FLIP: "schön" (German) — o-diaeresis is weak and not a
    /// function word -> NOT sv. (Was sv under the OLD lenient policy.)
    /// </summary>
    [Fact]
    public void Swedish_Schon_IsNotSwedish()
    {
        Assert.False(ContainsSwedish(MakeSvDetector(), "schön"));
    }

    /// <summary>Weak-char invariant: "wörter" (o-diaeresis only) is NOT Swedish.</summary>
    [Fact]
    public void Swedish_Worter_IsNotSwedish()
    {
        Assert.False(ContainsSwedish(MakeSvDetector(), "wörter"));
    }

    /// <summary>Weak-char invariant: "xöx" (o-diaeresis only) is NOT Swedish.</summary>
    [Fact]
    public void Swedish_Xox_IsNotSwedish()
    {
        Assert.False(ContainsSwedish(MakeSvDetector(), "xöx"));
    }

    /// <summary>
    /// Gate: with languages ["en","es"] (no sv), the post-pass does not run,
    /// so "från" is NOT reclassified Swedish.
    /// </summary>
    [Fact]
    public void Swedish_NotDetected_WhenSvAbsent()
    {
        var det = new UnicodeLanguageDetector(new[] { "en", "es" }, defaultLatinLanguage: "en");
        Assert.False(ContainsSwedish(det, "från"));
    }

    /// <summary>
    /// Multi-word reclassification: "jag heter Anna" — "jag" is a function
    /// word, so the whole default-Latin segment becomes Swedish.
    /// </summary>
    [Fact]
    public void Swedish_Sentence_IsSwedish()
    {
        Assert.True(ContainsSwedish(MakeSvDetector(), "jag heter Anna"));
    }
}
