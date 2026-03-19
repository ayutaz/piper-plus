using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="SpanishPhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> stress marker handling ->
/// word boundary spaces -> punctuation -> prosody alignment ->
/// PostProcessIds BOS/EOS/PAD, using a stubbed <see cref="ISpanishG2PEngine"/>.
/// </summary>
public sealed class SpanishPhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubSpanishG2PEngine : ISpanishG2PEngine
    {
        private readonly List<string> _tokens;
        public StubSpanishG2PEngine(List<string> tokens) => _tokens = tokens;
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
        ["o"] = [10],
        ["l"] = [11],
        ["a"] = [12],
        ["\u02c8"] = [20], // ˈ
        ["k"] = [30],
        ["m"] = [31],
    };

    // ================================================================
    // 1. StressMarker_InOutput
    // ================================================================

    [Fact]
    public void StressMarker_InOutput()
    {
        // "hola" -> ˈ o l a
        // The stress marker ˈ should be present in the output tokens.
        var tokens = new List<string> { "\u02c8", "o", "l", "a" };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("hola");

        Assert.Contains("\u02c8", result); // ˈ
    }

    // ================================================================
    // 2. StressMarker_A2_Is2
    // ================================================================

    [Fact]
    public void StressMarker_A2_Is2()
    {
        // The stress marker ˈ itself should receive A2=2.
        var tokens = new List<string> { "\u02c8", "o", "l", "a" };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hola");

        int idx = result.IndexOf("\u02c8");
        Assert.True(idx >= 0, "Stress marker should be present");
        Assert.NotNull(prosody[idx]);
        Assert.Equal(2, prosody[idx]!.A2);
    }

    // ================================================================
    // 3. StressedVowel_A2_Is2
    // ================================================================

    [Fact]
    public void StressedVowel_A2_Is2()
    {
        // The vowel immediately after ˈ should also receive A2=2.
        var tokens = new List<string> { "\u02c8", "o", "l", "a" };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hola");

        int stressIdx = result.IndexOf("\u02c8");
        int vowelIdx = stressIdx + 1;
        Assert.True(vowelIdx < result.Count, "Vowel should follow stress marker");
        Assert.NotNull(prosody[vowelIdx]);
        Assert.Equal(2, prosody[vowelIdx]!.A2);
    }

    // ================================================================
    // 4. UnstressedPhoneme_A2_Is0
    // ================================================================

    [Fact]
    public void UnstressedPhoneme_A2_Is0()
    {
        // Phonemes that are not the stress marker nor the stressed vowel
        // should have A2=0. In "ˈ o l a", "l" and "a" are unstressed.
        var tokens = new List<string> { "\u02c8", "o", "l", "a" };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hola");

        // Find "l" -- it should be unstressed.
        int lIdx = result.IndexOf("l");
        Assert.True(lIdx >= 0, "'l' should be present");
        Assert.NotNull(prosody[lIdx]);
        Assert.Equal(0, prosody[lIdx]!.A2);

        // Find final "a" -- it should be unstressed.
        int aIdx = result.LastIndexOf("a");
        Assert.True(aIdx >= 0, "'a' should be present");
        Assert.NotNull(prosody[aIdx]);
        Assert.Equal(0, prosody[aIdx]!.A2);
    }

    // ================================================================
    // 5. A3_IsWordPhonemeCount
    // ================================================================

    [Fact]
    public void A3_IsWordPhonemeCount()
    {
        // "hola" -> ˈ o l a
        // A3 = phoneme count excluding ˈ = 3 (o, l, a).
        var tokens = new List<string> { "\u02c8", "o", "l", "a" };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("hola");

        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values); // all tokens in the word share the same A3
        Assert.Equal(3, a3Values[0]);
    }

    // ================================================================
    // 6. WordBoundary_Spaces
    // ================================================================

    [Fact]
    public void WordBoundary_Spaces()
    {
        // "hola mundo" -> ˈ o l a <space> m u n d o
        var tokens = new List<string>
        {
            "\u02c8", "o", "l", "a",
            " ",
            "m", "u", "n", "d", "o",
        };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("hola mundo");

        Assert.Contains(" ", result);
    }

    // ================================================================
    // 7. Punctuation_HasZeroProsody
    // ================================================================

    [Fact]
    public void Punctuation_HasZeroProsody()
    {
        // Punctuation tokens should receive ProsodyInfo(0, 0, 0).
        var tokens = new List<string>
        {
            "\u02c8", "o", "l", "a",
            ",",
        };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hola,");

        int commaIdx = result.IndexOf(",");
        Assert.True(commaIdx >= 0, "Comma should be present");
        Assert.NotNull(prosody[commaIdx]);
        Assert.Equal(0, prosody[commaIdx]!.A1);
        Assert.Equal(0, prosody[commaIdx]!.A2);
        Assert.Equal(0, prosody[commaIdx]!.A3);
    }

    // ================================================================
    // 8. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // tokens.Count must equal prosody.Count for multi-word input.
        var tokens = new List<string>
        {
            "\u02c8", "o", "l", "a",
            " ",
            "m", "u", "n", "d", "o",
            ".",
        };

        var phonemizer = new SpanishPhonemizer(new StubSpanishG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("hola mundo.");

        Assert.Equal(result.Count, prosody.Count);
    }

    // ================================================================
    // 9. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var phonemizer = new SpanishPhonemizer(
            new StubSpanishG2PEngine([]));

        // Spanish models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 10. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var phonemizer = new SpanishPhonemizer(
            new StubSpanishG2PEngine([]));

        // Input: three phoneme IDs (o, l, a).
        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 2, 3), new(0, 0, 3), new(0, 0, 3),
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
}
