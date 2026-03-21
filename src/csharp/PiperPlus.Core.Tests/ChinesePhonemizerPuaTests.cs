using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Tests for Chinese tone marker insertion and prosody alignment
/// through the <see cref="ChinesePhonemizer"/> + stub
/// <see cref="IChineseG2PEngine"/> pipeline.
/// <para>
/// These tests simulate what <c>DotNetChineseG2PEngine</c> produces
/// (PUA-mapped initials/finals + tone PUA markers + per-token prosody)
/// and verify that <see cref="ChinesePhonemizer"/> correctly passes
/// through and aligns the data.
/// </para>
/// </summary>
public sealed class ChinesePhonemizerPuaTests
{
    // ================================================================
    // PUA constants matching DotNetChineseG2PEngine
    // ================================================================

    // Tone marker PUA characters (U+E046-U+E04A)
    private const string Tone1 = "\uE046"; // 阴平
    private const string Tone2 = "\uE047"; // 阳平
    private const string Tone3 = "\uE048"; // 上声
    private const string Tone4 = "\uE049"; // 去声
    private const string Tone5 = "\uE04A"; // 轻声

    // Sample PUA-mapped initials/finals (matching zh_id_map ranges)
    private const string PuaN = "\uE020";   // n initial
    private const string PuaI = "\uE021";   // i final
    private const string PuaX = "\uE022";   // x initial
    private const string PuaA = "\uE023";   // a
    private const string PuaO = "\uE024";   // o final

    // ================================================================
    // Stub G2P engine
    // ================================================================

    /// <summary>
    /// Stub that returns pre-built <see cref="ChineseG2PResult"/>
    /// mimicking the output of <c>DotNetChineseG2PEngine</c>
    /// (PUA phonemes + tone markers + aligned prosody).
    /// </summary>
    private sealed class ToneStubEngine : IChineseG2PEngine
    {
        private readonly ChineseG2PResult _result;
        public ToneStubEngine(ChineseG2PResult result) => _result = result;
        public ChineseG2PResult Convert(string text) => _result;
    }

    // ================================================================
    // 1. TwoSyllable_ToneMarkersPresent
    // ================================================================

    /// <summary>
    /// Simulates "你好" (ni3 hao3):
    ///   DotNetG2P produces [n, i, tone3, x, a, o, tone3]
    /// Verifies that <see cref="ChinesePhonemizer"/> passes through
    /// all 7 tokens including the tone markers.
    /// </summary>
    [Fact]
    public void TwoSyllable_ToneMarkersPresent()
    {
        // Engine output: ni3 -> [n, i, tone3], hao3 -> [x, a, o, tone3]
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaN, PuaI, Tone3, PuaX, PuaA, PuaO, Tone3],
            A1: [3, 3, 3, 3, 3, 3, 3],
            A2: [1, 1, 1, 2, 2, 2, 2],
            A3: [2, 2, 2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("你好");

        // Should contain exactly the 7 tokens including tone markers
        Assert.Equal(7, tokens.Count);
        Assert.Equal(Tone3, tokens[2]); // tone marker after first syllable
        Assert.Equal(Tone3, tokens[6]); // tone marker after second syllable
    }

    // ================================================================
    // 2. ProsodyAligned_WithToneMarkers
    // ================================================================

    /// <summary>
    /// Verifies that prosody arrays are aligned 1:1 with phoneme tokens,
    /// including at tone marker positions.
    /// </summary>
    [Fact]
    public void ProsodyAligned_WithToneMarkers()
    {
        // "你好" with tone markers included in engine output
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaN, PuaI, Tone3, PuaX, PuaA, PuaO, Tone3],
            A1: [3, 3, 3, 3, 3, 3, 3],
            A2: [1, 1, 1, 2, 2, 2, 2],
            A3: [2, 2, 2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("你好");

        // Prosody list must have the same length as tokens
        Assert.Equal(tokens.Count, prosody.Count);

        // Every token (including tone markers) should have non-null prosody
        for (int i = 0; i < prosody.Count; i++)
        {
            Assert.NotNull(prosody[i]);
        }

        // Tone marker positions should carry the syllable's A1 value
        Assert.Equal(3, prosody[2]!.Value.A1); // tone3 marker for syllable 1
        Assert.Equal(3, prosody[6]!.Value.A1); // tone3 marker for syllable 2
    }

    // ================================================================
    // 3. FourTones_DistinctMarkers
    // ================================================================

