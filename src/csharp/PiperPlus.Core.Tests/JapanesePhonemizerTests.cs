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

    // ================================================================
    // 9. PhonemizeCore_InvalidG2PResult_MismatchedArrayLengths
    // ================================================================

    [Fact]
    public void PhonemizeCore_InvalidG2PResult_MismatchedArrayLengths()
    {
        // A1 array is shorter than Phonemes -> should throw InvalidOperationException
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "sil"],
            A1: [0, -1],            // length 2, mismatched with phonemes length 4
            A2: [0, 1, 2, 0],
            A3: [0, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));

        var ex = Assert.Throws<System.InvalidOperationException>(
            () => phonemizer.PhonemizeWithProsody("テスト"));

        Assert.Contains("inconsistent lengths", ex.Message);
    }

    // ================================================================
    // 10. Phonemize_ReturnsTokensOnly
    // ================================================================

    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        // Call Phonemize() (not PhonemizeWithProsody) and verify tokens
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "sil"],
            A1: [0, -1, 0, 0],
            A2: [0, 1, 2, 0],
            A3: [0, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        List<string> tokens = phonemizer.Phonemize("か");

        // Should produce BOS + phonemes + EOS
        Assert.Equal("^", tokens[0]);
        Assert.Equal("$", tokens[^1]);

        // "k" should be present
        Assert.Contains("k", tokens);

        // "a" should be present
        Assert.Contains("a", tokens);

        // Must not contain raw "sil" or "pau"
        Assert.DoesNotContain("sil", tokens);
    }

    // ================================================================
    // 11. PhonemizeWithProsody_EmptyPhonemes
    // ================================================================

    [Fact]
    public void PhonemizeWithProsody_EmptyPhonemes()
    {
        // Engine returns empty arrays -> empty result from PhonemizeWithProsody
        var g2p = new G2PResult(
            Phonemes: [],
            A1: [],
            A2: [],
            A3: []
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("何か");

        // Even though input text is non-empty, empty G2P means empty output
        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 12. AccentNucleusMark_InsertedAtCorrectPosition
    // ================================================================

    [Fact]
    public void AccentNucleusMark_InsertedAtCorrectPosition()
    {
        // Design input so that exactly one "]" is triggered:
        // Condition: a1==0 && a2_next == a2+1
        // "ka" with 2 morae, accent on mora 1 (a1 goes -1, 0).
        // idx=1 "k": a1=-1, a2=1 -> no trigger (a1 != 0)
        // idx=2 "a": a1=0, a2=2, a2_next(sil)=-1 -> no (a2_next != a2+1)
        // Need: phoneme where a1==0 and next phoneme's a2 == current a2 + 1.
        // "kaki" (2 morae): k a k i, accent on 1st mora.
        // a1: -1 0 1 1   a2: 1 1 2 2   a3: 2 2 2 2
        // Wait — a1 and a2 apply per-phoneme, with consonant+vowel sharing the same mora.
        // Let's use: "ka" = mora1, "ki" = mora2, accent falls after mora1.
        // idx=1 "k": a1=-1, a2=1, a3=2 -> a2_next(idx2)=1 -> no
        // idx=2 "a": a1=0, a2=1, a3=2 -> a2_next(idx3)=2 -> a2+1=2 YES -> "]"
        // idx=3 "k": a1=1, a2=2 -> no (a1!=0)
        // idx=4 "i": a1=1, a2=2 -> no (a1!=0)
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "k", "i", "sil"],
            A1: [0, -1, 0, 1, 1, 0],
            A2: [0, 1, 1, 2, 2, 0],
            A3: [0, 2, 2, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("かき");

        // Exactly one "]" should be inserted
        int count = tokens.Count(t => t == "]");
        Assert.Equal(1, count);

        // "]" must appear right after "a" (the accent nucleus phoneme)
        int aIdx = tokens.IndexOf("a");
        Assert.True(aIdx >= 0, "'a' must be present");
        Assert.Equal("]", tokens[aIdx + 1]);

        // "]" prosody must be null
        Assert.Null(prosody[aIdx + 1]);
    }

    // ================================================================
    // 13. AccentPhraseBoundary_InsertedCorrectly
    // ================================================================

    [Fact]
    public void AccentPhraseBoundary_InsertedCorrectly()
    {
        // Condition: a2==a3 && a2_next==1 -> "#"
        // Phrase 1: "kaki" (2 morae), Phrase 2: "kaku" (2 morae).
        //   idx=0 sil: ignored
        //   idx=1 k:  a1=1, a2=1, a3=2 -> a2!=a3, no boundary
        //   idx=2 a:  a1=1, a2=1, a3=2 -> a2!=a3, no boundary
        //   idx=3 k:  a1=1, a2=2, a3=2 -> a2==a3, a2_next(idx4 "i")=2 -> 2!=1, no
        //   idx=4 i:  a1=1, a2=2, a3=2 -> a2==a3, a2_next(idx5 "k")=1 -> "#" YES
        //   idx=5 k:  a1=1, a2=1, a3=2 -> a2!=a3, no boundary
        //   idx=6 a:  a1=1, a2=1, a3=2 -> a2!=a3, no boundary
        //   idx=7 k:  a1=1, a2=2, a3=2 -> a2==a3, a2_next(idx8 "u")=2 -> 2!=1, no
        //   idx=8 u:  a1=1, a2=2, a3=2 -> a2==a3, a2_next(sil)=0 -> 0!=1, no
        //   idx=9 sil: EOS
        // a1 set to 1 everywhere to avoid triggering "]" (a1==0 needed).
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "k", "i", "k", "a", "k", "u", "sil"],
            A1: [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
            A2: [0, 1, 1, 2, 2, 1, 1, 2, 2, 0],
            A3: [0, 2, 2, 2, 2, 2, 2, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("かきかく");

        // "#" should be present
        Assert.Contains("#", tokens);

        // Exactly one "#"
        Assert.Equal(1, tokens.Count(t => t == "#"));

        // "#" must appear after "i" (last phoneme of phrase 1)
        int iIdx = tokens.IndexOf("i");
        Assert.True(iIdx >= 0, "'i' must be present");

        int hashIdx = tokens.IndexOf("#");
        Assert.Equal(iIdx + 1, hashIdx);

        // "#" prosody must be null
        Assert.Null(prosody[hashIdx]);
    }

    // ================================================================
    // 14. RisingMark_InsertedCorrectly
    // ================================================================

    [Fact]
    public void RisingMark_InsertedCorrectly()
    {
        // Condition: a2==1 && a2_next==2 -> "["
        // A phrase with at least 2 morae: "kaki" (2 morae, no accent fall).
        // k(a2=1) a(a2=1) k(a2=2) i(a2=2).
        // idx=2 "a": a2=1, a2_next(idx3 "k")=2 -> "[" YES
        // Set a1 values so that "]" is NOT triggered (a1 != 0 for "a").
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "k", "i", "sil"],
            A1: [0, -1, -1, 0, 0, 0],
            A2: [0, 1, 1, 2, 2, 0],
            A3: [0, 2, 2, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, prosody) = phonemizer.PhonemizeWithProsody("かき");

        // "[" should be present
        Assert.Contains("[", tokens);

        // "[" must appear after "a" (end of mora 1, where a2==1 -> a2_next==2)
        int aIdx = tokens.IndexOf("a");
        Assert.True(aIdx >= 0, "'a' must be present");
        Assert.Equal("[", tokens[aIdx + 1]);

        // "[" prosody must be null
        Assert.Null(prosody[aIdx + 1]);

        // "]" should NOT be present (a1 != 0 for "a")
        Assert.DoesNotContain("]", tokens);
    }

    // ================================================================
    // 15. NMutation_UvularAtEndOfPhrase
    // ================================================================

    [Fact]
    public void NMutation_UvularAtEndOfPhrase()
    {
        // "N" at end of phrase (before sil) -> N_uvular (PUA U+E01C)
        var g2p = new G2PResult(
            Phonemes: ["sil", "k", "a", "N", "sil"],
            A1: [0, -1, 0, 1, 0],
            A2: [0, 1, 1, 2, 0],
            A3: [0, 2, 2, 2, 0]
        );

        var phonemizer = new JapanesePhonemizer(new StubG2PEngine(g2p));
        var (tokens, _) = phonemizer.PhonemizeWithProsody("かん");

        // N_uvular is mapped to PUA U+E01C
        Assert.Contains("\uE01C", tokens);

        // Raw "N" must not appear
        Assert.DoesNotContain("N", tokens);
    }
}
