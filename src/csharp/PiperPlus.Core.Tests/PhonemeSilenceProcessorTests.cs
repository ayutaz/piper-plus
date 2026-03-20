using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PhonemeSilenceProcessor"/>.
/// Covers specification parsing, phoneme-ID sequence splitting, prosody
/// alignment, silence sample calculation, and edge cases.
/// </summary>
public sealed class PhonemeSilenceProcessorTests
{
    // ================================================================
    // Shared helpers
    // ================================================================

    /// <summary>
    /// Minimal phoneme_id_map used by split tests.
    /// Mirrors a typical config.json mapping.
    /// </summary>
    private static Dictionary<string, int[]> MakeIdMap() => new()
    {
        ["_"] = [0],
        ["^"] = [1],
        ["$"] = [2],
        ["a"] = [10],
        ["i"] = [11],
        ["k"] = [12],
        ["#"] = [20],
    };

    // ================================================================
    // Parse — valid specifications
    // ================================================================

    // ----------------------------------------------------------------
    // 1. Single phoneme specification
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_SingleEntry_ReturnsSingleMapping()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.5");

        Assert.Single(result);
        Assert.Equal(0.5f, result["_"]);
    }

    // ----------------------------------------------------------------
    // 2. Multiple comma-separated entries
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_MultipleEntries_ReturnsAllMappings()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.5,# 0.3");

        Assert.Equal(2, result.Count);
        Assert.Equal(0.5f, result["_"]);
        Assert.Equal(0.3f, result["#"]);
    }

    // ----------------------------------------------------------------
    // 3. Whitespace around entries is trimmed
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_WhitespaceAroundEntries_Trimmed()
    {
        var result = PhonemeSilenceProcessor.Parse("  _ 0.5 , # 0.3  ");

        Assert.Equal(2, result.Count);
        Assert.Equal(0.5f, result["_"]);
        Assert.Equal(0.3f, result["#"]);
    }

    // ----------------------------------------------------------------
    // 4. Decimal precision preserved
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_DecimalPrecision_Preserved()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.125");

        Assert.Equal(0.125f, result["_"]);
    }

    // ----------------------------------------------------------------
    // 5. Integer seconds value accepted
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_IntegerSeconds_Accepted()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 1");

        Assert.Equal(1.0f, result["_"]);
    }

    // ----------------------------------------------------------------
    // 6. Duplicate phoneme — last value wins
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_DuplicatePhoneme_LastValueWins()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.5,_ 0.8");

        Assert.Single(result);
        Assert.Equal(0.8f, result["_"]);
    }

    // ================================================================
    // Parse — invalid specifications
    // ================================================================

    // ----------------------------------------------------------------
    // 7. Null specification throws
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_Null_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse(null!));
    }

    // ----------------------------------------------------------------
    // 8. Empty string throws
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_EmptyString_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse(""));
    }

    // ----------------------------------------------------------------
    // 9. Whitespace-only string throws
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_WhitespaceOnly_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse("   "));
    }

    // ----------------------------------------------------------------
    // 10. Missing seconds value throws
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_MissingSeconds_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse("_"));
    }

    // ----------------------------------------------------------------
    // 11. Non-numeric seconds throws
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_NonNumericSeconds_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse("_ abc"));
    }

    // ----------------------------------------------------------------
    // 12. Entry with only a space throws (empty phoneme)
    // ----------------------------------------------------------------

    [Fact]
    public void Parse_SpaceOnlyEntry_ThrowsArgumentException()
    {
        // After comma-split and trim, an entry like " 0.5" would have
        // lastSpace at 0, triggering the <= 0 check.
        Assert.Throws<ArgumentException>(
            () => PhonemeSilenceProcessor.Parse(", 0.5"));
    }

    // ================================================================
    // SplitAtPhonemeSilence — basic splitting
    // ================================================================

    // ----------------------------------------------------------------
    // 13. No silence phonemes — single phrase, zero silence
    // ----------------------------------------------------------------

    [Fact]
    public void Split_NoSilencePhonemes_SinglePhrase()
    {
        long[] ids = [1, 10, 11, 2]; // ^ a i $
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Single(phrases);
        Assert.Equal([1L, 10L, 11L, 2L], phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
        Assert.Null(phrases[0].ProsodyFlat);
    }

    // ----------------------------------------------------------------
    // 14. Single silence phoneme — two phrases
    // ----------------------------------------------------------------

    [Fact]
    public void Split_OneSilenceMarker_TwoPhrases()
    {
        // Sequence: ^ a _ i $
        // "_" maps to ID 0, and has 0.5s silence.
        long[] ids = [1, 10, 0, 11, 2];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);

        // First phrase: [^, a, _], silence = 0.5 * 22050 = 11025.
        Assert.Equal([1L, 10L, 0L], phrases[0].PhonemeIds);
        Assert.Equal(11025, phrases[0].SilenceSamples);

        // Second phrase: [i, $], silence = 0.
        Assert.Equal([11L, 2L], phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 15. Multiple silence markers — three phrases
    // ----------------------------------------------------------------

    [Fact]
    public void Split_MultipleSilenceMarkers_MultiplePhrases()
    {
        // Sequence: ^ a _ i # k $
        // "_" (ID 0) -> 0.5s, "#" (ID 20) -> 0.3s
        long[] ids = [1, 10, 0, 11, 20, 12, 2];
        var silence = new Dictionary<string, float>
        {
            ["_"] = 0.5f,
            ["#"] = 0.3f,
        };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(3, phrases.Count);

        // Phrase 0: [^, a, _]
        Assert.Equal([1L, 10L, 0L], phrases[0].PhonemeIds);
        Assert.Equal((int)(0.5f * 22050), phrases[0].SilenceSamples);

        // Phrase 1: [i, #]
        Assert.Equal([11L, 20L], phrases[1].PhonemeIds);
        Assert.Equal((int)(0.3f * 22050), phrases[1].SilenceSamples);

        // Phrase 2: [k, $]
        Assert.Equal([12L, 2L], phrases[2].PhonemeIds);
        Assert.Equal(0, phrases[2].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 16. Silence at the very end — trailing empty phrase
    // ----------------------------------------------------------------

    [Fact]
    public void Split_SilenceAtEnd_TrailingEmptyPhrase()
    {
        // Sequence: ^ a _
        // The silence phoneme is the last ID, so the trailing phrase is empty.
        long[] ids = [1, 10, 0];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);

        Assert.Equal([1L, 10L, 0L], phrases[0].PhonemeIds);
        Assert.Equal(11025, phrases[0].SilenceSamples);

        // Trailing phrase is empty with 0 silence.
        Assert.Empty(phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 17. Empty input — single empty phrase
    // ----------------------------------------------------------------

    [Fact]
    public void Split_EmptyInput_SingleEmptyPhrase()
    {
        long[] ids = [];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Single(phrases);
        Assert.Empty(phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 18. Single phoneme (non-silence) — single phrase
    // ----------------------------------------------------------------

    [Fact]
    public void Split_SinglePhonemeNonSilence_SinglePhrase()
    {
        long[] ids = [10]; // just "a"
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Single(phrases);
        Assert.Equal([10L], phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 19. Single phoneme that IS a silence marker
    // ----------------------------------------------------------------

    [Fact]
    public void Split_SinglePhonemeSilence_TwoPhrasesOneEmpty()
    {
        long[] ids = [0]; // just "_"
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);
        Assert.Equal([0L], phrases[0].PhonemeIds);
        Assert.Equal(11025, phrases[0].SilenceSamples);
        Assert.Empty(phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 20. All phonemes are silence markers
    // ----------------------------------------------------------------

    [Fact]
    public void Split_AllSilencePhonemes_EachSplits()
    {
        long[] ids = [0, 0, 0]; // three "_" in a row
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        // Each "_" closes a phrase, plus a trailing empty phrase.
        Assert.Equal(4, phrases.Count);
        for (int i = 0; i < 3; i++)
        {
            Assert.Equal([0L], phrases[i].PhonemeIds);
            Assert.Equal(11025, phrases[i].SilenceSamples);
        }
        Assert.Empty(phrases[3].PhonemeIds);
        Assert.Equal(0, phrases[3].SilenceSamples);
    }

    // ================================================================
    // SplitAtPhonemeSilence — prosody alignment
    // ================================================================

    // ----------------------------------------------------------------
    // 21. Prosody flat array is split in sync with phoneme IDs
    // ----------------------------------------------------------------

    [Fact]
    public void Split_WithProsody_SlicedCorrectly()
    {
        // Sequence: a _ i (IDs: 10, 0, 11)
        long[] ids = [10, 0, 11];
        // Prosody: 3 values per phoneme -> 9 total
        long[] prosody = [1, 2, 3, 4, 5, 6, 7, 8, 9];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosody, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);

        // Phrase 0: phonemes [a, _], prosody for indices 0 and 1.
        Assert.Equal([10L, 0L], phrases[0].PhonemeIds);
        Assert.NotNull(phrases[0].ProsodyFlat);
        Assert.Equal([1L, 2L, 3L, 4L, 5L, 6L], phrases[0].ProsodyFlat);

        // Phrase 1: phoneme [i], prosody for index 2.
        Assert.Equal([11L], phrases[1].PhonemeIds);
        Assert.NotNull(phrases[1].ProsodyFlat);
        Assert.Equal([7L, 8L, 9L], phrases[1].ProsodyFlat);
    }

    // ----------------------------------------------------------------
    // 22. Null prosody — all phrases have null ProsodyFlat
    // ----------------------------------------------------------------

    [Fact]
    public void Split_NullProsody_AllPhrasesHaveNullProsody()
    {
        long[] ids = [10, 0, 11];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        foreach (var phrase in phrases)
        {
            Assert.Null(phrase.ProsodyFlat);
        }
    }

    // ----------------------------------------------------------------
    // 23. Wrong-length prosody treated as no prosody
    // ----------------------------------------------------------------

    [Fact]
    public void Split_WrongLengthProsody_TreatedAsNoProsody()
    {
        long[] ids = [10, 0, 11];
        // Wrong length: should be 3*3=9 but is 5.
        long[] prosody = [1, 2, 3, 4, 5];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosody, silence, map, sampleRate: 22050);

        // Prosody length mismatch -> treated as no prosody.
        foreach (var phrase in phrases)
        {
            Assert.Null(phrase.ProsodyFlat);
        }
    }

    // ----------------------------------------------------------------
    // 24. Prosody on trailing empty phrase is empty (not null)
    // ----------------------------------------------------------------

    [Fact]
    public void Split_ProsodyOnTrailingEmptyPhrase_IsEmptyList()
    {
        // Sequence ends with silence phoneme: a _
        long[] ids = [10, 0];
        long[] prosody = [1, 2, 3, 4, 5, 6];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosody, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);

        // Trailing phrase has prosody enabled but empty.
        Assert.NotNull(phrases[1].ProsodyFlat);
        Assert.Empty(phrases[1].ProsodyFlat!);
    }

    // ================================================================
    // SplitAtPhonemeSilence — silence sample calculation
    // ================================================================

    // ----------------------------------------------------------------
    // 25. Sample rate affects silence samples
    // ----------------------------------------------------------------

    [Theory]
    [InlineData(22050, 0.5f, 11025)]
    [InlineData(44100, 0.5f, 22050)]
    [InlineData(16000, 1.0f, 16000)]
    [InlineData(22050, 0.0f, 0)]
    public void Split_SilenceSamples_MatchesSampleRate(
        int sampleRate, float seconds, int expectedSamples)
    {
        long[] ids = [10, 0]; // a _
        var silence = new Dictionary<string, float> { ["_"] = seconds };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: sampleRate);

        Assert.Equal(expectedSamples, phrases[0].SilenceSamples);
    }

    // ================================================================
    // SplitAtPhonemeSilence — phoneme ID map interaction
    // ================================================================

    // ----------------------------------------------------------------
    // 26. Silence phoneme not in ID map — ignored silently
    // ----------------------------------------------------------------

    [Fact]
    public void Split_SilencePhonemeNotInIdMap_NoSplit()
    {
        long[] ids = [1, 10, 11, 2];
        // "z" is in the silence spec but not in the phoneme_id_map.
        var silence = new Dictionary<string, float> { ["z"] = 0.5f };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        // No split — "z" is not in the map so it cannot match any ID.
        Assert.Single(phrases);
        Assert.Equal([1L, 10L, 11L, 2L], phrases[0].PhonemeIds);
    }

    // ----------------------------------------------------------------
    // 27. Multi-ID phoneme — split triggers on last ID only
    // ----------------------------------------------------------------

    [Fact]
    public void Split_MultiIdPhoneme_SplitsOnLastId()
    {
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["a"] = [10],
            ["x"] = [50, 51], // multi-ID phoneme
        };

        // "x" maps to [50, 51], silence triggers on 51 (last ID).
        var silence = new Dictionary<string, float> { ["x"] = 0.5f };
        // Sequence: a x[0] x[1] a  (IDs: 10, 50, 51, 10)
        long[] ids = [10, 50, 51, 10];

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(2, phrases.Count);

        // Split occurs after ID 51.
        Assert.Equal([10L, 50L, 51L], phrases[0].PhonemeIds);
        Assert.Equal(11025, phrases[0].SilenceSamples);

        Assert.Equal([10L], phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    // ----------------------------------------------------------------
    // 28. Empty phoneme ID map — no splits possible
    // ----------------------------------------------------------------

    [Fact]
    public void Split_EmptyPhonemeIdMap_NoSplits()
    {
        long[] ids = [1, 10, 0, 11, 2];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = new Dictionary<string, int[]>();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        // No phoneme can be resolved, so no splits.
        Assert.Single(phrases);
        Assert.Equal([1L, 10L, 0L, 11L, 2L], phrases[0].PhonemeIds);
    }

    // ================================================================
    // SplitAtPhonemeSilence — argument validation
    // ================================================================

    // ----------------------------------------------------------------
    // 29. Null phonemeIds throws
    // ----------------------------------------------------------------

    [Fact]
    public void Split_NullPhonemeIds_ThrowsArgumentNullException()
    {
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };
        var map = MakeIdMap();

        Assert.Throws<ArgumentNullException>(
            () => PhonemeSilenceProcessor.SplitAtPhonemeSilence(
                null!, null, silence, map, 22050));
    }

    // ----------------------------------------------------------------
    // 30. Null phonemeSilence throws
    // ----------------------------------------------------------------

    [Fact]
    public void Split_NullPhonemeSilence_ThrowsArgumentNullException()
    {
        long[] ids = [1, 10, 2];
        var map = MakeIdMap();

        Assert.Throws<ArgumentNullException>(
            () => PhonemeSilenceProcessor.SplitAtPhonemeSilence(
                ids, null, null!, map, 22050));
    }

    // ----------------------------------------------------------------
    // 31. Null phonemeIdMap throws
    // ----------------------------------------------------------------

    [Fact]
    public void Split_NullPhonemeIdMap_ThrowsArgumentNullException()
    {
        long[] ids = [1, 10, 2];
        var silence = new Dictionary<string, float> { ["_"] = 0.5f };

        Assert.Throws<ArgumentNullException>(
            () => PhonemeSilenceProcessor.SplitAtPhonemeSilence(
                ids, null, silence, null!, 22050));
    }

    // ================================================================
    // SplitAtPhonemeSilence — empty silence map (no splits at all)
    // ================================================================

    // ----------------------------------------------------------------
    // 32. Empty silence map — whole sequence in one phrase
    // ----------------------------------------------------------------

    [Fact]
    public void Split_EmptySilenceMap_SinglePhrase()
    {
        long[] ids = [1, 10, 0, 11, 2];
        var silence = new Dictionary<string, float>();
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Single(phrases);
        Assert.Equal([1L, 10L, 0L, 11L, 2L], phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
    }

    // ================================================================
    // Phrase record struct validation
    // ================================================================

    // ----------------------------------------------------------------
    // 33. Phrase record equality
    // ----------------------------------------------------------------

    [Fact]
    public void Phrase_RecordEquality_Works()
    {
        var a = new PhonemeSilenceProcessor.Phrase(
            new List<long> { 1, 2, 3 }, null, 100);
        var b = new PhonemeSilenceProcessor.Phrase(
            new List<long> { 1, 2, 3 }, null, 100);

        // Record struct equality compares by value for value types
        // and by reference for reference types (List<long>), so a != b.
        Assert.NotEqual(a, b);

        // But same reference should be equal.
        var list = new List<long> { 1, 2, 3 };
        var c = new PhonemeSilenceProcessor.Phrase(list, null, 100);
        var d = new PhonemeSilenceProcessor.Phrase(list, null, 100);
        Assert.Equal(c, d);
    }

    // ================================================================
    // Integration: Parse + Split round-trip
    // ================================================================

    // ----------------------------------------------------------------
    // 34. Parse output feeds directly into Split
    // ----------------------------------------------------------------

    [Fact]
    public void ParseThenSplit_RoundTrip_Works()
    {
        var silence = PhonemeSilenceProcessor.Parse("_ 0.5,# 0.3");
        var map = MakeIdMap();
        // Sequence: ^ a _ i # k $
        long[] ids = [1, 10, 0, 11, 20, 12, 2];

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(3, phrases.Count);
        Assert.Equal((int)(0.5f * 22050), phrases[0].SilenceSamples);
        Assert.Equal((int)(0.3f * 22050), phrases[1].SilenceSamples);
        Assert.Equal(0, phrases[2].SilenceSamples);

        // Verify all original phoneme IDs are present across phrases.
        var allIds = phrases.SelectMany(p => p.PhonemeIds).ToList();
        Assert.Equal([1L, 10L, 0L, 11L, 20L, 12L, 2L], allIds);
    }

    // ----------------------------------------------------------------
    // 35. Consecutive silence markers of different types
    // ----------------------------------------------------------------

    [Fact]
    public void Split_ConsecutiveDifferentSilenceMarkers_EachSplits()
    {
        // Sequence: a _ # k
        long[] ids = [10, 0, 20, 12];
        var silence = new Dictionary<string, float>
        {
            ["_"] = 0.5f,
            ["#"] = 0.3f,
        };
        var map = MakeIdMap();

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            ids, prosodyFlat: null, silence, map, sampleRate: 22050);

        Assert.Equal(3, phrases.Count);

        Assert.Equal([10L, 0L], phrases[0].PhonemeIds);
        Assert.Equal((int)(0.5f * 22050), phrases[0].SilenceSamples);

        Assert.Equal([20L], phrases[1].PhonemeIds);
        Assert.Equal((int)(0.3f * 22050), phrases[1].SilenceSamples);

        Assert.Equal([12L], phrases[2].PhonemeIds);
        Assert.Equal(0, phrases[2].SilenceSamples);
    }
}
