using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="KoreanPhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> token pass-through ->
/// prosody alignment -> PostProcessIds BOS/EOS/PAD,
/// using a stubbed <see cref="IKoreanG2PEngine"/>.
/// </summary>
public sealed class KoreanPhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubKoreanG2PEngine : IKoreanG2PEngine
    {
        private readonly KoreanG2PResult _result;
        public StubKoreanG2PEngine(KoreanG2PResult result) => _result = result;
        public KoreanG2PResult Convert(string text) => _result;
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
        ["a"] = [10],
        ["n"] = [11],
        ["k"] = [12],
    };

    // ================================================================
    // 1. BasicPhonemes_PassedThrough
    // ================================================================

    [Fact]
    public void BasicPhonemes_PassedThrough()
    {
        // Simulated output for a simple Korean word.
        var g2p = new KoreanG2PResult(
            Phonemes: ["k", "a", "n", "a", "t", "a"],
            A1: [0, 0, 0, 0, 0, 0],
            A2: [0, 0, 0, 0, 0, 0],
            A3: [3, 3, 3, 3, 3, 3]
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("\uAC00\uB098\uB2E4");

        Assert.Equal(["k", "a", "n", "a", "t", "a"], tokens);
    }

    // ================================================================
    // 2. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: ["k", "a", "n", "a"],
            A1: [0, 0, 0, 0],
            A2: [0, 0, 0, 0],
            A3: [2, 2, 2, 2]
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("\uAC00\uB098");

        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 3. Prosody_A1A2Zero_A3SyllableCount
    // ================================================================

    [Fact]
    public void Prosody_A1A2Zero_A3SyllableCount()
    {
        // A1=0, A2=0, A3=2 (two Hangul syllables in word).
        var g2p = new KoreanG2PResult(
            Phonemes: ["k", "a", "n", "a"],
            A1: [0, 0, 0, 0],
            A2: [0, 0, 0, 0],
            A3: [2, 2, 2, 2]
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("\uAC00\uB098");

        foreach (var p in prosody)
        {
            Assert.NotNull(p);
            Assert.Equal(0, p!.Value.A1);
            Assert.Equal(0, p!.Value.A2);
            Assert.Equal(2, p!.Value.A3);
        }
    }

    // ================================================================
    // 4. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        // Korean models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 5. PostProcessIds_AddsBosEos
    // ================================================================

    [Fact]
    public void PostProcessIds_AddsBosEos()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

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
    // 6. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        // Input: two phoneme IDs.
        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 2), new(0, 0, 2),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected:
        // BOS(1), PAD(0), 10, PAD(0), 11, PAD(0), EOS(2)
        // = [1, 0, 10, 0, 11, 0, 2]
        Assert.Equal([1, 0, 10, 0, 11, 0, 2], ids);

        // IDs and prosody must have the same length.
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 7. MismatchedArrayLengths_Throws
    // ================================================================

    [Fact]
    public void MismatchedArrayLengths_Throws()
    {
        // A1 array is shorter than Phonemes -> should throw InvalidOperationException.
        var g2p = new KoreanG2PResult(
            Phonemes: ["k", "a", "n", "a"],
            A1: [0, 0],              // length 2, mismatched with phonemes length 4
            A2: [0, 0, 0, 0],
            A3: [2, 2, 2, 2]
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        var ex = Assert.Throws<InvalidOperationException>(
            () => phonemizer.PhonemizeWithProsody("\uAC00\uB098"));

        Assert.Contains("inconsistent lengths", ex.Message);
    }

    // ================================================================
    // 8. EmptyInput_ReturnsEmpty
    // ================================================================

    [Fact]
    public void EmptyInput_ReturnsEmpty()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 9. PostProcessIds_EmptyInput
    // ================================================================

    [Fact]
    public void PostProcessIds_EmptyInput()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Empty input should still produce BOS(1), PAD(0), EOS(2).
        Assert.Equal([1, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 10. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: ["k", "a", "n", "a"],
            A1: [0, 0, 0, 0],
            A2: [0, 0, 0, 0],
            A3: [2, 2, 2, 2]
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        // Call Phonemize() (not PhonemizeWithProsody) and verify it returns tokens.
        var tokens = phonemizer.Phonemize("\uAC00\uB098");

        Assert.Equal(["k", "a", "n", "a"], tokens);
    }

    // ================================================================
    // 11. PhonemizeWithProsody_EmptyInput
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyInput()
    {
        // Engine returns empty phonemes and prosody arrays.
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("any text");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 12. PostProcessIds_SkipsPadAfterPadToken
    // ================================================================

    [Fact]
    public void PostProcessIds_SkipsPadAfterPadToken()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        // Input contains a PAD token (0) between two phoneme IDs.
        var inputIds = new List<int> { 10, 0, 11 };
        var inputProsody = new List<ProsodyInfo?> { null, null, null };
        var map = MakeMap();

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // The PAD token (0) should not get another PAD inserted after it.
        // Expected: BOS(1), PAD(0), 10, PAD(0), 0, 11, PAD(0), EOS(2)
        Assert.Equal([1, 0, 10, 0, 0, 11, 0, 2], ids);
    }

    // ================================================================
    // 13. PostProcessIds_ProsodyAlignmentWithPadSkip
    // ================================================================

    [Fact]
    public void PostProcessIds_ProsodyAlignmentWithPadSkip()
    {
        var g2p = new KoreanG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new KoreanPhonemizer(new StubKoreanG2PEngine(g2p));

        // Input with a PAD token (0) that triggers the skip logic.
        var inputIds = new List<int> { 10, 0, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(0, 0, 2), null, new(0, 0, 2),
        };
        var map = MakeMap();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Prosody list length must always match IDs list length.
        Assert.Equal(ids.Count, prosody.Count);

        // BOS and EOS positions should have null prosody.
        Assert.Null(prosody[0]); // BOS
        Assert.Null(prosody[^1]); // EOS
    }
}
