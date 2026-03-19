using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PortuguesePhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> stress marker stripping ->
/// word boundary spaces -> punctuation -> prosody alignment ->
/// PostProcessIds BOS/EOS/PAD, using a stubbed <see cref="IPortugueseG2PEngine"/>.
/// </summary>
public sealed class PortuguesePhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubPortugueseG2PEngine : IPortugueseG2PEngine
    {
        private readonly List<string> _tokens;
        public StubPortugueseG2PEngine(List<string> tokens) => _tokens = tokens;
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
        ["b"] = [10],
        ["\u027e"] = [11], // ɾ
        ["a"] = [12],
        ["z"] = [13],
        ["i"] = [14],
        ["w"] = [15],
    };

    // ================================================================
    // 1. StressMarker_StrippedFromOutput
    // ================================================================

    [Fact]
    public void StressMarker_StrippedFromOutput()
    {
        // "Brasil" -> b ɾ a z ˈ i w
        // The stress marker ˈ should NOT appear in the output tokens
        // (Python implementation strips it).
        var tokens = new List<string> { "b", "\u027e", "a", "z", "\u02c8", "i", "w" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("Brasil");

        Assert.DoesNotContain("\u02c8", result); // ˈ must not appear
    }

    // ================================================================
    // 2. StressedPhoneme_A2_Is2
    // ================================================================

    [Fact]
    public void StressedPhoneme_A2_Is2()
    {
        // "Brasil" -> b ɾ a z ˈ i w
        // The phoneme immediately after ˈ ("i") should receive A2=2.
        var tokens = new List<string> { "b", "\u027e", "a", "z", "\u02c8", "i", "w" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("Brasil");

        // After stripping ˈ, output is: b ɾ a z i w
        // "i" is at index 4 in the output.
        int iIdx = result.IndexOf("i");
        Assert.True(iIdx >= 0, "'i' should be present");
        Assert.NotNull(prosody[iIdx]);
        Assert.Equal(2, prosody[iIdx]!.A2);
    }

    // ================================================================
    // 3. UnstressedPhoneme_A2_Is0
    // ================================================================

    [Fact]
    public void UnstressedPhoneme_A2_Is0()
    {
        // "Brasil" -> b ɾ a z ˈ i w
        // Phonemes that are NOT after ˈ should have A2=0.
        var tokens = new List<string> { "b", "\u027e", "a", "z", "\u02c8", "i", "w" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("Brasil");

        // "b" at index 0 should be unstressed.
        int bIdx = result.IndexOf("b");
        Assert.True(bIdx >= 0, "'b' should be present");
        Assert.NotNull(prosody[bIdx]);
        Assert.Equal(0, prosody[bIdx]!.A2);

        // "a" should also be unstressed.
        int aIdx = result.IndexOf("a");
        Assert.True(aIdx >= 0, "'a' should be present");
        Assert.NotNull(prosody[aIdx]);
        Assert.Equal(0, prosody[aIdx]!.A2);

        // "w" (final) should also be unstressed.
        int wIdx = result.IndexOf("w");
        Assert.True(wIdx >= 0, "'w' should be present");
        Assert.NotNull(prosody[wIdx]);
        Assert.Equal(0, prosody[wIdx]!.A2);
    }

    // ================================================================
    // 4. A3_IsPhonemeCountExcludingStress
    // ================================================================

    [Fact]
    public void A3_IsPhonemeCountExcludingStress()
    {
        // "Brasil" -> b ɾ a z ˈ i w
        // A3 = phoneme count excluding ˈ = 6 (b, ɾ, a, z, i, w).
        var tokens = new List<string> { "b", "\u027e", "a", "z", "\u02c8", "i", "w" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("Brasil");

        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values); // all tokens in the word share the same A3
        Assert.Equal(6, a3Values[0]);
    }

    // ================================================================
    // 5. WordBoundary_Spaces
    // ================================================================

    [Fact]
    public void WordBoundary_Spaces()
    {
        // "bom dia" -> b o m <space> d i a
        var tokens = new List<string>
        {
            "b", "o", "m",
            " ",
            "d", "i", "a",
        };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, _) = phonemizer.PhonemizeWithProsody("bom dia");

        Assert.Contains(" ", result);
    }

    // ================================================================
    // 6. Punctuation_HasZeroProsody
    // ================================================================

    [Fact]
    public void Punctuation_HasZeroProsody()
    {
        // Punctuation tokens should receive ProsodyInfo(0, 0, 0).
        var tokens = new List<string>
        {
            "\u02c8", "b", "o", "m",
            ",",
        };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("bom,");

        int commaIdx = result.IndexOf(",");
        Assert.True(commaIdx >= 0, "Comma should be present");
        Assert.NotNull(prosody[commaIdx]);
        Assert.Equal(0, prosody[commaIdx]!.A1);
        Assert.Equal(0, prosody[commaIdx]!.A2);
        Assert.Equal(0, prosody[commaIdx]!.A3);
    }

    // ================================================================
    // 7. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // tokens.Count must equal prosody.Count for multi-word input.
        var tokens = new List<string>
        {
            "b", "\u027e", "a", "z", "\u02c8", "i", "w",
            " ",
            "\u02c8", "b", "o", "m",
            ".",
        };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("Brasil bom.");

        Assert.Equal(result.Count, prosody.Count);
    }

    // ================================================================
    // 8. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var phonemizer = new PortuguesePhonemizer(
            new StubPortugueseG2PEngine([]));

        // Portuguese models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 9. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var phonemizer = new PortuguesePhonemizer(
            new StubPortugueseG2PEngine([]));

        // Input: three phoneme IDs (b, ɾ, a).
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
    // 10. NoStressMarker_AllUnstressed
    // ================================================================

    [Fact]
    public void NoStressMarker_AllUnstressed()
    {
        // If the G2P engine returns no ˈ marker, all phonemes get A2=0.
        var tokens = new List<string> { "b", "o", "m" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bom");

        foreach (var p in prosody)
        {
            Assert.NotNull(p);
            Assert.Equal(0, p!.A2);
        }
    }
}