    /// <summary>
    /// Tests all four lexical tones plus neutral tone (5) to verify
    /// each tone marker PUA character is distinct.
    /// </summary>
    [Fact]
    public void FourTones_DistinctMarkers()
    {
        // Simulate 5 single-phoneme syllables, one for each tone
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaA, Tone1, PuaA, Tone2, PuaA, Tone3, PuaA, Tone4, PuaA, Tone5],
            A1: [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
            A2: [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
            A3: [5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("妈麻马骂吗");

        // 5 phonemes + 5 tone markers = 10 tokens
        Assert.Equal(10, tokens.Count);

        // Verify each tone marker is distinct
        Assert.Equal(Tone1, tokens[1]);
        Assert.Equal(Tone2, tokens[3]);
        Assert.Equal(Tone3, tokens[5]);
        Assert.Equal(Tone4, tokens[7]);
        Assert.Equal(Tone5, tokens[9]);

        // Verify A1 values match tone numbers at marker positions
        Assert.Equal(1, prosody[1]!.Value.A1);
        Assert.Equal(2, prosody[3]!.Value.A1);
        Assert.Equal(3, prosody[5]!.Value.A1);
        Assert.Equal(4, prosody[7]!.Value.A1);
        Assert.Equal(5, prosody[9]!.Value.A1);
    }

    // ================================================================
    // 4. SyllablePosition_A2Preserved
    // ================================================================

    /// <summary>
    /// Verifies that A2 (syllable position within word) is correctly
    /// preserved through the phonemizer for a multi-syllable word.
    /// </summary>
    [Fact]
    public void SyllablePosition_A2Preserved()
    {
        // "你好吗" (3-syllable word): A2 = 1, 2, 3
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaN, PuaI, Tone3, PuaX, PuaA, PuaO, Tone3, PuaN, PuaA, Tone5],
            A1: [3, 3, 3, 3, 3, 3, 3, 5, 5, 5],
            A2: [1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
            A3: [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("你好吗");

        // First syllable tokens: A2=1
        Assert.Equal(1, prosody[0]!.Value.A2);
        Assert.Equal(1, prosody[1]!.Value.A2);
        Assert.Equal(1, prosody[2]!.Value.A2); // tone marker

        // Second syllable tokens: A2=2
        Assert.Equal(2, prosody[3]!.Value.A2);
        Assert.Equal(2, prosody[6]!.Value.A2); // tone marker

        // Third syllable tokens: A2=3
        Assert.Equal(3, prosody[7]!.Value.A2);
        Assert.Equal(3, prosody[9]!.Value.A2); // tone marker
    }

    // ================================================================
    // 5. WordLength_A3Preserved
    // ================================================================

    /// <summary>
    /// Verifies that A3 (word length in syllables) is correctly
    /// propagated to all tokens of a word.
    /// </summary>
    [Fact]
    public void WordLength_A3Preserved()
    {
        // Two words: "你" (1 syllable, A3=1) + "好吗" (2 syllables, A3=2)
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaN, PuaI, Tone3, PuaX, PuaA, PuaO, Tone3, PuaN, PuaA, Tone5],
            A1: [3, 3, 3, 3, 3, 3, 3, 5, 5, 5],
            A2: [1, 1, 1, 1, 1, 1, 1, 2, 2, 2],
            A3: [1, 1, 1, 2, 2, 2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (_, prosody) = phonemizer.PhonemizeWithProsody("你好吗");

        // First word (A3=1)
        Assert.Equal(1, prosody[0]!.Value.A3);
        Assert.Equal(1, prosody[2]!.Value.A3); // tone marker

        // Second word (A3=2)
        Assert.Equal(2, prosody[3]!.Value.A3);
        Assert.Equal(2, prosody[6]!.Value.A3); // tone marker
        Assert.Equal(2, prosody[9]!.Value.A3); // tone marker
    }

    // ================================================================
    // 6. PostProcessIds_ToneMarkersGetBosEosPad
    // ================================================================

    /// <summary>
    /// Verifies that the full pipeline (phonemize -> ID lookup ->
    /// PostProcessIds) correctly wraps tone markers with BOS/EOS/PAD.
    /// </summary>
    [Fact]
    public void PostProcessIds_ToneMarkersGetBosEosPad()
    {
        // Simple: one phoneme + one tone marker
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaA, Tone1],
            A1: [1, 1],
            A2: [1, 1],
            A3: [1, 1]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));

        // Simulate phoneme ID map that maps PUA chars to IDs
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
            [PuaA] = [10],
            [Tone1] = [20],
        };

        var inputIds = new List<int> { 10, 20 };
        var inputProsody = new List<ProsodyInfo?> { new(1, 1, 1), new(1, 1, 1) };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected: BOS(1), PAD(0), 10, PAD(0), 20, PAD(0), EOS(2)
        Assert.Equal([1, 0, 10, 0, 20, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 7. EmptyPhonemes_WithToneOnly_Handled
    // ================================================================

    /// <summary>
    /// Edge case: engine returns only tone markers (no initials/finals).
    /// The phonemizer should still pass through and align correctly.
    /// </summary>
    [Fact]
    public void EmptyPhonemes_WithToneOnly_Handled()
    {
        var g2p = new ChineseG2PResult(
            Phonemes: [Tone3],
            A1: [3],
            A2: [1],
            A3: [1]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("x");

        Assert.Single(tokens);
        Assert.Equal(Tone3, tokens[0]);
        Assert.Single(prosody);
        Assert.Equal(3, prosody[0]!.Value.A1);
    }

    // ================================================================
    // 8. MultipleWords_ProsodyBoundaries
    // ================================================================

    /// <summary>
    /// Verifies prosody boundaries are correct across multiple words:
    /// "我 爱 中国" -> 3 words, 4 syllables total.
    /// </summary>
    [Fact]
    public void MultipleWords_ProsodyBoundaries()
    {
        // "我" (tone3, A2=1, A3=1), "爱" (tone4, A2=1, A3=1),
        // "中" (tone1, A2=1, A3=2), "国" (tone2, A2=2, A3=2)
        var g2p = new ChineseG2PResult(
            Phonemes: [PuaO, Tone3, PuaA, PuaI, Tone4, PuaN, PuaO, Tone1, PuaN, PuaO, Tone2],
            A1: [3, 3, 4, 4, 4, 1, 1, 1, 2, 2, 2],
            A2: [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2],
            A3: [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2]
        );

        var phonemizer = new ChinesePhonemizer(new ToneStubEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("我爱中国");

        Assert.Equal(11, tokens.Count);
        Assert.Equal(tokens.Count, prosody.Count);

        // Verify word boundary: "我" (A3=1) -> "爱" (A3=1) -> "中国" (A3=2)
        Assert.Equal(1, prosody[0]!.Value.A3);  // 我
        Assert.Equal(1, prosody[2]!.Value.A3);  // 爱
        Assert.Equal(2, prosody[5]!.Value.A3);  // 中 (first syllable of 2-syllable word)
        Assert.Equal(2, prosody[8]!.Value.A3);  // 国 (second syllable)
    }
}
