using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="MultilingualPhonemizer"/>.
/// <para>
/// Uses stub <see cref="IPhonemizer"/> implementations that return fixed
/// tokens (including BOS "^" / EOS "$") so we can verify segment
/// concatenation, BOS/EOS stripping, question-marker tracking, prosody
/// alignment, and PostProcessIds delegation.
/// </para>
/// </summary>
public sealed class MultilingualPhonemizerTests
{
    // ================================================================
    // Stub phonemizer -- returns fixed tokens for any text
    // ================================================================

    /// <summary>
    /// Minimal <see cref="IPhonemizer"/> stub that returns pre-configured
    /// tokens and prosody regardless of input text. Used to verify the
    /// multilingual orchestration layer without real G2P engines.
    /// </summary>
    private class StubPhonemizer : IPhonemizer
    {
        private readonly List<string> _tokens;
        private readonly List<ProsodyInfo?> _prosody;

        public StubPhonemizer(List<string> tokens, List<ProsodyInfo?> prosody)
        {
            _tokens = tokens;
            _prosody = prosody;
        }

        public List<string> Phonemize(string text) => _tokens;

        public (List<string>, List<ProsodyInfo?>) PhonemizeWithProsody(string text)
            => (_tokens, _prosody);

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;
    }

    // ================================================================
    // Shared helpers
    // ================================================================

    /// <summary>
    /// JA stub: returns ["^", "k", "o", "$"] with prosody for real phonemes.
    /// </summary>
    private static StubPhonemizer MakeJaStub() => new(
        new List<string> { "^", "k", "o", "$" },
        new List<ProsodyInfo?>
        {
            null,                      // ^ (BOS)
            new ProsodyInfo(-1, 1, 2), // k
            new ProsodyInfo(0, 2, 2),  // o
            null,                      // $ (EOS)
        });

