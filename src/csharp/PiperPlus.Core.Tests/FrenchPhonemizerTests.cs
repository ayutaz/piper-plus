using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="FrenchPhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> last-vowel stress assignment ->
/// word boundary spaces -> punctuation handling -> prosody alignment ->
/// PostProcessIds BOS/EOS/PAD, using a stubbed <see cref="IFrenchG2PEngine"/>.
/// </summary>
public sealed class FrenchPhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubFrenchG2PEngine : IFrenchG2PEngine
    {
        private readonly List<string> _tokens;
        public StubFrenchG2PEngine(List<string> tokens) => _tokens = tokens;
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
        ["o"] = [11],
        ["\u0292"] = [12],  // ʒ
        ["u"] = [13],
        ["\u0281"] = [14],  // ʁ
    };

    // ================================================================
    // 1. LastVowel_GetsStress
    // ================================================================

    [Fact]
    public void LastVowel_GetsStress()
    {
        // "bonjour" -> b ɔ̃ ʒ u ʁ
        // Last vowel = "u" at index 3 -> A2=2.
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bonjour");

        // Find the prosody entry for "u" (index 3 in the word).
        // u is the last vowel, so it should get A2=2.
        var nonNull = prosody.Where(p => p is not null).ToList();
        var uProsody = nonNull[3]; // b(0), ɔ̃(1), ʒ(2), u(3)
        Assert.Equal(2, uProsody!.Value.A2);
    }

    // ================================================================
    // 2. OtherPhonemes_NoStress
    // ================================================================

    [Fact]
    public void OtherPhonemes_NoStress()
    {
        // "bonjour" -> b ɔ̃ ʒ u ʁ
        // ɔ̃ is a vowel but NOT the last vowel -> A2=0.
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bonjour");

        // ɔ̃ at index 1 is a vowel but not the last -> A2=0.
        var nonNull = prosody.Where(p => p is not null).ToList();
        Assert.Equal(0, nonNull[1]!.Value.A2); // ɔ̃
    }

    // ================================================================
    // 3. Consonant_NoStress
    // ================================================================

    [Fact]
    public void Consonant_NoStress()
    {
        // "bonjour" -> b ɔ̃ ʒ u ʁ
        // Consonants never get stress: b, ʒ, ʁ all A2=0.
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bonjour");

        var nonNull = prosody.Where(p => p is not null).ToList();
        Assert.Equal(0, nonNull[0]!.Value.A2); // b
        Assert.Equal(0, nonNull[2]!.Value.A2); // ʒ
        Assert.Equal(0, nonNull[4]!.Value.A2); // ʁ
    }

    // ================================================================
    // 4. A3_IsWordPhonemeCount
    // ================================================================

    [Fact]
    public void A3_IsWordPhonemeCount()
    {
        // "bonjour" -> b ɔ̃ ʒ u ʁ = 5 phonemes.
        // A3 should be 5 for all tokens in the word.
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bonjour");

        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.Value.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values);
        Assert.Equal(5, a3Values[0]);
    }

    // ================================================================
    // 5. NoStressMarkerInOutput
    // ================================================================

    [Fact]
    public void NoStressMarkerInOutput()
    {
        // French does NOT insert ˈ or ˌ stress markers in the output.
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (outputTokens, _) = phonemizer.PhonemizeWithProsody("bonjour");

        Assert.DoesNotContain("\u02c8", outputTokens); // no ˈ
        Assert.DoesNotContain("\u02cc", outputTokens); // no ˌ
    }

    // ================================================================
    // 6. WordBoundary_Spaces
    // ================================================================

    [Fact]
    public void WordBoundary_Spaces()
    {
        // "le chat" -> l ə " " ʃ a
        var tokens = new List<string> { "l", "\u0259", " ", "\u0283", "a" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (outputTokens, _) = phonemizer.PhonemizeWithProsody("le chat");

        Assert.Contains(" ", outputTokens);
    }

    // ================================================================
    // 7. Punctuation_HasZeroProsody
    // ================================================================

    [Fact]
    public void Punctuation_HasZeroProsody()
    {
        // "oui," -> u i , (comma is punctuation)
        var tokens = new List<string> { "u", "i", "," };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("oui,");

        // The comma should have A1=0, A2=0, A3=0.
        var commaProsody = prosody[^1];
        Assert.NotNull(commaProsody);
        Assert.Equal(0, commaProsody!.Value.A1);
        Assert.Equal(0, commaProsody!.Value.A2);
        Assert.Equal(0, commaProsody!.Value.A3);
    }

    // ================================================================
    // 8. NasalVowel_IsVowel
    // ================================================================

    [Fact]
    public void NasalVowel_IsVowel()
    {
        // A word ending with a nasal vowel: "bon" -> b ɔ̃
        // ɔ̃ is the last vowel and should get A2=2.
        var tokens = new List<string> { "b", "\u0254\u0303" }; // b ɔ̃

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("bon");

        var nonNull = prosody.Where(p => p is not null).ToList();
        Assert.Equal(2, nonNull[1]!.Value.A2); // ɔ̃ is last vowel -> stressed

        // Also test ɛ̃ and ɑ̃.
        var tokens2 = new List<string> { "v", "\u025b\u0303" }; // v ɛ̃
        var phonemizer2 = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens2));
        var (_, prosody2) = phonemizer2.PhonemizeWithProsody("vin");

        var nonNull2 = prosody2.Where(p => p is not null).ToList();
        Assert.Equal(2, nonNull2[1]!.Value.A2); // ɛ̃ is last vowel -> stressed

        var tokens3 = new List<string> { "l", "\u0251\u0303" }; // l ɑ̃
        var phonemizer3 = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens3));
        var (_, prosody3) = phonemizer3.PhonemizeWithProsody("lent");

        var nonNull3 = prosody3.Where(p => p is not null).ToList();
        Assert.Equal(2, nonNull3[1]!.Value.A2); // ɑ̃ is last vowel -> stressed
    }

    // ================================================================
    // 9. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // Multi-word: "le chat" -> l ə " " ʃ a
        // tokens.Count must equal prosody.Count.
        var tokens = new List<string> { "l", "\u0259", " ", "\u0283", "a" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (outputTokens, prosody) = phonemizer.PhonemizeWithProsody("le chat");

        Assert.Equal(outputTokens.Count, prosody.Count);
    }

    // ================================================================
    // 10. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var phonemizer = new FrenchPhonemizer(
            new StubFrenchG2PEngine([]));

        // French models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 11. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var phonemizer = new FrenchPhonemizer(
            new StubFrenchG2PEngine([]));

        // Input: three phoneme IDs (b, o, ʒ).
        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 3), new(0, 2, 3), new(0, 0, 3),
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
    // 12. PostProcessIds_SkipsPadAfterPadToken
    // ================================================================

    [Fact]
    public void PostProcessIds_SkipsPadAfterPadToken()
    {
        var phonemizer = new FrenchPhonemizer(
            new StubFrenchG2PEngine([]));

        // Input: [b(10), PAD(0), o(11)] — PAD token already present.
        // PAD-after-PAD should be skipped (matching Python base.py).
        var inputIds = new List<int> { 10, 0, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 3), null, new(0, 2, 3),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected:
        // BOS(1), PAD(0), 10, PAD(0), 0, 11, PAD(0), EOS(2)
        // = [1, 0, 10, 0, 0, 11, 0, 2]
        // Note: no double-PAD after the PAD(0) token itself.
        Assert.Equal([1, 0, 10, 0, 0, 11, 0, 2], ids);

        // IDs and prosody must have the same length.
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 13. PostProcessIds_EmptyInput
    // ================================================================

    [Fact]
    public void PostProcessIds_EmptyInput()
    {
        var phonemizer = new FrenchPhonemizer(
            new StubFrenchG2PEngine([]));

        // Empty input: no phoneme IDs at all.
        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected: BOS(1), PAD(0), EOS(2) = [1, 0, 2]
        Assert.Equal([1, 0, 2], ids);

        // IDs and prosody must have the same length.
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 14. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        // "bonjour" -> b ɔ̃ ʒ u ʁ
        var tokens = new List<string> { "b", "\u0254\u0303", "\u0292", "u", "\u0281" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var result = phonemizer.Phonemize("bonjour");

        // Phonemize() should return tokens (possibly PUA-mapped).
        Assert.NotNull(result);
        Assert.NotEmpty(result);
        Assert.Equal(tokens.Count, result.Count);
    }

    // ================================================================
    // 15. PhonemizeWithProsody_EmptyInput
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyInput()
    {
        // Engine returns empty list -> empty result.
        var phonemizer = new FrenchPhonemizer(
            new StubFrenchG2PEngine([]));

        var (outputTokens, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(outputTokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 16. Punctuation_InvertedMarks
    // ================================================================

    [Fact]
    public void Punctuation_InvertedMarks()
    {
        // ¡ and ¿ are recognized as punctuation with zero prosody.
        var tokens = new List<string> { "\u00bf", "u", "i", "\u00a1" }; // ¿ u i ¡

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("\u00bfoui\u00a1");

        // ¿ at index 0 should be punctuation with zero prosody.
        Assert.NotNull(prosody[0]);
        Assert.Equal(0, prosody[0]!.Value.A1);
        Assert.Equal(0, prosody[0]!.Value.A2);
        Assert.Equal(0, prosody[0]!.Value.A3);

        // ¡ at the end should also be punctuation with zero prosody.
        Assert.NotNull(prosody[^1]);
        Assert.Equal(0, prosody[^1]!.Value.A1);
        Assert.Equal(0, prosody[^1]!.Value.A2);
        Assert.Equal(0, prosody[^1]!.Value.A3);
    }

    // ================================================================
    // 17. Punctuation_Guillemets
    // ================================================================

    [Fact]
    public void Punctuation_Guillemets()
    {
        // « and » are recognized as punctuation.
        var tokens = new List<string> { "\u00ab", "u", "i", "\u00bb" }; // « u i »

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("\u00aboui\u00bb");

        // « at index 0 should be punctuation with zero prosody.
        Assert.NotNull(prosody[0]);
        Assert.Equal(0, prosody[0]!.Value.A1);
        Assert.Equal(0, prosody[0]!.Value.A2);
        Assert.Equal(0, prosody[0]!.Value.A3);

        // » at the end should also be punctuation with zero prosody.
        Assert.NotNull(prosody[^1]);
        Assert.Equal(0, prosody[^1]!.Value.A1);
        Assert.Equal(0, prosody[^1]!.Value.A2);
        Assert.Equal(0, prosody[^1]!.Value.A3);
    }

    // ================================================================
    // 18. YVowel_TreatedAsVowel
    // ================================================================

    [Fact]
    public void YVowel_TreatedAsVowel()
    {
        // "y_vowel" token is treated as a vowel for stress detection.
        // Word: "k y_vowel" — y_vowel is the last vowel -> A2=2.
        var tokens = new List<string> { "k", "y_vowel" };

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("test");

        var nonNull = prosody.Where(p => p is not null).ToList();
        Assert.Equal(0, nonNull[0]!.Value.A2);  // k = consonant -> no stress
        Assert.Equal(2, nonNull[1]!.Value.A2);  // y_vowel = last vowel -> stressed
    }

    // ================================================================
    // 19. Schwa_TreatedAsVowel
    // ================================================================

    [Fact]
    public void Schwa_TreatedAsVowel()
    {
        // ə (schwa) token is treated as a vowel for stress detection.
        // Word: "l ə" — ə is the last vowel -> A2=2.
        var tokens = new List<string> { "l", "\u0259" }; // l ə

        var phonemizer = new FrenchPhonemizer(new StubFrenchG2PEngine(tokens));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("le");

        var nonNull = prosody.Where(p => p is not null).ToList();
        Assert.Equal(0, nonNull[0]!.Value.A2);  // l = consonant -> no stress
        Assert.Equal(2, nonNull[1]!.Value.A2);  // ə = last vowel -> stressed
    }
}
