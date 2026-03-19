using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="ChinesePhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> token pass-through ->
/// prosody alignment -> PostProcessIds BOS/EOS/PAD,
/// using a stubbed <see cref="IChineseG2PEngine"/>.
/// </summary>
public sealed class ChinesePhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubChineseG2PEngine : IChineseG2PEngine
    {
        private readonly ChineseG2PResult _result;
        public StubChineseG2PEngine(ChineseG2PResult result) => _result = result;
        public ChineseG2PResult Convert(string text) => _result;
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
    };

    // ================================================================
    // 1. BasicPhonemes_PassedThrough
    // ================================================================

    [Fact]
    public void BasicPhonemes_PassedThrough()
    {
        // "ni hao" -> engine tokens appear in output unchanged.
        var g2p = new ChineseG2PResult(
            Phonemes: ["n", "i", "x", "a", "o"],
            A1: [3, 3, 3, 3, 3],
            A2: [1, 1, 1, 1, 1],
            A3: [1, 1, 1, 1, 1]
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("你好");

        Assert.Equal(["n", "i", "x", "a", "o"], tokens);
    }

    // ================================================================
    // 2. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: ["n", "i", "x", "a", "o"],
            A1: [3, 3, 3, 3, 3],
            A2: [1, 1, 2, 2, 2],
            A3: [2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("你好");

        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 3. Prosody_ToneValues
    // ================================================================

    [Fact]
    public void Prosody_ToneValues()
    {
        // "ni3 hao3" -> tone 3 for both syllables.
        var g2p = new ChineseG2PResult(
            Phonemes: ["n", "i", "x", "a", "o"],
            A1: [3, 3, 3, 3, 3],
            A2: [1, 1, 2, 2, 2],
            A3: [2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("你好");

        // All A1 values should be tone 3 (preserved from engine).
        foreach (var p in prosody)
        {
            Assert.NotNull(p);
            Assert.Equal(3, p!.A1);
        }
    }

    // ================================================================
    // 4. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));

        // Chinese models use the phoneme-ID map from config.json.
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 5. PostProcessIds_AddsBosEos
    // ================================================================

    [Fact]
    public void PostProcessIds_AddsBosEos()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));

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
    // 6. PostProcessIds_InsertsInterPhonemePad
    // ================================================================

    [Fact]
    public void PostProcessIds_InsertsInterPhonemePad()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));

        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?> { null, null };
        var map = MakeMap();

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Pattern: BOS(1), PAD(0), 10, PAD(0), 11, PAD(0), EOS(2)
        // Check that PAD (0) appears between phoneme IDs.
        int bosAndPadCount = 2; // BOS(1) + PAD(0)
        Assert.Equal(0, ids[bosAndPadCount + 1]); // PAD after first phoneme
    }

    // ================================================================
    // 7. PostProcessIds_FullSequence
    // ================================================================

    [Fact]
    public void PostProcessIds_FullSequence()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));

        // Input: two phoneme IDs.
        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new(3, 1, 1), new(3, 1, 1),
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
    // 8. MismatchedArrayLengths_Throws
    // ================================================================

    [Fact]
    public void MismatchedArrayLengths_Throws()
    {
        // A1 array is shorter than Phonemes -> should throw InvalidOperationException.
        var g2p = new ChineseG2PResult(
            Phonemes: ["n", "i", "x", "a", "o"],
            A1: [3, 3],              // length 2, mismatched with phonemes length 5
            A2: [1, 1, 2, 2, 2],
            A3: [2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));

        var ex = Assert.Throws<InvalidOperationException>(
            () => phonemizer.PhonemizeWithProsody("你好"));

        Assert.Contains("inconsistent lengths", ex.Message);
    }

    // ================================================================
    // 9. EmptyInput_ReturnsEmpty
    // ================================================================

    [Fact]
    public void EmptyInput_ReturnsEmpty()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new ChinesePhonemizer(new StubChineseG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }
}
