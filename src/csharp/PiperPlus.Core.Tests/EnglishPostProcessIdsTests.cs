using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Detailed unit tests for <see cref="EnglishPhonemizer.PostProcessIds"/>.
/// <para>
/// Verifies the inter-phoneme PAD insertion and BOS/EOS wrapping logic
/// that mirrors the Python <c>EnglishPhonemizer.post_process_ids()</c> in
/// <c>piper_train/phonemize/english.py</c>.
/// </para>
/// </summary>
public sealed class EnglishPostProcessIdsTests
{
    // ================================================================
    // Stub G2P engine (returns empty — tests only exercise PostProcessIds)
    // ================================================================

    /// <summary>
    /// Minimal <see cref="IEnglishG2PEngine"/> stub that returns an empty
    /// word list. Tests in this class only call <see cref="EnglishPhonemizer.PostProcessIds"/>
    /// directly, so phonemization output is irrelevant.
    /// </summary>
    private sealed class StubEnglishG2PEngine : IEnglishG2PEngine
    {
        public List<List<string>> ConvertToArpabet(string text) => [];
    }

    // ================================================================
    // Shared helpers
    // ================================================================

    /// <summary>
    /// Standard phoneme-ID map used by most tests.
    /// </summary>
    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],    // PAD
        ["^"] = [1],    // BOS
        ["$"] = [2],    // EOS
        ["h"] = [10],
        ["\u0259"] = [11],  // ə
        ["l"] = [12],
    };

    /// <summary>
    /// Create an <see cref="EnglishPhonemizer"/> backed by the stub engine.
    /// </summary>
    private static EnglishPhonemizer MakePhonemizer() => new(new StubEnglishG2PEngine());

    // ================================================================
    // 1. BasicSequence
    // ================================================================

    /// <summary>
    /// Three input IDs produce: BOS(1) + PAD(0) + 10 + PAD(0) + 11 + PAD(0) + 12 + PAD(0) + EOS(2).
    /// </summary>
    [Fact]
    public void BasicSequence_PadAndBosEosInserted()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 3),
            new ProsodyInfo(0, 2, 3),
            new ProsodyInfo(0, 0, 3),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1), PAD(0), 10, PAD(0), 11, PAD(0), 12, PAD(0), EOS(2)
        Assert.Equal([1, 0, 10, 0, 11, 0, 12, 0, 2], ids);
    }

    // ================================================================
    // 2. SinglePhoneme
    // ================================================================

    /// <summary>
    /// A single phoneme ID: BOS(1) + PAD(0) + 10 + PAD(0) + EOS(2).
    /// </summary>
    [Fact]
    public void SinglePhoneme_PadAndBosEosInserted()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { new ProsodyInfo(0, 2, 1) };

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        Assert.Equal([1, 0, 10, 0, 2], ids);
    }

    // ================================================================
    // 3. EmptyInput
    // ================================================================

    /// <summary>
    /// Empty input produces BOS(1) + PAD(0) + EOS(2) only.
    /// </summary>
    [Fact]
    public void EmptyInput_BosAndEosOnly()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1) + PAD(0) + EOS(2)
        Assert.Equal([1, 0, 2], ids);

        // All prosody entries should be null (BOS, PAD, EOS are structural).
        Assert.Equal(3, prosody.Count);
        Assert.All(prosody, p => Assert.Null(p));
    }

    // ================================================================
    // 4. ProsodyAlignment
    // ================================================================

    /// <summary>
    /// Input prosody [p1, p2, p3] should align as:
    /// [null, null, p1, null, p2, null, p3, null, null]
    /// where null positions correspond to BOS, PADs, and EOS.
    /// </summary>
    [Fact]
    public void ProsodyAlignment_PadPositionsAreNull()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var p1 = new ProsodyInfo(0, 2, 3);
        var p2 = new ProsodyInfo(0, 0, 3);
        var p3 = new ProsodyInfo(0, 0, 3);

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?> { p1, p2, p3 };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Expected: [null, null, p1, null, p2, null, p3, null, null]
        //            BOS   PAD  10   PAD  11   PAD  12   PAD  EOS
        Assert.Equal(9, prosody.Count);

        Assert.Null(prosody[0]);   // BOS
        Assert.Null(prosody[1]);   // PAD after BOS
        Assert.Equal(p1, prosody[2]); // phoneme 10
        Assert.Null(prosody[3]);   // PAD after 10
        Assert.Equal(p2, prosody[4]); // phoneme 11
        Assert.Null(prosody[5]);   // PAD after 11
        Assert.Equal(p3, prosody[6]); // phoneme 12
        Assert.Null(prosody[7]);   // PAD after 12
        Assert.Null(prosody[8]);   // EOS
    }

    // ================================================================
    // 5. NoBOS
    // ================================================================

    /// <summary>
    /// When "^" is absent from the phoneme-ID map, BOS is skipped.
    /// Result: 10 + PAD(0) + EOS(2).
    /// </summary>
    [Fact]
    public void NoBOS_BosSkipped()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map.Remove("^");

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { new ProsodyInfo(0, 2, 1) };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // No BOS prefix: just padded IDs + EOS.
        Assert.Equal([10, 0, 2], ids);

        // Prosody: [p1, null(PAD), null(EOS)]
        Assert.Equal(3, prosody.Count);
        Assert.NotNull(prosody[0]);  // phoneme 10
        Assert.Null(prosody[1]);     // PAD
        Assert.Null(prosody[2]);     // EOS
    }

    // ================================================================
    // 6. NoEOS
    // ================================================================

    /// <summary>
    /// When "$" is absent from the phoneme-ID map, EOS is skipped.
    /// Result: BOS(1) + PAD(0) + 10 + PAD(0).
    /// </summary>
    [Fact]
    public void NoEOS_EosSkipped()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map.Remove("$");

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { new ProsodyInfo(0, 2, 1) };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS + PAD + 10 + PAD, no EOS.
        Assert.Equal([1, 0, 10, 0], ids);

        // Prosody: [null(BOS), null(PAD), p1, null(PAD)]
        Assert.Equal(4, prosody.Count);
        Assert.Null(prosody[0]);     // BOS
        Assert.Null(prosody[1]);     // PAD after BOS
        Assert.NotNull(prosody[2]);  // phoneme 10
        Assert.Null(prosody[3]);     // PAD after 10
    }

    // ================================================================
    // 7. MultiIdPad
    // ================================================================

    /// <summary>
    /// When PAD maps to multiple IDs (e.g. [0, 99]), each phoneme
    /// is followed by all PAD IDs, and BOS is followed by only the
    /// first PAD ID (pad_ids[0]).
    /// </summary>
    [Fact]
    public void MultiIdPad_AllPadIdsInserted()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map["_"] = [0, 99]; // Multi-ID PAD

        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 2),
            new ProsodyInfo(0, 0, 2),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1) + pad[0]=0 + 10 + 0 + 99 + 11 + 0 + 99 + EOS(2)
        Assert.Equal([1, 0, 10, 0, 99, 11, 0, 99, 2], ids);

        // Prosody count must match IDs count.
        Assert.Equal(ids.Count, prosody.Count);

        // Multi-ID PAD positions are all null.
        Assert.Null(prosody[3]); // first PAD id after phoneme 10
        Assert.Null(prosody[4]); // second PAD id after phoneme 10
        Assert.Null(prosody[6]); // first PAD id after phoneme 11
        Assert.Null(prosody[7]); // second PAD id after phoneme 11
    }

    // ================================================================
    // 8. ProsodyLengthMatchesIds
    // ================================================================

    /// <summary>
    /// After PostProcessIds, Ids.Count must always equal Prosody.Count.
    /// This invariant is tested with various input sizes.
    /// </summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(5)]
    [InlineData(20)]
    public void ProsodyLengthMatchesIds(int inputLength)
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int>();
        var inputProsody = new List<ProsodyInfo?>();
        for (int i = 0; i < inputLength; i++)
        {
            inputIds.Add(10);
            inputProsody.Add(new ProsodyInfo(0, 0, inputLength));
        }

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 9. NoBosNoEos — neither BOS nor EOS in map
    // ================================================================

    /// <summary>
    /// When both "^" and "$" are absent, output is only the padded phoneme
    /// IDs with no BOS/EOS wrapping.
    /// </summary>
    [Fact]
    public void NoBosNoEos_OnlyPaddingApplied()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map.Remove("^");
        map.Remove("$");

        var inputIds = new List<int> { 10, 11 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 2),
            new ProsodyInfo(0, 0, 2),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Just padded: 10 + PAD(0) + 11 + PAD(0)
        Assert.Equal([10, 0, 11, 0], ids);
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 10. NoPadInMap — "_" absent, defaults to [0]
    // ================================================================

    /// <summary>
    /// When "_" is not in the map, PAD defaults to [0].
    /// This mirrors the Python fallback: <c>pad_ids = phoneme_id_map.get("_", [0])</c>.
    /// </summary>
    [Fact]
    public void NoPadInMap_DefaultsToZero()
    {
        var phonemizer = MakePhonemizer();
        var map = new Dictionary<string, int[]>
        {
            ["^"] = [1],
            ["$"] = [2],
            ["h"] = [10],
        };
        // "_" is absent — should default to PAD=[0].

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { null };

        var (ids, _) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1) + PAD(0) + 10 + PAD(0) + EOS(2)
        Assert.Equal([1, 0, 10, 0, 2], ids);
    }

    // ================================================================
    // 11. AllProsodyNull — structural-only input
    // ================================================================

    /// <summary>
    /// When all input prosody entries are null (e.g. punctuation-only
    /// input), the output prosody must also be all null and the ID
    /// transformation must still be correct.
    /// </summary>
    [Fact]
    public void AllProsodyNull_StillCorrect()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int> { 10, 12 };
        var inputProsody = new List<ProsodyInfo?> { null, null };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        Assert.Equal([1, 0, 10, 0, 12, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);
        Assert.All(prosody, p => Assert.Null(p));
    }

    // ================================================================
    // 12. PostProcessIds_SkipsPadAfterPadToken
    // ================================================================

    /// <summary>
    /// When input contains a PAD token (0), no additional PAD should be
    /// inserted after it. Mirrors the Python conditional:
    /// <c>if phoneme_id not in pad_ids → skip PAD insertion</c>.
    /// </summary>
    [Fact]
    public void PostProcessIds_SkipsPadAfterPadToken()
    {
        var phonemizer = MakePhonemizer();
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
        };

        var phonemeIds = new List<int> { 10, 0, 11 };
        var prosody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 1, 3),
            null,
            new ProsodyInfo(0, 2, 3),
        };

        var (ids, pros) = phonemizer.PostProcessIds(phonemeIds, prosody, map);

        // Expected: [BOS=1, PAD=0, 10, PAD=0, 0(no extra PAD), 11, PAD=0, EOS=2]
        Assert.Equal([1, 0, 10, 0, 0, 11, 0, 2], ids);
        Assert.Equal(ids.Count, pros.Count);
    }

    // ================================================================
    // 13. PostProcessIds_AllPadTokens_NoPadInserted
    // ================================================================

    /// <summary>
    /// When all input IDs are PAD tokens, no inter-phoneme PAD is inserted
    /// after any of them. The output is just BOS + PAD + 0 + 0 + EOS.
    /// </summary>
    [Fact]
    public void PostProcessIds_AllPadTokens_NoPadInserted()
    {
        var phonemizer = MakePhonemizer();
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
        };

        var phonemeIds = new List<int> { 0, 0 };
        var prosody = new List<ProsodyInfo?> { null, null };

        var (ids, pros) = phonemizer.PostProcessIds(phonemeIds, prosody, map);

        // Expected: [BOS=1, PAD=0, 0, 0, EOS=2] (no extra PADs after the 0s)
        Assert.Equal([1, 0, 0, 0, 2], ids);
        Assert.Equal(ids.Count, pros.Count);
    }

    // ================================================================
    // 14. Integration — PostProcessIds via PhonemeEncoder
    // ================================================================

    /// <summary>
    /// Verifies that <see cref="PhonemeEncoder.Encode"/> calls
    /// <see cref="EnglishPhonemizer.PostProcessIds"/> and the final
    /// output reflects BOS/EOS + inter-phoneme padding.
    /// </summary>
    [Fact]
    public void Integration_EncodeCallsPostProcessIds()
    {
        // Build a G2P engine that returns a single word "hel" → ["HH", "EH1", "L"]
        var stubEngine = new SingleWordG2PEngine([["HH", "EH1", "L"]]);
        var phonemizer = new EnglishPhonemizer(stubEngine);

        // The phonemizer will produce IPA tokens: "h", "ˈ", "ɛ", "l"
        // (stress marker ˈ inserted before EH1's IPA).
        // We need a map that covers all these tokens.
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
            ["h"] = [10],
            ["\u02c8"] = [20],   // ˈ (primary stress marker)
            ["\u025b"] = [30],   // ɛ (EH with stress)
            ["l"] = [12],
        };

        var (ids, prosody) = PhonemeEncoder.Encode(phonemizer, "dummy", map);

        // First and last IDs must be BOS and EOS.
        Assert.Equal(1, ids[0]);       // BOS
        Assert.Equal(2, ids[^1]);      // EOS

        // Second ID must be PAD (after BOS).
        Assert.Equal(0, ids[1]);

        // Ids and Prosody must be the same length.
        Assert.Equal(ids.Count, prosody.Count);
    }

    // ================================================================
    // 15. PostProcessIds_NoBosInMap — multi-phoneme, no BOS
    // ================================================================

    /// <summary>
    /// When "^" is absent from the map and multiple phonemes are given,
    /// output has no BOS prefix: [PAD, id1, PAD, id2, PAD, EOS].
    /// Verifies the pattern with more than one phoneme (complements
    /// <see cref="NoBOS_BosSkipped"/> which tests a single phoneme).
    /// </summary>
    [Fact]
    public void PostProcessIds_NoBosInMap()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map.Remove("^");

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 3),
            new ProsodyInfo(0, 1, 3),
            new ProsodyInfo(0, 0, 3),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // No BOS: 10 + PAD(0) + 11 + PAD(0) + 12 + PAD(0) + EOS(2)
        Assert.Equal([10, 0, 11, 0, 12, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);

        // First element is phoneme, not BOS null.
        Assert.NotNull(prosody[0]);
        // EOS at the end is null.
        Assert.Null(prosody[^1]);
    }

    // ================================================================
    // 16. PostProcessIds_NoEosInMap — multi-phoneme, no EOS
    // ================================================================

    /// <summary>
    /// When "$" is absent from the map and multiple phonemes are given,
    /// output has no EOS suffix: [BOS, PAD, id1, PAD, id2, PAD, id3, PAD].
    /// Verifies the pattern with more than one phoneme (complements
    /// <see cref="NoEOS_EosSkipped"/> which tests a single phoneme).
    /// </summary>
    [Fact]
    public void PostProcessIds_NoEosInMap()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();
        map.Remove("$");

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 3),
            new ProsodyInfo(0, 1, 3),
            new ProsodyInfo(0, 0, 3),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1) + PAD(0) + 10 + PAD(0) + 11 + PAD(0) + 12 + PAD(0), no EOS.
        Assert.Equal([1, 0, 10, 0, 11, 0, 12, 0], ids);
        Assert.Equal(ids.Count, prosody.Count);

        // BOS and its PAD are null.
        Assert.Null(prosody[0]);
        Assert.Null(prosody[1]);
        // Last element is a trailing PAD (null), not EOS.
        Assert.Null(prosody[^1]);
        // Phoneme at index 6 is the last real phoneme.
        Assert.NotNull(prosody[6]);
    }

    // ================================================================
    // 17. PostProcessIds_NoPadInMap — multi-phoneme, default PAD
    // ================================================================

    /// <summary>
    /// When "_" is absent from the map with multiple phonemes,
    /// PAD defaults to [0]. Extends <see cref="NoPadInMap_DefaultsToZero"/>
    /// (single phoneme) to confirm the default PAD is inserted between
    /// every phoneme pair.
    /// </summary>
    [Fact]
    public void PostProcessIds_NoPadInMap()
    {
        var phonemizer = MakePhonemizer();
        var map = new Dictionary<string, int[]>
        {
            ["^"] = [1],
            ["$"] = [2],
            ["h"] = [10],
            ["\u0259"] = [11],  // ə
            ["l"] = [12],
        };
        // "_" is absent — PAD should fall back to [0].

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?>
        {
            new ProsodyInfo(0, 2, 3),
            new ProsodyInfo(0, 1, 3),
            new ProsodyInfo(0, 0, 3),
        };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // BOS(1) + PAD(0) + 10 + PAD(0) + 11 + PAD(0) + 12 + PAD(0) + EOS(2)
        Assert.Equal([1, 0, 10, 0, 11, 0, 12, 0, 2], ids);
        Assert.Equal(ids.Count, prosody.Count);

        // All PAD positions (indices 1, 3, 5, 7) use fallback value 0.
        Assert.Equal(0, ids[1]);
        Assert.Equal(0, ids[3]);
        Assert.Equal(0, ids[5]);
        Assert.Equal(0, ids[7]);
    }

    // ================================================================
    // 18. PostProcessIds_SinglePhoneme — detailed assertions
    // ================================================================

    /// <summary>
    /// A single phoneme [10] produces exactly [BOS(1), PAD(0), 10, PAD(0), EOS(2)].
    /// Extends <see cref="SinglePhoneme_PadAndBosEosInserted"/> with explicit
    /// per-index checks for both IDs and prosody.
    /// </summary>
    [Fact]
    public void PostProcessIds_SinglePhoneme()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var inputIds = new List<int> { 10 };
        var inputProsody = new List<ProsodyInfo?> { new ProsodyInfo(0, 2, 1) };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Exact output: [BOS, PAD, 10, PAD, EOS]
        Assert.Equal(5, ids.Count);
        Assert.Equal(1, ids[0]);   // BOS
        Assert.Equal(0, ids[1]);   // PAD
        Assert.Equal(10, ids[2]);  // phoneme
        Assert.Equal(0, ids[3]);   // PAD
        Assert.Equal(2, ids[4]);   // EOS

        // Prosody: only index 2 carries the original prosody.
        Assert.Equal(5, prosody.Count);
        Assert.Null(prosody[0]);   // BOS
        Assert.Null(prosody[1]);   // PAD
        Assert.NotNull(prosody[2]);
        Assert.Equal(new ProsodyInfo(0, 2, 1), prosody[2]);
        Assert.Null(prosody[3]);   // PAD
        Assert.Null(prosody[4]);   // EOS
    }

    // ================================================================
    // 19. PostProcessIds_ProsodyPreservedThroughPadding
    // ================================================================

    /// <summary>
    /// Verifies that distinct prosody values survive padding and appear
    /// at the correct indices in the output. Each phoneme carries a
    /// unique <see cref="ProsodyInfo"/> so we can confirm positional
    /// integrity after BOS/PAD insertion.
    /// </summary>
    [Fact]
    public void PostProcessIds_ProsodyPreservedThroughPadding()
    {
        var phonemizer = MakePhonemizer();
        var map = MakeMap();

        var p1 = new ProsodyInfo(A1: -1, A2: 2, A3: 5);
        var p2 = new ProsodyInfo(A1: 0, A2: 1, A3: 5);
        var p3 = new ProsodyInfo(A1: 1, A2: 0, A3: 5);

        var inputIds = new List<int> { 10, 11, 12 };
        var inputProsody = new List<ProsodyInfo?> { p1, p2, p3 };

        var (ids, prosody) = phonemizer.PostProcessIds(inputIds, inputProsody, map);

        // Output layout:
        // idx: 0     1     2    3     4    5     6    7     8
        //      BOS   PAD   10   PAD   11   PAD   12   PAD   EOS
        Assert.Equal(9, ids.Count);
        Assert.Equal(9, prosody.Count);

        // Phoneme positions carry the exact original prosody values.
        Assert.Equal(p1, prosody[2]);  // phoneme 10 -> p1
        Assert.Equal(-1, prosody[2]!.Value.A1);
        Assert.Equal(2, prosody[2]!.Value.A2);
        Assert.Equal(5, prosody[2]!.Value.A3);

        Assert.Equal(p2, prosody[4]);  // phoneme 11 -> p2
        Assert.Equal(0, prosody[4]!.Value.A1);
        Assert.Equal(1, prosody[4]!.Value.A2);
        Assert.Equal(5, prosody[4]!.Value.A3);

        Assert.Equal(p3, prosody[6]);  // phoneme 12 -> p3
        Assert.Equal(1, prosody[6]!.Value.A1);
        Assert.Equal(0, prosody[6]!.Value.A2);
        Assert.Equal(5, prosody[6]!.Value.A3);

        // All structural positions (BOS, PADs, EOS) must be null.
        Assert.Null(prosody[0]);  // BOS
        Assert.Null(prosody[1]);  // PAD after BOS
        Assert.Null(prosody[3]);  // PAD after phoneme 10
        Assert.Null(prosody[5]);  // PAD after phoneme 11
        Assert.Null(prosody[7]);  // PAD after phoneme 12
        Assert.Null(prosody[8]);  // EOS
    }

    // ================================================================
    // Helper: stub G2P engine that returns pre-configured ARPAbet words
    // ================================================================

    /// <summary>
    /// G2P engine stub that returns a fixed list of ARPAbet words
    /// regardless of input text. Used for integration-level tests.
    /// </summary>
    private sealed class SingleWordG2PEngine : IEnglishG2PEngine
    {
        private readonly List<List<string>> _words;

        public SingleWordG2PEngine(IEnumerable<IEnumerable<string>> words)
        {
            _words = new List<List<string>>();
            foreach (var w in words)
            {
                _words.Add(new List<string>(w));
            }
        }

        public List<List<string>> ConvertToArpabet(string text) => _words;
    }
}
