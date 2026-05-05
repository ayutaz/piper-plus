using PiperPlus.Core.Mapping;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="SwedishPhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> stress marker handling ->
/// word boundary spaces -> punctuation -> prosody alignment ->
/// PostProcessIds BOS/EOS/PAD, PUA mapping for long vowels, and
/// Swedish language detection, using a stubbed <see cref="ISwedishG2PEngine"/>.
/// </summary>
public sealed class SwedishPhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubSwedishG2PEngine : ISwedishG2PEngine
    {
        private readonly List<string> _tokens;
        public StubSwedishG2PEngine(List<string> tokens) => _tokens = tokens;
        public List<string> ToPhonemeList(string text) => _tokens;
    }

    // ================================================================
    // Shared phoneme ID map for PostProcessIds tests
    // ================================================================

    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],
        ["^"] = [1],
        ["$"] = [2],
        [" "] = [3],
        ["h"] = [10],
        ["e"] = [11],
        ["j"] = [12],
        ["\u02c8"] = [20], // U+02C8 primary stress marker
        ["\u02cc"] = [21], // U+02CC secondary stress marker
        ["k"] = [30],
        ["m"] = [31],
    };

    // ================================================================
    // 1. PrimaryStressMarker_InOutput
    // ================================================================

    [Fact]
    public void PrimaryStressMarker_InOutput()
    {
        // "hej" -> U+02C8 h e j
        // The primary stress marker should be present in the output tokens.
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("hej");

        Assert.Contains("\u02c8", result); // primary stress marker present
    }

    // ================================================================
    // 2. PrimaryStressMarker_A2_Is2
    // ================================================================

    [Fact]
    public void PrimaryStressMarker_A2_Is2()
    {
        // The primary stress marker itself should receive A2=2.
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej");

        int idx = result.IndexOf("\u02c8");
        Assert.True(idx >= 0, "Primary stress marker should be present");
        Assert.NotNull(prosody[idx]);
        Assert.Equal(2, prosody[idx]!.Value.A2);
    }

    // ================================================================
    // 3. SecondaryStressMarker_A2_Is1
    // ================================================================

    [Fact]
    public void SecondaryStressMarker_A2_Is1()
    {
        // The secondary stress marker U+02CC should receive A2=1.
        var tokens = new List<string> { "\u02cc", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej");

        int idx = result.IndexOf("\u02cc");
        Assert.True(idx >= 0, "Secondary stress marker should be present");
        Assert.NotNull(prosody[idx]);
        Assert.Equal(1, prosody[idx]!.Value.A2);
    }

    // ================================================================
    // 4. UnstressedPhoneme_A2_Is0
    // ================================================================

    [Fact]
    public void UnstressedPhoneme_A2_Is0()
    {
        // In "U+02C8 h e j", phonemes h/e/j are NOT stress markers
        // and should have A2=0.
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej");

        // Find "h" -- it should be unstressed.
        int hIdx = result.IndexOf("h");
        Assert.True(hIdx >= 0, "'h' should be present");
        Assert.NotNull(prosody[hIdx]);
        Assert.Equal(0, prosody[hIdx]!.Value.A2);

        // Find "e" -- it should be unstressed.
        int eIdx = result.IndexOf("e");
        Assert.True(eIdx >= 0, "'e' should be present");
        Assert.NotNull(prosody[eIdx]);
        Assert.Equal(0, prosody[eIdx]!.Value.A2);

        // Find "j" -- it should be unstressed.
        int jIdx = result.IndexOf("j");
        Assert.True(jIdx >= 0, "'j' should be present");
        Assert.NotNull(prosody[jIdx]);
        Assert.Equal(0, prosody[jIdx]!.Value.A2);
    }

    // ================================================================
    // 5. A1_AlwaysZero
    // ================================================================

    [Fact]
    public void A1_AlwaysZero()
    {
        // A1 should always be 0 for all tokens in Swedish phonemizer.
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("hej");

        foreach (var p in prosody)
        {
            Assert.NotNull(p);
            Assert.Equal(0, p!.Value.A1);
        }
    }

    // ================================================================
    // 6. A3_IsWordPhonemeCount_ExcludingStressMarkers
    // ================================================================

    [Fact]
    public void A3_IsWordPhonemeCount_ExcludingStressMarkers()
    {
        // "hej" -> U+02C8 h e j
        // A3 = phoneme count excluding stress markers = 3 (h, e, j).
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("hej");

        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.Value.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values); // all tokens in the word share the same A3
        Assert.Equal(3, a3Values[0]);
    }

    // ================================================================
    // 7. A3_MultipleStressMarkers_Excluded
    // ================================================================

    [Fact]
    public void A3_MultipleStressMarkers_Excluded()
    {
        // Word with both primary and secondary stress: U+02C8 h U+02CC e j
        // A3 = phoneme count excluding both stress markers = 3 (h, e, j).
        var tokens = new List<string> { "\u02c8", "h", "\u02cc", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("test");

        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.Value.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values);
        Assert.Equal(3, a3Values[0]);
    }

    // ================================================================
    // 8. WordBoundary_Spaces
    // ================================================================

    [Fact]
    public void WordBoundary_Spaces()
    {
        // "hej alla" -> U+02C8 h e j <space> U+02C8 a l a
        var tokens = new List<string>
        {
            "\u02c8", "h", "e", "j",
            " ",
            "\u02c8", "a", "l", "a",
        };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("hej alla");

        Assert.Contains(" ", result);
    }

    // ================================================================
    // 9. Punctuation_HasZeroProsody
    // ================================================================

    [Fact]
    public void Punctuation_HasZeroProsody()
    {
        // Punctuation tokens should receive ProsodyInfo(0, 0, 0).
        var tokens = new List<string>
        {
            "\u02c8", "h", "e", "j",
            ",",
        };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej,");

        int commaIdx = result.IndexOf(",");
        Assert.True(commaIdx >= 0, "Comma should be present");
        Assert.NotNull(prosody[commaIdx]);
        Assert.Equal(0, prosody[commaIdx]!.Value.A1);
        Assert.Equal(0, prosody[commaIdx]!.Value.A2);
        Assert.Equal(0, prosody[commaIdx]!.Value.A3);
    }

    // ================================================================
    // 10. SpaceBoundary_HasZeroProsody
    // ================================================================

    [Fact]
    public void SpaceBoundary_HasZeroProsody()
    {
        // Space boundary tokens should receive ProsodyInfo(0, 0, 0).
        var tokens = new List<string>
        {
            "\u02c8", "h", "e", "j",
            " ",
            "k",
        };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej k");

        int spaceIdx = result.IndexOf(" ");
        Assert.True(spaceIdx >= 0, "Space should be present");
        Assert.NotNull(prosody[spaceIdx]);
        Assert.Equal(0, prosody[spaceIdx]!.Value.A1);
        Assert.Equal(0, prosody[spaceIdx]!.Value.A2);
        Assert.Equal(0, prosody[spaceIdx]!.Value.A3);
    }

    // ================================================================
    // 11. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // tokens.Count must equal prosody.Count for multi-word input.
        var tokens = new List<string>
        {
            "\u02c8", "h", "e", "j",
            " ",
            "m", "e", "j",
            ".",
        };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej mej.");

        Assert.Equal(result.Count, prosody.Count);
    }

    // ================================================================
    // 12. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var phonemizer = new SwedishPhonemizer(
            new StubSwedishG2PEngine([]));

        // Swedish models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 13. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var phonemizer = new SwedishPhonemizer(
            new StubSwedishG2PEngine([]));

        // Input: three phoneme IDs (h, e, j).
        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 3), new(0, 0, 3), new(0, 0, 3),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected:
        // BOS(1), PAD(0), 10, PAD(0), 11, PAD(0), 12, PAD(0), EOS(2)
        // = [1, 0, 10, 0, 11, 0, 12, 0, 2]
        Assert.Equal([1, 0, 10, 0, 11, 0, 12, 0, 2], ids);

        // IDs and prosody must have the same length.
        Assert.Equal(ids.Count, prosody.Count);

        // BOS and EOS positions should have null prosody.
        Assert.Null(prosody[0]);   // BOS
        Assert.Null(prosody[^1]);  // EOS
    }

    // ================================================================
    // 14. PostProcessIds_SkipsPadAfterPadToken
    // ================================================================

    [Fact]
    public void PostProcessIds_SkipsPadAfterPadToken()
    {
        var phonemizer = new SwedishPhonemizer(
            new StubSwedishG2PEngine([]));

        // Input: [10, 0, 11] where 0 is PAD. No double-PAD should be inserted.
        var inputIds = new List<int> { 10, 0, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 3), null, new(0, 0, 3),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected:
        // BOS(1), PAD(0), 10, PAD(0), 0, 11, PAD(0), EOS(2)
        // = [1, 0, 10, 0, 0, 11, 0, 2]
        Assert.Equal([1, 0, 10, 0, 0, 11, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 15. PostProcessIds_EmptyInput
    // ================================================================

    [Fact]
    public void PostProcessIds_EmptyInput()
    {
        var phonemizer = new SwedishPhonemizer(
            new StubSwedishG2PEngine([]));

        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Empty input -> BOS(1), PAD(0), EOS(2) only.
        Assert.Equal([1, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 16. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        // Phonemize() should return the same tokens as PhonemizeWithProsody().
        var tokens = new List<string> { "\u02c8", "h", "e", "j" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var plain = phonemizer.Phonemize("hej");
        var (withProsody, _) = phonemizer.PhonemizeWithProsody("hej");

        Assert.Equal(withProsody, plain);
    }

    // ================================================================
    // 17. PhonemizeWithProsody_EmptyInput
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyInput()
    {
        // Engine returns empty list -> empty phonemes and prosody.
        var phonemizer = new SwedishPhonemizer(
            new StubSwedishG2PEngine([]));

        var (result, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(result);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 18. MultiWord_A3_PerWord
    // ================================================================

    [Fact]
    public void MultiWord_A3_PerWord()
    {
        // Two words: "hej" (3 phonemes) and "ja" (2 phonemes).
        // A3 should differ per word.
        var tokens = new List<string>
        {
            "\u02c8", "h", "e", "j",   // word 1: A3=3 (h, e, j)
            " ",
            "\u02c8", "j", "a",         // word 2: A3=2 (j, a)
        };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej ja");

        // First word tokens should have A3=3.
        int hIdx = result.IndexOf("h");
        Assert.Equal(3, prosody[hIdx]!.Value.A3);

        // Second word: find "a" (only in second word).
        int aIdx = result.IndexOf("a");
        Assert.Equal(2, prosody[aIdx]!.Value.A3);
    }

    // ================================================================
    // 19. AllPunctuationTypes
    // ================================================================

    [Theory]
    [InlineData(".")]
    [InlineData(",")]
    [InlineData(";")]
    [InlineData(":")]
    [InlineData("!")]
    [InlineData("?")]
    public void AllPunctuationTypes_ZeroProsody(string punct)
    {
        // Each punctuation character should have A1=0, A2=0, A3=0.
        var tokens = new List<string> { "h", "e", "j", punct };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hej" + punct);

        int idx = result.IndexOf(punct);
        Assert.True(idx >= 0, $"Punctuation '{punct}' should be present");
        Assert.NotNull(prosody[idx]);
        Assert.Equal(0, prosody[idx]!.Value.A1);
        Assert.Equal(0, prosody[idx]!.Value.A2);
        Assert.Equal(0, prosody[idx]!.Value.A3);
    }

    // ================================================================
    // 20. PrimaryStressMarker_AtEndOfWord
    // ================================================================

    [Fact]
    public void PrimaryStressMarker_AtEndOfWord()
    {
        // Stress marker at the end of a word (unusual but possible).
        // It still receives A2=2 and A3 = phoneme count excluding markers.
        var tokens = new List<string> { "h", "e", "\u02c8" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("he");

        int stressIdx = result.IndexOf("\u02c8");
        Assert.True(stressIdx >= 0, "Stress marker should be present");
        Assert.NotNull(prosody[stressIdx]);
        Assert.Equal(2, prosody[stressIdx]!.Value.A2);
        Assert.Equal(2, prosody[stressIdx]!.Value.A3); // h, e = 2 phonemes
    }

    // ================================================================
    // 21. LongVowel_PuaMapped
    // ================================================================

    [Fact]
    public void LongVowel_PuaMapped()
    {
        // Long vowel "i\u02D0" should be PUA-mapped to U+E059.
        var tokens = new List<string> { "\u02c8", "l", "i\u02D0", "v" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("liv");

        // The multi-character token "i\u02D0" should be replaced with PUA U+E059.
        Assert.Contains("\uE059", result);
        Assert.DoesNotContain("i\u02D0", result);
    }

    // ================================================================
    // 22. LongVowel_ProsodyPreservedAfterMapping
    // ================================================================

    [Fact]
    public void LongVowel_ProsodyPreservedAfterMapping()
    {
        // Prosody alignment must still hold after PUA mapping.
        var tokens = new List<string> { "\u02c8", "l", "i\u02D0", "v" };

        var phonemizer = new SwedishPhonemizer(new StubSwedishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("liv");

        Assert.Equal(result.Count, prosody.Count);
    }

    // ================================================================
    // 23. NullEngine_ThrowsArgumentNull
    // ================================================================

    [Fact]
    public void NullEngine_ThrowsArgumentNull()
    {
        Assert.Throws<ArgumentNullException>(() => new SwedishPhonemizer(null!));
    }

    // ================================================================
    // PUA Mapping Tests (Swedish long vowels)
    // ================================================================

    // ================================================================
    // 24. PuaMapping_All9SvLongVowels_Exist
    // ================================================================

    [Fact]
    public void PuaMapping_All9SvLongVowels_Exist()
    {
        // Verify all 9 SV long vowel PUA entries exist in OpenJTalkToPiperMapping.
        var map = OpenJTalkToPiperMapping.TokenToChar;

        Assert.True(map.ContainsKey("i\u02D0"), "Missing: i\u02D0 (long i)");
        Assert.True(map.ContainsKey("y\u02D0"), "Missing: y\u02D0 (long y)");
        Assert.True(map.ContainsKey("e\u02D0"), "Missing: e\u02D0 (long e)");
        Assert.True(map.ContainsKey("\u025B\u02D0"), "Missing: \u025B\u02D0 (long open-e)");
        Assert.True(map.ContainsKey("\u00F8\u02D0"), "Missing: \u00F8\u02D0 (long o-slash)");
        Assert.True(map.ContainsKey("\u0251\u02D0"), "Missing: \u0251\u02D0 (long open-a)");
        Assert.True(map.ContainsKey("o\u02D0"), "Missing: o\u02D0 (long o)");
        Assert.True(map.ContainsKey("u\u02D0"), "Missing: u\u02D0 (long u)");
        Assert.True(map.ContainsKey("\u0289\u02D0"), "Missing: \u0289\u02D0 (long barred-u)");
    }

    // ================================================================
    // 25. PuaMapping_SvLongVowels_CorrectCodepoints
    // ================================================================

    [Fact]
    public void PuaMapping_SvLongVowels_CorrectCodepoints()
    {
        // Verify the exact PUA codepoints for all 9 SV long vowels.
        var map = OpenJTalkToPiperMapping.TokenToChar;

        Assert.Equal('\uE059', map["i\u02D0"]);           // long i
        Assert.Equal('\uE05A', map["y\u02D0"]);           // long y
        Assert.Equal('\uE05B', map["e\u02D0"]);           // long e
        Assert.Equal('\uE05C', map["\u025B\u02D0"]);      // long open-e
        Assert.Equal('\uE05D', map["\u00F8\u02D0"]);      // long o-slash
        Assert.Equal('\uE05E', map["\u0251\u02D0"]);      // long open-a
        Assert.Equal('\uE05F', map["o\u02D0"]);           // long o
        Assert.Equal('\uE060', map["u\u02D0"]);           // long u
        Assert.Equal('\uE061', map["\u0289\u02D0"]);      // long barred-u
    }

    // ================================================================
    // 26. PuaMapping_SvRange_U_E059_to_U_E061
    // ================================================================

    [Fact]
    public void PuaMapping_SvRange_U_E059_to_U_E061()
    {
        // The SV PUA range must be contiguous from U+E059 to U+E061.
        var reverseMap = OpenJTalkToPiperMapping.CharToToken;

        for (char c = '\uE059'; c <= '\uE061'; c++)
        {
            Assert.True(reverseMap.ContainsKey(c),
                $"Missing reverse mapping for U+{(int)c:X4}");
        }
    }

    // ================================================================
    // 27. PuaMapping_TotalCount_Is99
    // ================================================================

    [Fact]
    public void PuaMapping_TotalCount_Is99()
    {
        // PUA v2: 29 JA + 2 shared + 43 ZH + 8 KO + 2 ES/PT + 3 FR + 9 SV + 3 multi-CP v2 = 99
        Assert.Equal(99, OpenJTalkToPiperMapping.TokenToChar.Count);
    }

    // ================================================================
    // 28. PuaMapping_ReverseCount_Matches
    // ================================================================

    [Fact]
    public void PuaMapping_ReverseCount_Matches()
    {
        // Forward and reverse maps must have the same entry count.
        Assert.Equal(
            OpenJTalkToPiperMapping.TokenToChar.Count,
            OpenJTalkToPiperMapping.CharToToken.Count);
    }

    // ================================================================
    // UnicodeLanguageDetector Swedish detection tests
    // ================================================================

    // ================================================================
    // 29. SwedishDetection_TextWithADiaeresis
    // ================================================================

    [Fact]
    public void SwedishDetection_TextWithADiaeresis()
    {
        // Text containing a-diaeresis (U+00E4) should be detected as Swedish
        // when sv is in the language set alongside en.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("Det \u00E4r bra");  // "Det ar bra" with a-diaeresis

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 30. SwedishDetection_TextWithORing
    // ================================================================

    [Fact]
    public void SwedishDetection_TextWithORing()
    {
        // Text containing a-ring (U+00E5) should be detected as Swedish.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("G\u00E5 till parken");  // "Ga till parken" with a-ring

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 31. SwedishDetection_TextWithODiaeresis
    // ================================================================

    [Fact]
    public void SwedishDetection_TextWithODiaeresis()
    {
        // Text containing o-diaeresis (U+00F6) should be detected as Swedish.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("H\u00F6r du mig");  // "Hor du mig" with o-diaeresis

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 32. SwedishDetection_FunctionWord_Och
    // ================================================================

    [Fact]
    public void SwedishDetection_FunctionWord_Och()
    {
        // "och" is a Swedish function word that should trigger sv detection.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("katten och hunden");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 33. SwedishDetection_FunctionWord_Jag
    // ================================================================

    [Fact]
    public void SwedishDetection_FunctionWord_Jag()
    {
        // "jag" is a Swedish function word.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("jag tycker om det");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 34. SwedishDetection_EnglishText_NotSwedish
    // ================================================================

    [Fact]
    public void SwedishDetection_EnglishText_NotSwedish()
    {
        // Plain English text without any Swedish indicators should remain "en".
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("Hello, how are you today?");

        Assert.Single(segments);
        Assert.Equal("en", segments[0].Lang);
    }

    // ================================================================
    // 35. SwedishDetection_NoSvInLanguages_NoRefinement
    // ================================================================

    [Fact]
    public void SwedishDetection_NoSvInLanguages_NoRefinement()
    {
        // When sv is NOT in the language set, text with Swedish chars
        // should remain the default Latin language.
        var detector = new UnicodeLanguageDetector(
            ["en", "fr"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("Det \u00E4r bra");

        Assert.Single(segments);
        Assert.Equal("en", segments[0].Lang);
    }

    // ================================================================
    // 36. SwedishDetection_SvOnly_NoRefinement
    // ================================================================

    [Fact]
    public void SwedishDetection_SvOnly_NoRefinement()
    {
        // When sv is the ONLY Latin language, _detectSwedish is false
        // (latinLangCount < 2), so no refinement occurs.
        // But sv is default Latin -> all Latin maps to "sv" directly.
        var detector = new UnicodeLanguageDetector(
            ["ja", "sv"], defaultLatinLanguage: "sv");

        var segments = detector.SegmentText("hej alla");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 37. SwedishDetection_UppercaseChars
    // ================================================================

    [Fact]
    public void SwedishDetection_UppercaseChars()
    {
        // Uppercase Swedish characters should also trigger detection.
        // U+00C4 = A-diaeresis, U+00C5 = A-ring, U+00D6 = O-diaeresis
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("\u00C4ven om det regnar");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 38. SwedishDetection_MultipleFunctionWords
    // ================================================================

    [Fact]
    public void SwedishDetection_MultipleFunctionWords()
    {
        // Text with multiple Swedish function words.
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("han kan inte komma");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }

    // ================================================================
    // 39. SwedishDetection_CaseInsensitiveFunctionWords
    // ================================================================

    [Fact]
    public void SwedishDetection_CaseInsensitiveFunctionWords()
    {
        // Function word matching is case-insensitive ("Och" should match).
        var detector = new UnicodeLanguageDetector(
            ["en", "sv"], defaultLatinLanguage: "en");

        var segments = detector.SegmentText("Och det var bra");

        Assert.Single(segments);
        Assert.Equal("sv", segments[0].Lang);
    }
}

// ====================================================================
// SwedishG2PEngine unit tests
// ====================================================================

/// <summary>
/// Tests for <see cref="SwedishG2PEngine"/>: verifies the full rule-based
/// G2P pipeline including consonant rules, vowel length, retroflex
/// assimilation, stress placement, loanword suffixes, and function words.
/// </summary>
public sealed class SwedishG2PEngineTests
{
    private readonly SwedishG2PEngine _engine = new();

    // Helper: extract just phoneme tokens (no spaces/punctuation) from output.
    private List<string> PhonemeTokens(List<string> tokens)
    {
        return tokens.Where(t => t != " " && t.Length == 1 && ".,:;!?".Contains(t[0]) == false
            || t.Length > 1
            || (t.Length == 1 && !".,:;!?".Contains(t[0]) && t != " ")).ToList();
    }

    // ================================================================
    // 1. Consonant rules: soft k before front vowel
    // ================================================================

    [Fact]
    public void SoftK_BeforeFrontVowel_ProducesAlveopalatal()
    {
        // "köpa" -> k before ö (front vowel) = /ɕ/ (soft)
        // köpa is NOT in HardKWords
        var tokens = _engine.ToPhonemeList("köpa");
        Assert.Contains("\u0255", tokens);  // ɕ
    }

    // ================================================================
    // 2. Consonant rules: hard k exception word
    // ================================================================

    [Fact]
    public void HardK_ExceptionWord_ProducesK()
    {
        // "kille" is in HardKWords -> hard /k/ before front vowel
        var tokens = _engine.ToPhonemeList("kille");
        // Should have "k" but not "\u0255"
        Assert.Contains("k", tokens);
        Assert.DoesNotContain("\u0255", tokens);
    }

    // ================================================================
    // 3. Consonant rules: soft g before front vowel
    // ================================================================

    [Fact]
    public void SoftG_BeforeFrontVowel_ProducesJ()
    {
        // "göra" -> g before ö (front vowel) = /j/ (soft)
        // göra is NOT in HardGWords
        var tokens = _engine.ToPhonemeList("göra");
        // First phoneme should be "j" (not "ɡ")
        // Filter out stress markers
        var filtered = tokens.Where(t => t != "\u02c8" && t != "\u02cc").ToList();
        Assert.Equal("j", filtered[0]);
    }

    // ================================================================
    // 4. Consonant rules: hard g exception word
    // ================================================================

    [Fact]
    public void HardG_ExceptionWord_ProducesG()
    {
        // "ger" is in HardGWords -> hard /ɡ/ before front vowel
        var tokens = _engine.ToPhonemeList("ger");
        Assert.Contains("\u0261", tokens);  // ɡ
    }

    // ================================================================
    // 5. Hard g -era verb heuristic
    // ================================================================

    [Fact]
    public void HardG_EraVerbHeuristic()
    {
        // Words ending in -era get hard g (e.g. navigera)
        var tokens = _engine.ToPhonemeList("navigera");
        // The g before e should be hard /ɡ/
        Assert.Contains("\u0261", tokens);
    }

    // ================================================================
    // 6. Digraph: sj -> /ɧ/
    // ================================================================

    [Fact]
    public void Digraph_Sj_ProducesFricative()
    {
        // "sjö" -> sj = /ɧ/
        var tokens = _engine.ToPhonemeList("sjö");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 7. Digraph: tj -> /ɕ/
    // ================================================================

    [Fact]
    public void Digraph_Tj_ProducesTjSound()
    {
        // "tjugo" -> tj = /ɕ/
        var tokens = _engine.ToPhonemeList("tjugo");
        Assert.Contains("\u0255", tokens);  // ɕ
    }

    // ================================================================
    // 8. Digraph: ng -> /ŋ/
    // ================================================================

    [Fact]
    public void Digraph_Ng_ProducesVelarNasal()
    {
        // "ring" -> ng = /ŋ/
        var tokens = _engine.ToPhonemeList("ring");
        Assert.Contains("\u014b", tokens);  // ŋ
    }

    // ================================================================
    // 9. Digraph: sk before front vowel -> /ɧ/
    // ================================================================

    [Fact]
    public void Digraph_Sk_BeforeFrontVowel_ProducesFricative()
    {
        // "sked" -> sk + e (front) = /ɧ/
        var tokens = _engine.ToPhonemeList("sked");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 10. Digraph: sk before back vowel -> /sk/
    // ================================================================

    [Fact]
    public void Digraph_Sk_BeforeBackVowel_ProducesSK()
    {
        // "skog" -> sk + o (back) = /sk/
        var tokens = _engine.ToPhonemeList("skog");
        Assert.Contains("s", tokens);
        Assert.Contains("k", tokens);
    }

    // ================================================================
    // 11. Trigraph: skj -> /ɧ/
    // ================================================================

    [Fact]
    public void Trigraph_Skj_ProducesFricative()
    {
        var tokens = _engine.ToPhonemeList("skjorta");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 12. Trigraph: stj -> /ɧ/
    // ================================================================

    [Fact]
    public void Trigraph_Stj_ProducesFricative()
    {
        var tokens = _engine.ToPhonemeList("stjärna");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 13. Digraph: ch -> /ɧ/ (default) or /k/ (exception)
    // ================================================================

    [Fact]
    public void Digraph_Ch_Default_ProducesFricative()
    {
        // "check" -> ch = /ɧ/ (not in CH_EXCEPTIONS_K)
        var tokens = _engine.ToPhonemeList("check");
        Assert.Contains("\u0267", tokens);
    }

    [Fact]
    public void Digraph_Ch_Exception_ProducesK()
    {
        // "och" is in ChExceptionsK -> ch = /k/
        var tokens = _engine.ToPhonemeList("och");
        Assert.Contains("k", tokens);
        Assert.DoesNotContain("\u0267", tokens);
    }

    // ================================================================
    // 14. Digraph: nk -> /ŋk/
    // ================================================================

    [Fact]
    public void Digraph_Nk_ProducesVelarNasalPlusK()
    {
        var tokens = _engine.ToPhonemeList("bank");
        Assert.Contains("\u014b", tokens);
        Assert.Contains("k", tokens);
    }

    // ================================================================
    // 15. Digraph: ck -> /k/
    // ================================================================

    [Fact]
    public void Digraph_Ck_ProducesK()
    {
        var tokens = _engine.ToPhonemeList("bäck");
        Assert.Contains("k", tokens);
    }

    // ================================================================
    // 16. Digraph: gn initial -> /ɡn/, medial -> /ŋn/
    // ================================================================

    [Fact]
    public void Digraph_Gn_Initial_ProducesGN()
    {
        var tokens = _engine.ToPhonemeList("gnaga");
        var filtered = tokens.Where(t => t != "\u02c8").ToList();
        // gn at position 0 -> ɡ n
        Assert.Equal("\u0261", filtered[0]);  // ɡ
        Assert.Equal("n", filtered[1]);
    }

    [Fact]
    public void Digraph_Gn_Medial_ProducesVelarN()
    {
        // "vagn" -> gn not at position 0 -> /ŋn/
        var tokens = _engine.ToPhonemeList("vagn");
        Assert.Contains("\u014b", tokens);  // ŋ
    }

    // ================================================================
    // 17. Word-initial digraphs: gj, lj, dj, hj -> /j/
    // ================================================================

    [Theory]
    [InlineData("gjord")]
    [InlineData("ljus")]
    [InlineData("djur")]
    [InlineData("hjälp")]
    public void WordInitialDigraph_ProducesJ(string word)
    {
        var tokens = _engine.ToPhonemeList(word);
        var filtered = tokens.Where(t => t != "\u02c8").ToList();
        Assert.Equal("j", filtered[0]);
    }

    // ================================================================
    // 18. Vowel length: long vowel with single consonant
    // ================================================================

    [Fact]
    public void VowelLength_SingleConsonant_LongVowel()
    {
        // "mat" -> 'a' + single 't' -> long ɑː
        var tokens = _engine.ToPhonemeList("mat");
        Assert.Contains("\u0251\u02d0", tokens);  // ɑː
    }

    // ================================================================
    // 19. Vowel length: short vowel with consonant cluster
    // ================================================================

    [Fact]
    public void VowelLength_ConsonantCluster_ShortVowel()
    {
        // "katt" -> a + tt (2 consonants) -> short 'a'
        var tokens = _engine.ToPhonemeList("katt");
        Assert.Contains("a", tokens);
        Assert.DoesNotContain("\u0251\u02d0", tokens);
    }

    // ================================================================
    // 20. Vowel length: word-final vowel -> long
    // ================================================================

    [Fact]
    public void VowelLength_WordFinal_LongVowel()
    {
        // "bo" -> o in O_LONG_AS_OO + word-final -> oː
        var tokens = _engine.ToPhonemeList("bo");
        Assert.Contains("o\u02d0", tokens);
    }

    // ================================================================
    // 21. Vowel length: O_LONG_AS_OO
    // ================================================================

    [Fact]
    public void VowelLength_OLongAsOo_ProducesLongO()
    {
        // "son" -> o + single n AND in O_LONG_AS_OO -> oː (not uː)
        var tokens = _engine.ToPhonemeList("son");
        Assert.Contains("o\u02d0", tokens);
        Assert.DoesNotContain("u\u02d0", tokens);
    }

    // ================================================================
    // 22. Vowel length: default o (not in O_LONG_AS_OO) -> uː
    // ================================================================

    [Fact]
    public void VowelLength_DefaultO_ProducesLongU()
    {
        // "bok" -> o + single k AND not in O_LONG_AS_OO -> uː
        var tokens = _engine.ToPhonemeList("bok");
        Assert.Contains("u\u02d0", tokens);
    }

    // ================================================================
    // 23. Vowel length: FinalMShortWords
    // ================================================================

    [Fact]
    public void VowelLength_FinalMShort_ProducesShortVowel()
    {
        // "hem" is in FinalMShortWords -> short vowel despite single consonant
        var tokens = _engine.ToPhonemeList("hem");
        // 'e' -> short ɛ
        Assert.Contains("\u025b", tokens);
        Assert.DoesNotContain("e\u02d0", tokens);
    }

    // ================================================================
    // 24. Function words: no stress marker
    // ================================================================

    [Fact]
    public void FunctionWord_NoStressMarker()
    {
        // "och" is a function word -> stress_syl = -1 -> no stress marker
        var tokens = _engine.ToPhonemeList("och");
        Assert.DoesNotContain("\u02c8", tokens);
        Assert.DoesNotContain("\u02cc", tokens);
    }

    // ================================================================
    // 25. Function words: short vowel
    // ================================================================

    [Fact]
    public void FunctionWord_ShortVowel()
    {
        // "du" is a function word -> short vowel
        var tokens = _engine.ToPhonemeList("du");
        // 'u' short = /ɵ/
        Assert.Contains("\u0275", tokens);
    }

    // ================================================================
    // 26. Retroflex assimilation: r+t -> /ʈ/
    // ================================================================

    [Fact]
    public void Retroflex_RT_ProducesRetroflexT()
    {
        // "kort" -> r+t -> /ʈ/
        var tokens = _engine.ToPhonemeList("kort");
        Assert.Contains("\u0288", tokens);  // ʈ
    }

    // ================================================================
    // 27. Retroflex assimilation: r+d -> /ɖ/
    // ================================================================

    [Fact]
    public void Retroflex_RD_ProducesRetroflexD()
    {
        // "bord" -> r+d -> /ɖ/
        var tokens = _engine.ToPhonemeList("bord");
        Assert.Contains("\u0256", tokens);  // ɖ
    }

    // ================================================================
    // 28. Retroflex assimilation: r+s -> /ʂ/
    // ================================================================

    [Fact]
    public void Retroflex_RS_ProducesRetroflexS()
    {
        // "mars" -> r+s -> /ʂ/
        var tokens = _engine.ToPhonemeList("mars");
        Assert.Contains("\u0282", tokens);  // ʂ
    }

    // ================================================================
    // 29. Retroflex assimilation: r+n -> /ɳ/
    // ================================================================

    [Fact]
    public void Retroflex_RN_ProducesRetroflexN()
    {
        // "barn" -> r+n -> /ɳ/
        var tokens = _engine.ToPhonemeList("barn");
        Assert.Contains("\u0273", tokens);  // ɳ
    }

    // ================================================================
    // 30. Retroflex assimilation: r+l -> /ɭ/
    // ================================================================

    [Fact]
    public void Retroflex_RL_ProducesRetroflexL()
    {
        // "karl" -> r+l -> /ɭ/
        var tokens = _engine.ToPhonemeList("karl");
        Assert.Contains("\u026d", tokens);  // ɭ
    }

    // ================================================================
    // 31. Retroflex: rr blocks assimilation
    // ================================================================

    [Fact]
    public void Retroflex_RR_BlocksAssimilation()
    {
        // Test apply_retroflex directly: ["r","r","t"] -> ["r","r","t"]
        var input = new List<string> { "r", "r", "t" };
        var result = SwedishG2PEngine.ApplyRetroflex(input);
        Assert.Equal(new List<string> { "r", "r", "t" }, result);
    }

    // ================================================================
    // 32. Retroflex cascade: r+t+s -> /ʈ/ /ʂ/
    // ================================================================

    [Fact]
    public void Retroflex_Cascade_RTS()
    {
        // Cascade: r+t -> ʈ (propagating), then t+s -> ʂ
        var input = new List<string> { "r", "t", "s" };
        var result = SwedishG2PEngine.ApplyRetroflex(input);
        Assert.Equal(new List<string> { "\u0288", "\u0282" }, result);
    }

    // ================================================================
    // 33. Retroflex: ɭ stops cascade
    // ================================================================

    [Fact]
    public void Retroflex_ReflexL_StopsCascade()
    {
        // r+l -> ɭ (non-propagating), then next consonant should NOT be retroflex
        var input = new List<string> { "r", "l", "t" };
        var result = SwedishG2PEngine.ApplyRetroflex(input);
        // ɭ stops cascade, so t stays as t
        Assert.Equal(new List<string> { "\u026d", "t" }, result);
    }

    // ================================================================
    // 34. Stress: monosyllabic word gets stress on syllable 0
    // ================================================================

    [Fact]
    public void Stress_Monosyllabic_SyllableZero()
    {
        // "hej" is monosyllabic -> stress on syllable 0
        var tokens = _engine.ToPhonemeList("hej");
        Assert.Contains("\u02c8", tokens);
        // Stress marker should be at the beginning
        Assert.Equal("\u02c8", tokens[0]);
    }

    // ================================================================
    // 35. Stress: stress-attracting suffix
    // ================================================================

    [Fact]
    public void Stress_AttractingSuffix_Tion()
    {
        // "station" -> -tion is stress-attracting
        var tokens = _engine.ToPhonemeList("station");
        Assert.Contains("\u02c8", tokens);
    }

    // ================================================================
    // 36. Stress: unstressed prefix
    // ================================================================

    [Fact]
    public void Stress_UnstressedPrefix_Foer()
    {
        // "förstå" -> "för" is unstressed prefix -> stress on 2nd syllable
        int stressSyl = SwedishG2PEngine.DetectStress("förstå");
        Assert.Equal(1, stressSyl);
    }

    // ================================================================
    // 37. Stress: default first syllable
    // ================================================================

    [Fact]
    public void Stress_DefaultFirstSyllable()
    {
        // "vatten" has 2 syllables, no special suffix/prefix -> stress on 0
        int stressSyl = SwedishG2PEngine.DetectStress("vatten");
        Assert.Equal(0, stressSyl);
    }

    // ================================================================
    // 38. Stress: function word returns -1
    // ================================================================

    [Fact]
    public void Stress_FunctionWord_ReturnsNegativeOne()
    {
        Assert.Equal(-1, SwedishG2PEngine.DetectStress("jag"));
        Assert.Equal(-1, SwedishG2PEngine.DetectStress("och"));
        Assert.Equal(-1, SwedishG2PEngine.DetectStress("inte"));
    }

    // ================================================================
    // 39. Loanword suffix: -tion
    // ================================================================

    [Fact]
    public void Loanword_Tion_ProducesCorrectPhonemes()
    {
        // "nation" -> stem "na" + suffix -tion -> ɧ uː n
        var tokens = _engine.ToPhonemeList("nation");
        Assert.Contains("\u0267", tokens);    // ɧ
        Assert.Contains("u\u02d0", tokens);   // uː
    }

    // ================================================================
    // 40. Loanword suffix: -age (not native)
    // ================================================================

    [Fact]
    public void Loanword_Age_NonNative_ProducesLoanPhonemes()
    {
        // "garage" is not in AgeNativeWords -> loanword suffix
        var tokens = _engine.ToPhonemeList("garage");
        Assert.Contains("\u0251\u02d0", tokens); // ɑː
        Assert.Contains("\u0267", tokens);        // ɧ
    }

    // ================================================================
    // 41. Loanword suffix: -age (native exception)
    // ================================================================

    [Fact]
    public void Loanword_Age_NativeException_NoLoanPhonemes()
    {
        // "mage" is in AgeNativeWords -> NOT treated as loanword
        var tokens = _engine.ToPhonemeList("mage");
        // Should not have the loanword ɑː ɧ pattern;
        // instead native G2P applies
        Assert.DoesNotContain("\u0267", tokens);
    }

    // ================================================================
    // 42. Loanword suffix: -eur
    // ================================================================

    [Fact]
    public void Loanword_Eur_ProducesCorrectPhonemes()
    {
        // "friseur" -> stem "fris" + suffix -eur -> øː r
        var tokens = _engine.ToPhonemeList("friseur");
        Assert.Contains("\u00f8\u02d0", tokens);  // øː
    }

    // ================================================================
    // 43. Punctuation preserved
    // ================================================================

    [Fact]
    public void Punctuation_Preserved()
    {
        var tokens = _engine.ToPhonemeList("hej!");
        Assert.Contains("!", tokens);
    }

    // ================================================================
    // 44. Word boundaries
    // ================================================================

    [Fact]
    public void WordBoundary_SpaceToken()
    {
        var tokens = _engine.ToPhonemeList("hej alla");
        Assert.Contains(" ", tokens);
    }

    // ================================================================
    // 45. Empty input
    // ================================================================

    [Fact]
    public void EmptyInput_ReturnsEmptyList()
    {
        var tokens = _engine.ToPhonemeList("");
        Assert.Empty(tokens);
    }

    // ================================================================
    // 46. Digraph: ph -> /f/
    // ================================================================

    [Fact]
    public void Digraph_Ph_ProducesF()
    {
        var tokens = _engine.ToPhonemeList("photo");
        Assert.Contains("f", tokens);
    }

    // ================================================================
    // 47. Digraph: th -> /t/
    // ================================================================

    [Fact]
    public void Digraph_Th_ProducesT()
    {
        var tokens = _engine.ToPhonemeList("thema");
        var filtered = tokens.Where(t => t != "\u02c8").ToList();
        Assert.Equal("t", filtered[0]);
    }

    // ================================================================
    // 48. Long vowel: all 9 Swedish long vowels
    // ================================================================

    [Theory]
    [InlineData("mat", "\u0251\u02d0")]   // a -> ɑː
    [InlineData("bok", "u\u02d0")]        // o -> uː (default)
    [InlineData("se", "e\u02d0")]         // e -> eː (word-final)
    public void LongVowel_Produced(string word, string expectedVowel)
    {
        var tokens = _engine.ToPhonemeList(word);
        Assert.Contains(expectedVowel, tokens);
    }

    // ================================================================
    // 49. CountSyllables
    // ================================================================

    [Theory]
    [InlineData("hej", 1)]
    [InlineData("vatten", 2)]
    [InlineData("station", 2)]
    [InlineData("telefon", 3)]
    public void CountSyllables_Correct(string word, int expected)
    {
        Assert.Equal(expected, SwedishG2PEngine.CountSyllables(word));
    }

    // ================================================================
    // 50. r + C exception preserves long vowel
    // ================================================================

    [Fact]
    public void VowelLength_RPlusSingleC_LongVowel()
    {
        // "barn" -> a + rn (2 consonants with r first) -> long ɑː
        // (r+C exception: 'a' != 'o', and word[pos+1]=='r')
        var tokens = _engine.ToPhonemeList("barn");
        Assert.Contains("\u0251\u02d0", tokens);  // ɑː
    }

    // ================================================================
    // 51. x -> /ks/
    // ================================================================

    [Fact]
    public void Consonant_X_ProducesKS()
    {
        var tokens = _engine.ToPhonemeList("box");
        Assert.Contains("k", tokens);
        Assert.Contains("s", tokens);
    }

    // ================================================================
    // 52. c before e -> /s/
    // ================================================================

    [Fact]
    public void Consonant_C_BeforeE_ProducesS()
    {
        var tokens = _engine.ToPhonemeList("cell");
        var filtered = tokens.Where(t => t != "\u02c8").ToList();
        Assert.Equal("s", filtered[0]);
    }

    // ================================================================
    // 53. w -> /v/
    // ================================================================

    [Fact]
    public void Consonant_W_ProducesV()
    {
        var tokens = _engine.ToPhonemeList("webb");
        Assert.Contains("v", tokens);
    }

    // ================================================================
    // 54. z -> /s/
    // ================================================================

    [Fact]
    public void Consonant_Z_ProducesS()
    {
        var tokens = _engine.ToPhonemeList("zon");
        Assert.Contains("s", tokens);
    }

    // ================================================================
    // 55. Trigraph: sch -> /ɧ/
    // ================================================================

    [Fact]
    public void Trigraph_Sch_ProducesFricative()
    {
        var tokens = _engine.ToPhonemeList("schema");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 56. Multiple words with stress
    // ================================================================

    [Fact]
    public void MultipleWords_EachHasStress()
    {
        var tokens = _engine.ToPhonemeList("hej alla");
        // Should have two stress markers
        int stressCount = tokens.Count(t => t == "\u02c8");
        Assert.Equal(2, stressCount);
    }

    // ================================================================
    // 57. Digraph: kj -> /ɕ/
    // ================================================================

    [Fact]
    public void Digraph_Kj_ProducesTjSound()
    {
        var tokens = _engine.ToPhonemeList("kjol");
        Assert.Contains("\u0255", tokens);  // ɕ
    }

    // ================================================================
    // 58. Stress-attracting suffix: -eri
    // ================================================================

    [Fact]
    public void Stress_AttractingSuffix_Eri()
    {
        // "bageri" -> -eri suffix -> stress on syllable after "bag"
        int stressSyl = SwedishG2PEngine.DetectStress("bageri");
        // "bag" = 1 syllable, so stress on syllable index 1
        Assert.Equal(1, stressSyl);
    }

    // ================================================================
    // 59. Loanword -ssion suffix
    // ================================================================

    [Fact]
    public void Loanword_Ssion_ProducesCorrectPhonemes()
    {
        var tokens = _engine.ToPhonemeList("passion");
        Assert.Contains("\u0267", tokens);    // ɧ
        Assert.Contains("u\u02d0", tokens);   // uː
    }

    // ================================================================
    // 60. Hard k stem matching
    // ================================================================

    [Fact]
    public void HardK_StemMatch_ProducesK()
    {
        // "leker" -> stem "lek" is in HardKStems -> hard k
        var tokens = _engine.ToPhonemeList("leker");
        Assert.Contains("k", tokens);
        Assert.DoesNotContain("\u0255", tokens);
    }

    // ================================================================
    // 61. Retroflex: r at end of word (flush pending r)
    // ================================================================

    [Fact]
    public void Retroflex_FlushPendingR()
    {
        var input = new List<string> { "a", "r" };
        var result = SwedishG2PEngine.ApplyRetroflex(input);
        Assert.Equal(new List<string> { "a", "r" }, result);
    }

    // ================================================================
    // 62. Digraph: sh -> /ɧ/
    // ================================================================

    [Fact]
    public void Digraph_Sh_ProducesFricative()
    {
        var tokens = _engine.ToPhonemeList("shop");
        Assert.Contains("\u0267", tokens);  // ɧ
    }

    // ================================================================
    // 63. Normalization: uppercase input
    // ================================================================

    [Fact]
    public void Normalization_UppercaseInput()
    {
        var lower = _engine.ToPhonemeList("hej");
        var upper = _engine.ToPhonemeList("HEJ");
        Assert.Equal(lower, upper);
    }

    // ================================================================
    // 64. Long vowel ö -> øː
    // ================================================================

    [Fact]
    public void LongVowel_Oe_ProducesLongOSlash()
    {
        // "söt" -> ö + single t -> long øː
        var tokens = _engine.ToPhonemeList("söt");
        Assert.Contains("\u00f8\u02d0", tokens);  // øː
    }

    // ================================================================
    // 65. Long vowel ä -> ɛː
    // ================================================================

    [Fact]
    public void LongVowel_Ae_ProducesLongEpsilon()
    {
        // "säl" -> ä + single l -> long ɛː
        var tokens = _engine.ToPhonemeList("säl");
        Assert.Contains("\u025b\u02d0", tokens);  // ɛː
    }

    // ================================================================
    // 66. Long vowel å -> oː
    // ================================================================

    [Fact]
    public void LongVowel_Aa_ProducesLongO()
    {
        // "bål" -> å + single l -> long oː
        var tokens = _engine.ToPhonemeList("bål");
        Assert.Contains("o\u02d0", tokens);  // oː
    }

    // ================================================================
    // 67. Short vowel ö -> œ
    // ================================================================

    [Fact]
    public void ShortVowel_Oe_ProducesOE()
    {
        // "höst" -> ö + st (cluster) -> short œ
        var tokens = _engine.ToPhonemeList("höst");
        Assert.Contains("\u0153", tokens);  // œ
    }

    // ================================================================
    // 68. Short vowel i -> ɪ
    // ================================================================

    [Fact]
    public void ShortVowel_I_ProducesNearCloseI()
    {
        // "vill" -> i + ll (cluster) -> short ɪ
        // But "vill" is function word -> short anyway
        var tokens = _engine.ToPhonemeList("vill");
        Assert.Contains("\u026a", tokens);  // ɪ
    }

    // ================================================================
    // 69. Loanword -ium suffix
    // ================================================================

    [Fact]
    public void Loanword_Ium_ProducesCorrectPhonemes()
    {
        var tokens = _engine.ToPhonemeList("stadium");
        Assert.Contains("\u026a", tokens);   // ɪ
        Assert.Contains("\u0275", tokens);   // ɵ
    }

    // ================================================================
    // 70. Multiple punctuation characters
    // ================================================================

    [Fact]
    public void MultiplePunctuation_AllPreserved()
    {
        var tokens = _engine.ToPhonemeList("hej!?");
        Assert.Contains("!", tokens);
        Assert.Contains("?", tokens);
    }

    // ================================================================
    // 71. Hard G stem: berg/borg compounds
    // ================================================================

    [Fact]
    public void HardG_Berg_ProducesHardG()
    {
        // "berg" is in HardGWords -> hard g
        var tokens = _engine.ToPhonemeList("berg");
        Assert.Contains("\u0261", tokens);  // ɡ
    }

    // ================================================================
    // 72. Trigraph: ckj -> /ɕ/
    // ================================================================

    [Fact]
    public void Trigraph_Ckj_ProducesTjSound()
    {
        var input = new List<string> { "a" };
        // Test via full word containing ckj... (rare but we test the rule)
        // Since ckj is unusual, let's test via the engine
        // "rackjobb" is not a real word but tests the trigraph
        // Let's just test the retroflex helper doesn't interfere
        // Actually test with a constructed word
        var tokens = _engine.ToPhonemeList("rackjobb");
        // ckj -> ɕ
        Assert.Contains("\u0255", tokens);
    }

    // ================================================================
    // 73. DetectStress: stress-attracting suffix -itet
    // ================================================================

    [Fact]
    public void Stress_AttractingSuffix_Itet()
    {
        // "kvalitet" -> -itet suffix -> stress after "kval"
        int stressSyl = SwedishG2PEngine.DetectStress("kvalitet");
        // "kval" = 1 syllable -> stress on syllable index 1
        Assert.Equal(1, stressSyl);
    }

    // ================================================================
    // 74. Full E2E: engine output fed to SwedishPhonemizer
    // ================================================================

    [Fact]
    public void E2E_EngineToPhonemizerIntegration()
    {
        var engine = new SwedishG2PEngine();
        var phonemizer = new SwedishPhonemizer(engine);

        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("hej");

        Assert.NotEmpty(tokens);
        Assert.Equal(tokens.Count, prosody.Count);
        // Should have stress marker somewhere in the output
        Assert.Contains("\u02c8", tokens);
    }

    // ================================================================
    // 75. E2E: multi-word with prosody
    // ================================================================

    [Fact]
    public void E2E_MultiWord_ProsodyAlignment()
    {
        var engine = new SwedishG2PEngine();
        var phonemizer = new SwedishPhonemizer(engine);

        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("hej alla");

        Assert.Equal(tokens.Count, prosody.Count);
        Assert.Contains(" ", tokens);  // word boundary
    }

    // ================================================================
    // 76. Stress-attracting suffix -ist
    // ================================================================

    [Fact]
    public void Stress_AttractingSuffix_Ist()
    {
        int stressSyl = SwedishG2PEngine.DetectStress("pianist");
        // "pian" -> 'ia' is one vowel cluster -> 1 syllable -> stress on index 1
        Assert.Equal(1, stressSyl);
    }

    // ================================================================
    // 77. Long vowel u -> ʉː
    // ================================================================

    [Fact]
    public void LongVowel_U_ProducesBarredU()
    {
        // "hus" -> u + single s -> long ʉː
        var tokens = _engine.ToPhonemeList("hus");
        Assert.Contains("\u0289\u02d0", tokens);  // ʉː
    }

    // ================================================================
    // 78. Long vowel y -> yː
    // ================================================================

    [Fact]
    public void LongVowel_Y_ProducesLongY()
    {
        // "by" -> y word-final -> long yː
        var tokens = _engine.ToPhonemeList("by");
        Assert.Contains("y\u02d0", tokens);  // yː
    }

    // ================================================================
    // 79. Long vowel i -> iː
    // ================================================================

    [Fact]
    public void LongVowel_I_ProducesLongI()
    {
        // "bil" -> i + single l -> long iː
        var tokens = _engine.ToPhonemeList("bil");
        Assert.Contains("i\u02d0", tokens);  // iː
    }

    // ================================================================
    // 80. Loanword -eum suffix
    // ================================================================

    [Fact]
    public void Loanword_Eum_ProducesCorrectPhonemes()
    {
        var tokens = _engine.ToPhonemeList("museum");
        Assert.Contains("e\u02d0", tokens);  // eː
        Assert.Contains("\u0275", tokens);   // ɵ
    }
}
