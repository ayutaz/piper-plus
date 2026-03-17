using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Integration tests for <see cref="JapanesePhonemizer"/>.
/// Verifies the full E2E flow: G2P result -> prosody mark insertion ->
/// N mutation -> PUA mapping -> prosody alignment, using a stubbed
/// <see cref="IJapaneseG2PEngine"/>.
/// </summary>
public sealed class JapanesePhonemizerTests
{
    // ================================================================
    // Stub G2P engine
    // ================================================================

    private class StubG2PEngine : IJapaneseG2PEngine
    {
        private readonly G2PResult _result;
        public StubG2PEngine(G2PResult result) => _result = result;
        public G2PResult Convert(string text) => _result;
    }

    // ================================================================
    // 1. BasicPhonemes_ConvertedCorrectly
    // ================================================================

    [Fact]
    public void BasicPhonemes_ConvertedCorrectly()
    {
        // "konnichiwa" (こんにちは) — G2P output
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "sil"],
            A1: [0, -4, -4, -3, -3, -2, -2, -1, 0, 0, 0],
            A2: [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 0],
            A3: [0, 5, 5, 5, 5, 5, 5, 5, 5, 5, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("こんにちは");

        // First "sil" -> "^" (BOS)
        Assert.Equal("^", tokens[0]);

        // Last "sil" -> "$" (declarative EOS)
        Assert.Equal("$", tokens[^1]);

        // "ch" should be mapped to PUA U+E00E
        Assert.Contains("\uE00E", tokens);

        // "N" should have been mutated (not remain as raw "N")
        Assert.DoesNotContain("N", tokens);

        // Token and prosody lists must be the same length
        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 2. QuestionText_GetsQuestionMarker
    // ================================================================

    [Fact]
    public void QuestionText_GetsQuestionMarker()
    {
        // Minimal G2P: just BOS phoneme + EOS phoneme
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "sil"],
            A1: [0, -1, 0, 0],
            A2: [0, 1, 2, 0],
            A3: [0, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("何ですか\uFF1F");

        // Last token should be "?" (mapped by GetQuestionType for full-width ？)
        Assert.Equal("?", tokens[^1]);
    }

    // ================================================================
    // 3. NMutation_AppliedCorrectly
    // ================================================================

    [Fact]
    public void NMutation_AppliedCorrectly()
    {
        // "sanpo" (さんぽ) — N before p -> N_m (bilabial)
        var g2p = new G2PResult(
            Phonemes: ["sil", "s", "a", "N", "p", "o", "sil"],
            A1: [0, -2, -2, -1, 0, 0, 0],
            A2: [0, 1, 1, 2, 3, 3, 0],
            A3: [0, 3, 3, 3, 3, 3, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("さんぽ");

        // N_m is mapped to PUA U+E019
        Assert.Contains("\uE019", tokens);

        // Raw "N" must not appear
        Assert.DoesNotContain("N", tokens);

        // "p" should remain as-is (single char, no PUA mapping)
        Assert.Contains("p", tokens);
    }

    // ================================================================
    // 4. ProsodyAlignment_Maintained
    // ================================================================

    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        // A sequence that triggers prosody mark insertion.
        // "kaki" with accent fall after first mora (a1=0, a2_next=a2+1 -> "]")
        // and phrase boundary at end (a2==a3 && a2_next==1 -> "#")
        // followed by second phrase with rising "[" (a2==1, a2_next==2).
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "k", "i", "pau", "k", "a", "k", "i", "sil"],
            A1: [0, -1, 0, 1, 1, 0, -1, 0, 1, 1, 0],
            A2: [0, 1, 2, 3, 3, 0, 1, 2, 3, 3, 0],
            A3: [0, 3, 3, 3, 3, 0, 3, 3, 3, 3, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("柿柿");

        // Prosody marks (], #, [) have null prosody
        Assert.Equal(tokens.Count, prosody.Count);

        // Check that any prosody marks have null prosody
        for (int i = 0; i < tokens.Count; i++)
        {
            var tok = tokens[i];
            if (tok == "]" || tok == "#" || tok == "[")
            {
                Assert.Null(prosody[i]);
            }
        }
    }

    // ================================================================
    // 5. PauToken_ConvertedToUnderscore
    // ================================================================

    [Fact]
    public void PauToken_ConvertedToUnderscore()
    {
        // "pau" in the middle of the sequence
        var g2p = new G2PResult(
            Phonemes: ["sil", "a", "pau", "i", "sil"],
            A1: [0, 0, 0, 0, 0],
            A2: [0, 1, 0, 1, 0],
            A3: [0, 1, 0, 1, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("あ、い");

        // "pau" should become "_"
        Assert.Contains("_", tokens);

        // "pau" should not appear in the output
        Assert.DoesNotContain("pau", tokens);

        // "_" prosody should be null
        int idx = tokens.IndexOf("_");
        Assert.Null(prosody[idx]);
    }

    // ================================================================
    // 6. AccentMarks_InsertedCorrectly
    // ================================================================

    [Fact]
    public void AccentMarks_InsertedCorrectly()
    {
        // Set up: phoneme at idx=1 has a1=0, a2=3, a3=5.
        // Next phoneme at idx=2 has a2=4 (== a2+1).
        // This triggers "]" insertion (accent nucleus mark).
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "k", "i", "k", "o", "sil"],
            A1: [0, -2, -1, 0, 1, 2, 2, 0],
            A2: [0, 1, 2, 3, 4, 5, 5, 0],
            A3: [0, 5, 5, 5, 5, 5, 5, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("かきこ");

        // "]" should be inserted after the phoneme where a1==0 and a2_next==a2+1
        Assert.Contains("]", tokens);

        // "]" prosody should be null
        int bracketIdx = tokens.IndexOf("]");
        Assert.True(bracketIdx > 0, "']' should not be the first token");
        Assert.Null(prosody[bracketIdx]);
    }

    // ================================================================
    // 7. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var g2p = new G2PResult(
            Phonemes: ["sil", "a", "sil"],
            A1: [0, 0, 0],
            A2: [0, 1, 0],
            A3: [0, 1, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));

        // Japanese models use config.json for the phoneme ID map
        Assert.Null(phonemizer.GetPhonemeIdMap());
    }

    // ================================================================
    // 8. EmptyInput_ReturnsEmpty
    // ================================================================

    [Fact]
    public void EmptyInput_ReturnsEmpty()
    {
        var g2p = new G2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }
}
