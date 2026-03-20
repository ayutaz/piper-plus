using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="EnglishPhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> stress marker insertion ->
/// function-word stress removal -> word boundary spaces -> punctuation
/// attachment -> prosody alignment -> PostProcessIds BOS/EOS/PAD,
/// using a stubbed <see cref="IEnglishG2PEngine"/>.
/// </summary>
public sealed class EnglishPhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubEnglishG2PEngine : IEnglishG2PEngine
    {
        private readonly List<List<string>> _words;
        public StubEnglishG2PEngine(List<List<string>> words) => _words = words;
        public List<List<string>> ConvertToArpabet(string text) => _words;
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
        ["\u0259"] = [11],  // ə
        ["l"] = [12],
        ["\u02c8"] = [20],  // ˈ
        ["\u02cc"] = [21],  // ˌ
        ["o"] = [59],
        ["\u028a"] = [24],  // ʊ
        ["\u00f0"] = [30],  // ð
        ["k"] = [31],
        ["\u00e6"] = [32],  // æ
        ["t"] = [33],
        [","] = [40],
    };

    // ================================================================
    // 1. StressMarkers_Inserted
    // ================================================================

    [Fact]
    public void StressMarkers_Inserted()
    {
        // "hello" -> HH AH0 L OW1 => h ə l ˈ oʊ
        // Primary stress on OW1 should insert "ˈ" before the vowel.
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("hello");

        Assert.Contains("\u02c8", tokens); // ˈ
        int idx = tokens.IndexOf("\u02c8");
        // The stressed vowel OW1 -> oʊ; first char "o" follows the marker.
        Assert.Equal("o", tokens[idx + 1]);
    }

    // ================================================================
    // 2. SecondaryStress_Marker
    // ================================================================

    [Fact]
    public void SecondaryStress_Marker()
    {
        // A content word with secondary stress: IH2 N F ER0 M EY1 SH AH0 N
        // "information" has secondary stress on the first syllable.
        var words = new List<List<string>>
        {
            new() { "IH2", "N", "F", "ER0", "M", "EY1", "SH", "AH0", "N" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("information");

        Assert.Contains("\u02cc", tokens); // ˌ
    }

    // ================================================================
    // 3. NoStress_NoMarker
    // ================================================================

    [Fact]
    public void NoStress_NoMarker()
    {
        // Unstressed vowel AH0 should NOT produce a stress marker.
        // "hello" -> HH AH0 L OW1: check the "ə" (AH0) has no marker before it.
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("hello");

        int schwaIdx = tokens.IndexOf("\u0259"); // ə
        Assert.True(schwaIdx >= 0, "Schwa should be present");
        if (schwaIdx > 0)
        {
            Assert.NotEqual("\u02c8", tokens[schwaIdx - 1]); // no ˈ before schwa
            Assert.NotEqual("\u02cc", tokens[schwaIdx - 1]); // no ˌ before schwa
        }
    }

    // ================================================================
    // 4. FunctionWord_NoStress
    // ================================================================

    [Fact]
    public void FunctionWord_NoStress()
    {
        // "the" is a function word. G2P might give DH AH0 (or DH IY1),
        // but the phonemizer should remove stress from function words.
        // Here we supply DH IY1 to verify stress removal.
        var words = new List<List<string>>
        {
            new() { "DH", "IY1" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("the");

        // Stress marker should NOT appear (function word).
        Assert.DoesNotContain("\u02c8", tokens); // no ˈ
        Assert.DoesNotContain("\u02cc", tokens); // no ˌ
    }

    // ================================================================
    // 5. ContentWord_KeepsStress
    // ================================================================

    [Fact]
    public void ContentWord_KeepsStress()
    {
        // "cat" is a content word. K AE1 T -> k ˈ æ t
        var words = new List<List<string>>
        {
            new() { "K", "AE1", "T" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("cat");

        Assert.Contains("\u02c8", tokens); // ˈ should be present
    }

    // ================================================================
    // 6. WordBoundary_Spaces
    // ================================================================

    [Fact]
    public void WordBoundary_Spaces()
    {
        // Two words: "hello world" should have a space between them.
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
            new() { "W", "ER1", "L", "D" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("hello world");

        Assert.Contains(" ", tokens);
    }

    // ================================================================
    // 7. NoLeadingSpace
    // ================================================================

    [Fact]
    public void NoLeadingSpace()
    {
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
            new() { "W", "ER1", "L", "D" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("hello world");

        Assert.NotEqual(" ", tokens[0]);
    }

    // ================================================================
    // 8. Punctuation_AttachedToPrevious
    // ================================================================

    [Fact]
    public void Punctuation_AttachedToPrevious()
    {
        // "Hello, world" -> [HH AH0 L OW1], [,], [W ER1 L D]
        // Comma should attach to "hello" (no space before comma).
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
            new() { "," },
            new() { "W", "ER1", "L", "D" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("Hello, world");

        int commaIdx = tokens.IndexOf(",");
        Assert.True(commaIdx > 0, "Comma should be present and not first");
        // No space before comma.
        Assert.NotEqual(" ", tokens[commaIdx - 1]);
    }

    // ================================================================
    // 9. PrimaryStress_MapsTo_A2_2
    // ================================================================

    [Fact]
    public void PrimaryStress_MapsTo_A2_2()
    {
        // Primary stress (1) -> A2=2.
        // "go" -> G OW1
        var words = new List<List<string>>
        {
            new() { "G", "OW1" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("go");

        var a2Values = prosody.Where(p => p is not null).Select(p => p!.Value.A2).ToList();
        Assert.Contains(2, a2Values);
    }

    // ================================================================
    // 10. Unstressed_MapsTo_A2_0
    // ================================================================

    [Fact]
    public void Unstressed_MapsTo_A2_0()
    {
        // "the" is a function word. DH AH0 -> unstressed -> A2=0 for all.
        var words = new List<List<string>>
        {
            new() { "DH", "AH0" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("the");

        var a2Values = prosody.Where(p => p is not null).Select(p => p!.Value.A2).ToList();
        Assert.Contains(0, a2Values);
    }

    // ================================================================
    // 11. A1_AlwaysZero
    // ================================================================

    [Fact]
    public void A1_AlwaysZero()
    {
        // English always has A1=0.
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
            new() { "W", "ER1", "L", "D" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("hello world");

        foreach (var p in prosody)
        {
            if (p is not null)
            {
                Assert.Equal(0, p!.Value.A1);
            }
        }
    }

    // ================================================================
    // 12. PostProcessIds_InsertsInterPhonemePad
    // ================================================================

    [Fact]
    public void PostProcessIds_InsertsInterPhonemePad()
    {
        var phonemizer = new EnglishPhonemizer(
            new StubEnglishG2PEngine([]));

        var inputIds = new List<int> { 10, 59 };
        var inputProsody = new List<ProsodyInfo?> { null, null };
        var map = MakeMap();

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Pattern: BOS(1), PAD(0), 10, PAD(0), 59, PAD(0), EOS(2)
        // Check that PAD (0) appears between phoneme IDs.
        // After BOS+PAD prefix, the pattern is: phoneme, pad, phoneme, pad, ...
        int bosAndPadCount = 2; // BOS(1) + PAD(0)
        Assert.Equal(0, ids[bosAndPadCount + 1]); // PAD after first phoneme
    }

    // ================================================================
    // 13. PostProcessIds_AddsBosEos
    // ================================================================

    [Fact]
    public void PostProcessIds_AddsBosEos()
    {
        var phonemizer = new EnglishPhonemizer(
            new StubEnglishG2PEngine([]));

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { null };
        var map = MakeMap();

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // First ID should be BOS (^) = 1.
        Assert.Equal(1, ids[0]);
        // Last ID should be EOS ($) = 2.
        Assert.Equal(2, ids[^1]);
    }

    // ================================================================
    // 14. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var phonemizer = new EnglishPhonemizer(
            new StubEnglishG2PEngine([]));

        // Input: three phoneme IDs.
        var inputIds = new List<int> { 10, 59, 24 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 3), new(0, 2, 3), new(0, 2, 3),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected:
        // BOS(1), PAD(0), 10, PAD(0), 59, PAD(0), 24, PAD(0), EOS(2)
        // = [1, 0, 10, 0, 59, 0, 24, 0, 2]
        Assert.Equal([1, 0, 10, 0, 59, 0, 24, 0, 2], ids);

        // IDs and prosody must have the same length.
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 15. PostProcessIds_ProsodyAlignment
    // ================================================================

    [Fact]
    public void PostProcessIds_ProsodyAlignment()
    {
        var phonemizer = new EnglishPhonemizer(
            new StubEnglishG2PEngine([]));

        var inputIds = new List<int> { 10, 59, 24, 31, 32 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 5), new(0, 2, 5), new(0, 2, 5),
            new(0, 0, 5), new(0, 0, 5),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        Assert.Equal(ids.Count, prosody.Count);

        // BOS and EOS positions should have null prosody.
        Assert.Null(prosody[0]);   // BOS
        Assert.Null(prosody[^1]);  // EOS
    }

    // ================================================================
    // 16. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        // Phonemize() should return the same token list as PhonemizeWithProsody().Tokens.
        var words = new List<List<string>>
        {
            new() { "K", "AE1", "T" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var tokens = phonemizer.Phonemize("cat");

        Assert.IsType<List<string>>(tokens);
        Assert.NotEmpty(tokens);
        // Should contain the IPA phonemes for "cat": k, æ, t (plus stress marker).
        Assert.Contains("k", tokens);
        Assert.Contains("t", tokens);
    }

    // ================================================================
    // 17. PhonemizeWithProsody_EmptyInput
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyInput()
    {
        // Engine returns empty word groups -> empty result.
        var words = new List<List<string>>();

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 18. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var phonemizer = new EnglishPhonemizer(
            new StubEnglishG2PEngine([]));

        // English models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 19. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // Multi-word input: tokens.Count must equal prosody.Count.
        var words = new List<List<string>>
        {
            new() { "HH", "AH0", "L", "OW1" },
            new() { "," },
            new() { "W", "ER1", "L", "D" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("Hello, world");

        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 20. ProsodyA3_IsWordPhonemeCount
    // ================================================================

    [Fact]
    public void ProsodyA3_IsWordPhonemeCount()
    {
        // "cat" -> K AE1 T => IPA: k(1) æ(1) t(1) = 3 IPA chars
        // A3 should be 3 for all phoneme tokens in the word.
        var words = new List<List<string>>
        {
            new() { "K", "AE1", "T" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("cat");

        // Count actual IPA characters (excluding stress markers)
        // K->k(1), AE1->æ(1), T->t(1), total=3
        // The stress marker ˈ also gets A3=3 in its prosody entry.
        var a3Values = prosody
            .Where(p => p is not null)
            .Select(p => p!.Value.A3)
            .Distinct()
            .ToList();

        Assert.Single(a3Values); // all tokens share the same A3
        Assert.Equal(3, a3Values[0]);
    }

    // ================================================================
    // 21. SecondaryStress_MapsTo_A2_1
    // ================================================================

    [Fact]
    public void SecondaryStress_MapsTo_A2_1()
    {
        // Secondary stress (2) -> A2=1.
        // Use a content word (not a function word) with secondary stress.
        // "replay" -> R IH0 P L EY2
        var words = new List<List<string>>
        {
            new() { "R", "IH0", "P", "L", "EY2" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("replay");

        var a2Values = prosody.Where(p => p is not null).Select(p => p!.Value.A2).ToList();
        Assert.Contains(1, a2Values);
    }

    // ================================================================
    // 22. MultipleStressMarkers_InSingleWord
    // ================================================================

    [Fact]
    public void MultipleStressMarkers_InSingleWord()
    {
        // A word with both primary and secondary stress:
        // "information" -> IH2 N F ER0 M EY1 SH AH0 N
        // Should produce both ˌ (before IH2) and ˈ (before EY1).
        var words = new List<List<string>>
        {
            new() { "IH2", "N", "F", "ER0", "M", "EY1", "SH", "AH0", "N" },
        };

        var phonemizer = new EnglishPhonemizer(new StubEnglishG2PEngine(words));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("information");

        Assert.Contains("\u02cc", tokens); // ˌ (secondary)
        Assert.Contains("\u02c8", tokens); // ˈ (primary)

        // ˌ should appear before ˈ in the token sequence.
        int secondaryIdx = tokens.IndexOf("\u02cc");
        int primaryIdx = tokens.IndexOf("\u02c8");
        Assert.True(secondaryIdx < primaryIdx,
            "Secondary stress marker should appear before primary stress marker");
    }
}