    /// <summary>
    /// EN stub: returns ["h", "e", "l", "o"] with prosody (no BOS/EOS).
    /// </summary>
    private static StubPhonemizer MakeEnStub() => new(
        new List<string> { "h", "e", "l", "o" },
        new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 0, 4),
            new ProsodyInfo(0, 2, 4),
            new ProsodyInfo(0, 0, 4),
            new ProsodyInfo(0, 2, 4),
        });

    /// <summary>
    /// JA stub with question marker: returns ["^", "k", "a", "?"] --
    /// the EOS is "?" instead of "$".
    /// </summary>
    private static StubPhonemizer MakeJaQuestionStub() => new(
        new List<string> { "^", "k", "a", "?" },
        new List<ProsodyInfo?>
        {
            null,                      // ^ (BOS)
            new ProsodyInfo(-1, 1, 2), // k
            new ProsodyInfo(0, 2, 2),  // a
            null,                      // ? (EOS)
        });

    /// <summary>
    /// JA stub with emphasis question marker (PUA U+E016 "?!"):
    /// returns ["^", "k", "a", "\uE016"].
    /// </summary>
    private static StubPhonemizer MakeJaEmphasisQuestionStub() => new(
        new List<string> { "^", "k", "a", "\uE016" },
        new List<ProsodyInfo?>
        {
            null,                      // ^ (BOS)
            new ProsodyInfo(-1, 1, 2), // k
            new ProsodyInfo(0, 2, 2),  // a
            null,                      // ?! EOS (PUA)
        });

    /// <summary>
    /// Create a <see cref="MultilingualPhonemizer"/> with JA and EN stubs.
    /// </summary>
    private static MultilingualPhonemizer MakeMultilingual(
        StubPhonemizer jaStub,
        StubPhonemizer enStub) => new(
        new Dictionary<string, IPhonemizer>
        {
            ["ja"] = jaStub,
            ["en"] = enStub,
        });

    /// <summary>
    /// Standard phoneme-ID map for PostProcessIds tests.
    /// </summary>
    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],    // PAD
        ["^"] = [1],    // BOS
        ["$"] = [2],    // declarative EOS
        ["?"] = [3],    // question EOS
        ["\uE016"] = [4], // ?! (PUA emphasis question)
        ["\uE017"] = [5], // ?. (PUA neutral question)
        ["\uE018"] = [6], // ?~ (PUA tag question)
        ["k"] = [10],
        ["o"] = [11],
        ["a"] = [12],
        ["h"] = [20],
        ["e"] = [21],
        ["l"] = [22],
    };

    // ================================================================
    // 1. SingleSegment_PassesThrough
    // ================================================================

    /// <summary>
    /// Japanese-only text delegates to the JA phonemizer.
    /// BOS "^" and EOS "$" from the individual segment are stripped by
    /// <see cref="MultilingualPhonemizer"/>; only real phonemes remain.
    /// </summary>
    [Fact]
    public void SingleSegment_PassesThrough()
    {
        // Japanese-only input: UnicodeLanguageDetector routes to JA.
        // JA stub returns ["^", "k", "o", "$"].
        // After stripping BOS/EOS, only ["k", "o"] should remain.
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        var (tokens, prosody) = multilingual.PhonemizeWithProsody("\u3053\u3093");  // こん (kana-only)

        // BOS/EOS should have been stripped
        Assert.DoesNotContain("^", tokens);
        Assert.DoesNotContain("$", tokens);

        // The JA stub's real phonemes pass through
        Assert.Equal(new List<string> { "k", "o" }, tokens);

        // Prosody alignment
        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 2. MixedLanguages_ConcatenatesSegments
    // ================================================================

    /// <summary>
    /// Mixed text with kana + Latin produces JA segment + EN segment.
    /// Both segments have BOS/EOS stripped and are concatenated.
    /// </summary>
    [Fact]
    public void MixedLanguages_ConcatenatesSegments()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        // "\u3053\u3093hello" = "こんhello" -> JA segment + EN segment
        var (tokens, prosody) = multilingual.PhonemizeWithProsody("\u3053\u3093hello");

        // JA: ["^", "k", "o", "$"] -> stripped -> ["k", "o"]
        // EN: ["h", "e", "l", "o"] -> no BOS/EOS -> ["h", "e", "l", "o"]
        // Combined: ["k", "o", "h", "e", "l", "o"]
        Assert.Equal(6, tokens.Count);
        Assert.Equal("k", tokens[0]);
        Assert.Equal("o", tokens[1]);
        Assert.Equal("h", tokens[2]);
        Assert.Equal("e", tokens[3]);
        Assert.Equal("l", tokens[4]);
        Assert.Equal("o", tokens[5]);

        // Prosody must match token count
        Assert.Equal(tokens.Count, prosody.Count);
    }

    // ================================================================
    // 3. BosEos_StrippedFromSegments
    // ================================================================

    /// <summary>
    /// Verify that "^" (BOS) and "$" (EOS) are removed from individual
    /// segment output during multilingual concatenation.
    /// </summary>
    [Fact]
    public void BosEos_StrippedFromSegments()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        // JA-only input: the stub returns ["^", "k", "o", "$"]
        var (tokens, prosody) = multilingual.PhonemizeWithProsody("\u3053\u3093");

        // "^" and "$" must not appear in the output
        Assert.DoesNotContain("^", tokens);
        Assert.DoesNotContain("$", tokens);

        // Only the real phonemes remain
        Assert.Equal(new List<string> { "k", "o" }, tokens);

        // Prosody alignment maintained after stripping
        Assert.Equal(tokens.Count, prosody.Count);

        // Prosody values for stripped BOS/EOS (null) should NOT be present
        Assert.All(prosody, p => Assert.NotNull(p));
    }

    // ================================================================
    // 4. QuestionMarker_TrackedAsLastEos
    // ================================================================

    /// <summary>
    /// Japanese "?" (or PUA ?! U+E016) is tracked as the last EOS.
    /// After PhonemizeWithProsody, PostProcessIds should use this
    /// dynamic EOS rather than the default "$".
    /// </summary>
    [Fact]
    public void QuestionMarker_TrackedAsLastEos()
    {
        // Use question stub for JA
        var multilingual = MakeMultilingual(MakeJaQuestionStub(), MakeEnStub());

        // JA-only input with question: stub returns ["^", "k", "a", "?"]
        var (tokens, _) = multilingual.PhonemizeWithProsody("\u3053\u3093");

        // "?" should have been stripped (it's an EOS token)
        Assert.DoesNotContain("?", tokens);

        // But PostProcessIds should use "?" as the EOS.
        // Feed the stripped tokens through PostProcessIds with a map
        // that includes both "$" (ID=2) and "?" (ID=3).
        var map = MakeMap();
        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        foreach (var token in tokens)
        {
            if (map.TryGetValue(token, out var ids))
            {
                foreach (var id in ids)
                {
                    inputIds.Add(id);
                    inputProsody.Add(null);
                }
            }
        }

        var (resultIds, _) = multilingual.PostProcessIds(inputIds, inputProsody, map);

        // Last ID should be the "?" EOS (ID=3), not "$" (ID=2)
        Assert.Equal(3, resultIds[^1]);
    }

    // ================================================================
    // 5. ProsodyAlignment_Maintained
    // ================================================================

    /// <summary>
    /// After multilingual segment concatenation, tokens.Count must
    /// equal prosody.Count for each call.
    /// </summary>
    [Fact]
    public void ProsodyAlignment_Maintained()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        // JA-only
        var (jaTokens, jaProsody) = multilingual.PhonemizeWithProsody("\u3053\u3093");
        Assert.Equal(jaTokens.Count, jaProsody.Count);

        // Mixed JA + EN
        var multilingual2 = MakeMultilingual(MakeJaStub(), MakeEnStub());
        var (mixedTokens, mixedProsody) = multilingual2.PhonemizeWithProsody("\u3053\u3093hello");
        Assert.Equal(mixedTokens.Count, mixedProsody.Count);
    }

    // ================================================================
    // 6. GetPhonemeIdMap_ReturnsNull
    // ================================================================

    /// <summary>
    /// The multilingual phonemizer returns <c>null</c> for
    /// <see cref="IPhonemizer.GetPhonemeIdMap"/> -- the phoneme-ID map
    /// comes from config.json.
    /// </summary>
    [Fact]
    public void GetPhonemeIdMap_ReturnsNull()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        Assert.Null(multilingual.GetPhonemeIdMap());
    }

    // ================================================================
    // 7. EmptyInput_ReturnsEmpty
    // ================================================================

    /// <summary>
    /// Empty input text should produce empty tokens and prosody lists.
    /// </summary>
    [Fact]
    public void EmptyInput_ReturnsEmpty()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        var (tokens, prosody) = multilingual.PhonemizeWithProsody("");

        Assert.Empty(tokens);
        Assert.Empty(prosody);
    }

    // ================================================================
    // 8. PostProcessIds_UsesLastEos
    // ================================================================

    /// <summary>
    /// Verify that <see cref="MultilingualPhonemizer.PostProcessIds"/>
    /// uses the dynamic EOS captured from the last segment.
    /// <para>
    /// When the last segment is a Japanese question ("?"), PostProcessIds
    /// should emit EOS ID=3 (for "?") rather than ID=2 (for "$").
    /// When the last segment is declarative, it should emit ID=2 (for "$").
    /// </para>
    /// </summary>
    [Fact]
    public void PostProcessIds_UsesLastEos()
    {
        var map = MakeMap();

        // --- Declarative case: last EOS is "$" ---
        var declarativeMultilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());
        // Trigger PhonemizeWithProsody to capture _lastEos = "$"
        declarativeMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var inputIds = new List<int> { 10, 11 };  // k, o
        var inputProsody = new List<ProsodyInfo?> { null, null };

        var (declIds, declProsody) = declarativeMultilingual.PostProcessIds(
            inputIds, inputProsody, map);

        // Expected: BOS(1), PAD(0), 10, PAD(0), 11, PAD(0), EOS(2)
        Assert.Equal(1, declIds[0]);     // BOS
        Assert.Equal(2, declIds[^1]);    // declarative EOS "$"
        Assert.Equal(declIds.Count, declProsody.Count);

        // --- Question case: last EOS is "?" ---
        var questionMultilingual = MakeMultilingual(MakeJaQuestionStub(), MakeEnStub());
        // Trigger PhonemizeWithProsody to capture _lastEos = "?"
        questionMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var inputIds2 = new List<int> { 10, 12 };  // k, a
        var inputProsody2 = new List<ProsodyInfo?> { null, null };

        var (qIds, qProsody) = questionMultilingual.PostProcessIds(
            inputIds2, inputProsody2, map);

        // Expected: BOS(1), PAD(0), 10, PAD(0), 12, PAD(0), EOS(3)
        Assert.Equal(1, qIds[0]);       // BOS
        Assert.Equal(3, qIds[^1]);      // question EOS "?"
        Assert.Equal(qIds.Count, qProsody.Count);

        // --- PUA emphasis question case: last EOS is "\uE016" ---
        var emphMultilingual = MakeMultilingual(MakeJaEmphasisQuestionStub(), MakeEnStub());
        emphMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var inputIds3 = new List<int> { 10, 12 };  // k, a
        var inputProsody3 = new List<ProsodyInfo?> { null, null };

        var (emphIds, emphProsody) = emphMultilingual.PostProcessIds(
            inputIds3, inputProsody3, map);

        // Expected: BOS(1), PAD(0), 10, PAD(0), 12, PAD(0), EOS(4)
        Assert.Equal(1, emphIds[0]);     // BOS
        Assert.Equal(4, emphIds[^1]);    // emphasis question EOS "?!" (PUA)
        Assert.Equal(emphIds.Count, emphProsody.Count);
    }

    // ================================================================
    // 9. AllQuestionMarkerTypes
    // ================================================================

    /// <summary>
    /// Verify that all three PUA question markers are tracked as _lastEos
    /// and correctly emitted by PostProcessIds:
    /// <list type="bullet">
    ///   <item>\uE016 = ?! (emphasis question, ID=4)</item>
    ///   <item>\uE017 = ?. (neutral question, ID=5)</item>
    ///   <item>\uE018 = ?~ (tag question, ID=6)</item>
    /// </list>
    /// </summary>
    [Fact]
    public void AllQuestionMarkerTypes()
    {
        var map = MakeMap();

        // --- ?! (PUA U+E016) -> ID 4 ---
        var emphStub = new StubPhonemizer(
            new List<string> { "^", "k", "a", "\uE016" },
            new List<ProsodyInfo?> { null, new ProsodyInfo(-1, 1, 2), new ProsodyInfo(0, 2, 2), null });
        var emphMultilingual = MakeMultilingual(emphStub, MakeEnStub());
        emphMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var (emphIds, _) = emphMultilingual.PostProcessIds(
            new List<int> { 10, 12 }, new List<ProsodyInfo?> { null, null }, map);
        Assert.Equal(4, emphIds[^1]);

        // --- ?. (PUA U+E017) -> ID 5 ---
        var neutralStub = new StubPhonemizer(
            new List<string> { "^", "k", "a", "\uE017" },
            new List<ProsodyInfo?> { null, new ProsodyInfo(-1, 1, 2), new ProsodyInfo(0, 2, 2), null });
        var neutralMultilingual = MakeMultilingual(neutralStub, MakeEnStub());
        neutralMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var (neutralIds, _) = neutralMultilingual.PostProcessIds(
            new List<int> { 10, 12 }, new List<ProsodyInfo?> { null, null }, map);
        Assert.Equal(5, neutralIds[^1]);

        // --- ?~ (PUA U+E018) -> ID 6 ---
        var tagStub = new StubPhonemizer(
            new List<string> { "^", "k", "a", "\uE018" },
            new List<ProsodyInfo?> { null, new ProsodyInfo(-1, 1, 2), new ProsodyInfo(0, 2, 2), null });
        var tagMultilingual = MakeMultilingual(tagStub, MakeEnStub());
        tagMultilingual.PhonemizeWithProsody("\u3053\u3093");

        var (tagIds, _) = tagMultilingual.PostProcessIds(
            new List<int> { 10, 12 }, new List<ProsodyInfo?> { null, null }, map);
        Assert.Equal(6, tagIds[^1]);
    }

    // ================================================================
    // 10. PostProcessIds_DynamicEosFallback
    // ================================================================

    /// <summary>
    /// When _lastEos is a PUA token that is NOT present in the phoneme-ID
    /// map, PostProcessIds should fall back to the standard "$" EOS.
    /// </summary>
    [Fact]
    public void PostProcessIds_DynamicEosFallback()
    {
        // Use the emphasis question stub to set _lastEos = "\uE016"
        var multilingual = MakeMultilingual(MakeJaEmphasisQuestionStub(), MakeEnStub());
        multilingual.PhonemizeWithProsody("\u3053\u3093");

        // Build a map that does NOT include "\uE016" -- the PUA token
        var mapWithoutPua = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],    // standard EOS only
            ["k"] = [10],
            ["a"] = [12],
        };

        var (ids, prosody) = multilingual.PostProcessIds(
            new List<int> { 10, 12 },
            new List<ProsodyInfo?> { null, null },
            mapWithoutPua);

        // Should fall back to "$" EOS (ID=2) since "\uE016" is not in the map
        Assert.Equal(2, ids[^1]);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 11. ThreeSegments_ProperConcatenation
    // ================================================================

    /// <summary>
    /// JA + EN + JA segments are concatenated correctly with BOS/EOS
    /// stripped from each segment. The last segment's EOS is tracked.
    /// </summary>
    [Fact]
    public void ThreeSegments_ProperConcatenation()
    {
        // JA stub: ["^", "k", "o", "$"]  -> stripped -> ["k", "o"]
        // EN stub: ["h", "e", "l", "o"]  -> no BOS/EOS -> ["h", "e", "l", "o"]
        // For the second JA segment, use a question stub to verify _lastEos tracking.
        // We need to construct a multilingual that processes: JA text + EN text + JA text
        // Input: "こんhelloか" -> JA("こん") + EN("hello") + JA("か")
        //
        // Since both JA segments use the same stub, both will return
        // the same tokens. The result should be:
        // ["k", "o"] + ["h", "e", "l", "o"] + ["k", "o"] = 10 tokens

        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        var (tokens, prosody) = multilingual.PhonemizeWithProsody(
            "\u3053\u3093hello\u304B\u306A");  // こんhelloかな

        // JA(2) + EN(4) + JA(2) = 8 tokens
        Assert.Equal(8, tokens.Count);

        // First JA segment
        Assert.Equal("k", tokens[0]);
        Assert.Equal("o", tokens[1]);

        // EN segment
        Assert.Equal("h", tokens[2]);
        Assert.Equal("e", tokens[3]);
        Assert.Equal("l", tokens[4]);
        Assert.Equal("o", tokens[5]);

        // Second JA segment
        Assert.Equal("k", tokens[6]);
        Assert.Equal("o", tokens[7]);

        // No BOS/EOS tokens should appear
        Assert.DoesNotContain("^", tokens);
        Assert.DoesNotContain("$", tokens);

        // Prosody alignment
        Assert.Equal(tokens.Count, prosody.Count);

        // Verify the last EOS was tracked: the last JA segment has "$",
        // so PostProcessIds should emit standard EOS.
        var map = MakeMap();
        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?> { null, null };

        var (resultIds, _) = multilingual.PostProcessIds(inputIds, inputProsody, map);
        Assert.Equal(2, resultIds[^1]);  // "$" EOS from last JA segment
    }

    // ================================================================
    // 12. Phonemize_ReturnsTokensOnly
    // ================================================================

    /// <summary>
    /// The non-prosody <see cref="MultilingualPhonemizer.Phonemize"/> method
    /// should return only the token list (same tokens as PhonemizeWithProsody
    /// but without the prosody tuple).
    /// </summary>
    [Fact]
    public void Phonemize_ReturnsTokensOnly()
    {
        var multilingual = MakeMultilingual(MakeJaStub(), MakeEnStub());

        // Call the non-prosody Phonemize() method
        var tokens = multilingual.Phonemize("\u3053\u3093hello");

        // Should match PhonemizeWithProsody result
        var multilingual2 = MakeMultilingual(MakeJaStub(), MakeEnStub());
        var (expectedTokens, _) = multilingual2.PhonemizeWithProsody("\u3053\u3093hello");

        Assert.Equal(expectedTokens, tokens);

        // BOS/EOS stripped
        Assert.DoesNotContain("^", tokens);
        Assert.DoesNotContain("$", tokens);

        // JA(2) + EN(4) = 6 tokens
        Assert.Equal(6, tokens.Count);
    }
}
