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
    // 27. PuaMapping_TotalCount_Is96
    // ================================================================

    [Fact]
    public void PuaMapping_TotalCount_Is96()
    {
        // 29 JA + 2 shared + 43 ZH + 8 KO + 2 ES/PT + 3 FR + 9 SV = 96
        Assert.Equal(96, OpenJTalkToPiperMapping.TokenToChar.Count);
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
