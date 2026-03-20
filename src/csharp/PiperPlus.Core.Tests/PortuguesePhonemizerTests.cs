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
        Assert.Equal(2, prosody[iIdx]!.Value.A2);
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
        Assert.Equal(0, prosody[bIdx]!.Value.A2);

        // "a" should also be unstressed.
        int aIdx = result.IndexOf("a");
        Assert.True(aIdx >= 0, "'a' should be present");
        Assert.NotNull(prosody[aIdx]);
        Assert.Equal(0, prosody[aIdx]!.Value.A2);

        // "w" (final) should also be unstressed.
        int wIdx = result.IndexOf("w");
        Assert.True(wIdx >= 0, "'w' should be present");
        Assert.NotNull(prosody[wIdx]);
        Assert.Equal(0, prosody[wIdx]!.Value.A2);
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
            .Select(p => p!.Value.A3)
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
        Assert.Equal(0, prosody[commaIdx]!.Value.A1);
        Assert.Equal(0, prosody[commaIdx]!.Value.A2);
        Assert.Equal(0, prosody[commaIdx]!.Value.A3);
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
            Assert.Equal(0, p!.Value.A2);
        }
    }

    // ================================================================
    // 11. PostProcessIds_SkipsPadAfterPadToken
    // ================================================================

    [Fact]
    public void PostProcessIds_SkipsPadAfterPadToken()
    {
        // When the input already contains a PAD token (0), no extra PAD
        // should be inserted after it (avoids double-PAD).
        var phonemizer = new PortuguesePhonemizer(
            new StubPortugueseG2PEngine([]));

        // Input: [10, 0, 11] where 0 is PAD.
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
    // 12. PostProcessIds_EmptyInput
    // ================================================================

    [Fact]
    public void PostProcessIds_EmptyInput()
    {
        // Empty phoneme list should still produce BOS + PAD + EOS.
        var phonemizer = new PortuguesePhonemizer(
            new StubPortugueseG2PEngine([]));

        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected: [BOS(1), PAD(0), EOS(2)]
        Assert.Equal([1, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 13. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        // Phonemize() should return tokens without prosody.
        var tokens = new List<string> { "b", "\u027e", "a", "z", "\u02c8", "i", "w" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var result = phonemizer.Phonemize("Brasil");

        Assert.NotEmpty(result);
        // Stress marker should be stripped (same behavior as PhonemizeWithProsody).
        Assert.DoesNotContain("\u02c8", result);
        // Phonemes should be present.
        Assert.Contains("b", result);
        Assert.Contains("i", result);
    }

    // ================================================================
    // 14. PhonemizeWithProsody_EmptyInput
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyInput()
    {
        // When the G2P engine returns an empty list, both tokens and
        // prosody should be empty.
        var phonemizer = new PortuguesePhonemizer(
            new StubPortugueseG2PEngine([]));

        var (result, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(result);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 15. Punctuation_InvertedMarks
    // ================================================================

    [Fact]
    public void Punctuation_InvertedMarks()
    {
        // ¡ (U+00A1) and ¿ (U+00BF) should be recognized as punctuation
        // and receive zero prosody.
        var tokens = new List<string>
        {
            "\u00bf",  // ¿
            "\u02c8", "b", "o", "m",
            "\u00a1",  // ¡
        };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("\u00bfbom\u00a1");

        // ¿ should be present with zero prosody.
        int qIdx = result.IndexOf("\u00bf");
        Assert.True(qIdx >= 0, "\u00bf should be present");
        Assert.NotNull(prosody[qIdx]);
        Assert.Equal(0, prosody[qIdx]!.Value.A1);
        Assert.Equal(0, prosody[qIdx]!.Value.A2);
        Assert.Equal(0, prosody[qIdx]!.Value.A3);

        // ¡ should be present with zero prosody.
        int eIdx = result.IndexOf("\u00a1");
        Assert.True(eIdx >= 0, "\u00a1 should be present");
        Assert.NotNull(prosody[eIdx]);
        Assert.Equal(0, prosody[eIdx]!.Value.A1);
        Assert.Equal(0, prosody[eIdx]!.Value.A2);
        Assert.Equal(0, prosody[eIdx]!.Value.A3);
    }

    // ================================================================
    // 16. Punctuation_Dashes
    // ================================================================

    [Fact]
    public void Punctuation_Dashes()
    {
        // — (U+2014 em dash), – (U+2013 en dash), and … (U+2026 ellipsis)
        // should all be recognized as punctuation with zero prosody.
        var tokens = new List<string>
        {
            "b", "o", "m",
            "\u2014",  // —
            "b", "o", "m",
            "\u2013",  // –
            "b", "o", "m",
            "\u2026",  // …
        };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("bom\u2014bom\u2013bom\u2026");

        foreach (var punct in new[] { "\u2014", "\u2013", "\u2026" })
        {
            int idx = result.IndexOf(punct);
            Assert.True(idx >= 0, $"{punct} should be present");
            Assert.NotNull(prosody[idx]);
            Assert.Equal(0, prosody[idx]!.Value.A1);
            Assert.Equal(0, prosody[idx]!.Value.A2);
            Assert.Equal(0, prosody[idx]!.Value.A3);
        }
    }

    // ================================================================
    // 17. StressMarker_AtEndOfWord
    // ================================================================

    [Fact]
    public void StressMarker_AtEndOfWord()
    {
        // When ˈ appears at the end of a word with no following phoneme,
        // it should be stripped and no phoneme receives A2=2.
        var tokens = new List<string> { "b", "o", "m", "\u02c8" };

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("bom");

        // ˈ should be stripped from output.
        Assert.DoesNotContain("\u02c8", result);
        // All phonemes should be unstressed (A2=0).
        foreach (var p in prosody)
        {
            Assert.NotNull(p);
            Assert.Equal(0, p!.Value.A2);
        }
        // The 3 phonemes should still be present.
        Assert.Equal(3, result.Count);
    }

    // ================================================================
    // 18. NasalVowel_PreservedInOutput
    // ================================================================

    [Fact]
    public void NasalVowel_PreservedInOutput()
    {
        // NFC nasal vowels (ã, õ, etc.) should pass through the
        // phonemizer without being altered or stripped.
        var tokens = new List<string> { "m", "\u00e3", "\u02c8", "\u00f5", "s" };
        //                                     ã                     õ

        var phonemizer = new PortuguesePhonemizer(new StubPortugueseG2PEngine(tokens));
        var (result, prosody) = phonemizer.PhonemizeWithProsody("m\u00e3os");

        // ã should be present.
        Assert.Contains("\u00e3", result);
        // õ should be present.
        Assert.Contains("\u00f5", result);
        // ˈ should be stripped.
        Assert.DoesNotContain("\u02c8", result);
        // Alignment check.
        Assert.Equal(result.Count, prosody.Count);
        // õ follows the stress marker, so it should have A2=2.
        int oIdx = result.IndexOf("\u00f5");
        Assert.NotNull(prosody[oIdx]);
        Assert.Equal(2, prosody[oIdx]!.Value.A2);
    }
}
