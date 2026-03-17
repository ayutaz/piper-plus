using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PhonemeEncoder"/>.
/// Covers token-to-ID mapping, prosody propagation, unknown token handling,
/// multi-ID tokens, and the ONNX-ready <see cref="PhonemeEncoder.EncodeDirect"/> path.
/// </summary>
public class PhonemeEncoderTests
{
    // ================================================================
    // Stub IPhonemizer
    // ================================================================

    /// <summary>
    /// Minimal <see cref="IPhonemizer"/> stub that returns pre-configured tokens
    /// and prosody values, with an optional <see cref="PostProcessIds"/> override.
    /// </summary>
    private class StubPhonemizer : IPhonemizer
    {
        private readonly List<string> _tokens;
        private readonly List<ProsodyInfo?> _prosody;
        private readonly Func<List<int>, List<ProsodyInfo?>, Dictionary<string, int[]>,
            (List<int>, List<ProsodyInfo?>)>? _postProcess;

        public bool PostProcessIdsCalled { get; private set; }

        public StubPhonemizer(
            List<string> tokens,
            List<ProsodyInfo?> prosody,
            Func<List<int>, List<ProsodyInfo?>, Dictionary<string, int[]>,
                (List<int>, List<ProsodyInfo?>)>? postProcess = null)
        {
            _tokens = tokens;
            _prosody = prosody;
            _postProcess = postProcess;
        }

        public List<string> Phonemize(string text) => _tokens;

        public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
            => (_tokens, _prosody);

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

        public (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
            List<int> phonemeIds,
            List<ProsodyInfo?> prosodyFeatures,
            Dictionary<string, int[]> phonemeIdMap)
        {
            PostProcessIdsCalled = true;
            if (_postProcess is not null)
                return _postProcess(phonemeIds, prosodyFeatures, phonemeIdMap);
            return (phonemeIds, prosodyFeatures);
        }
    }

    // ================================================================
    // Shared phoneme ID map
    // ================================================================

    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],
        ["^"] = [1],
        ["$"] = [2],
        ["a"] = [10],
        ["i"] = [11],
        ["k"] = [12],
        ["\uE013"] = [30], // PUA token (e.g. "ny")
    };

    // ================================================================
    // Encode tests
    // ================================================================

    // ----------------------------------------------------------------
    // 1. BasicTokens_ConvertToIds
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_BasicTokens_ConvertToIds()
    {
        var phonemizer = new StubPhonemizer(
            ["^", "a", "i", "$"],
            [null, null, null, null]);

        var (ids, _) = PhonemeEncoder.Encode(phonemizer, "dummy", MakeMap());

        Assert.Equal([1, 10, 11, 2], ids);
    }

    // ----------------------------------------------------------------
    // 2. ProsodyInfo_MappedCorrectly
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_ProsodyInfo_MappedCorrectly()
    {
        var p0 = new ProsodyInfo(-2, 1, 5);
        var p1 = new ProsodyInfo(0, 3, 5);

        var phonemizer = new StubPhonemizer(
            ["a", "k"],
            [p0, p1]);

        var (ids, prosody) = PhonemeEncoder.Encode(phonemizer, "dummy", MakeMap());

        Assert.Equal([10, 12], ids);
        Assert.Equal(2, prosody.Count);
        Assert.Equal(p0, prosody[0]);
        Assert.Equal(p1, prosody[1]);
    }

    // ----------------------------------------------------------------
    // 3. UnknownToken_Skipped
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_UnknownToken_Skipped()
    {
        // "z" is not in the map — it should be silently skipped.
        var phonemizer = new StubPhonemizer(
            ["a", "z", "i"],
            [null, null, null]);

        var (ids, prosody) = PhonemeEncoder.Encode(phonemizer, "dummy", MakeMap());

        Assert.Equal([10, 11], ids);
        Assert.Equal(2, prosody.Count);
    }

    // ----------------------------------------------------------------
    // 4. MultiIdToken
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_MultiIdToken_DuplicatesProsody()
    {
        // Override "a" to map to two IDs.
        var map = MakeMap();
        map["a"] = [10, 11];

        var prosodyA = new ProsodyInfo(1, 2, 3);
        var phonemizer = new StubPhonemizer(
            ["a", "k"],
            [prosodyA, null]);

        var (ids, prosody) = PhonemeEncoder.Encode(phonemizer, "dummy", map);

        // "a" expands to [10, 11], "k" stays [12].
        Assert.Equal([10, 11, 12], ids);
        Assert.Equal(3, prosody.Count);
        // Prosody is duplicated for each ID of the multi-ID token.
        Assert.Equal(prosodyA, prosody[0]);
        Assert.Equal(prosodyA, prosody[1]);
        Assert.Null(prosody[2]);
    }

    // ----------------------------------------------------------------
    // 5. EmptyInput_ReturnsEmpty
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_EmptyInput_ReturnsEmpty()
    {
        var phonemizer = new StubPhonemizer([], []);

        var (ids, prosody) = PhonemeEncoder.Encode(phonemizer, "", MakeMap());

        Assert.Empty(ids);
        Assert.Empty(prosody);
    }

    // ================================================================
    // EncodeDirect tests
    // ================================================================

    // ----------------------------------------------------------------
    // 6. ConvertToLongArray
    // ----------------------------------------------------------------

    [Fact]
    public void EncodeDirect_ConvertToLongArray()
    {
        var phonemizer = new StubPhonemizer(
            ["^", "a", "$"],
            [null, null, null]);

        var (phonemeIds, _) = PhonemeEncoder.EncodeDirect(phonemizer, "dummy", MakeMap());

        Assert.Equal([1L, 10L, 2L], phonemeIds);
        Assert.IsType<long[]>(phonemeIds);
    }

    // ----------------------------------------------------------------
    // 7. ProsodyFlat_CorrectLayout
    // ----------------------------------------------------------------

    [Fact]
    public void EncodeDirect_ProsodyFlat_CorrectLayout()
    {
        var p0 = new ProsodyInfo(1, 2, 3);
        var p2 = new ProsodyInfo(4, 5, 6);

        // Three tokens: prosody, null, prosody.
        var phonemizer = new StubPhonemizer(
            ["a", "k", "i"],
            [p0, null, p2]);

        var (phonemeIds, prosodyFlat) = PhonemeEncoder.EncodeDirect(phonemizer, "dummy", MakeMap());

        Assert.Equal([10L, 12L, 11L], phonemeIds);
        Assert.NotNull(prosodyFlat);

        // Expected flat layout: [1,2,3, 0,0,0, 4,5,6]
        Assert.Equal(9, prosodyFlat!.Length);
        Assert.Equal([1L, 2L, 3L, 0L, 0L, 0L, 4L, 5L, 6L], prosodyFlat);
    }

    // ----------------------------------------------------------------
    // 8. NoProsody_ReturnsNull
    // ----------------------------------------------------------------

    [Fact]
    public void EncodeDirect_NoProsody_ReturnsNull()
    {
        var phonemizer = new StubPhonemizer(
            ["a", "i"],
            [null, null]);

        var (_, prosodyFlat) = PhonemeEncoder.EncodeDirect(phonemizer, "dummy", MakeMap());

        Assert.Null(prosodyFlat);
    }

    // ----------------------------------------------------------------
    // 9. PostProcessIds_Called
    // ----------------------------------------------------------------

    [Fact]
    public void EncodeDirect_PostProcessIds_Called()
    {
        // Use a post-processor that prepends BOS=1 and appends EOS=2,
        // with inter-phoneme padding=0, mimicking English behaviour.
        var phonemizer = new StubPhonemizer(
            ["a", "i"],
            [null, null],
            postProcess: (ids, prosody, map) =>
            {
                var newIds = new List<int> { 1 };
                var newProsody = new List<ProsodyInfo?> { null };
                for (int i = 0; i < ids.Count; i++)
                {
                    newIds.Add(ids[i]);
                    newProsody.Add(prosody[i]);
                    newIds.Add(0);       // padding
                    newProsody.Add(null);
                }
                newIds.Add(2);
                newProsody.Add(null);
                return (newIds, newProsody);
            });

        var (phonemeIds, _) = PhonemeEncoder.EncodeDirect(phonemizer, "dummy", MakeMap());

        Assert.True(phonemizer.PostProcessIdsCalled);
        // Expected: [BOS=1, a=10, pad=0, i=11, pad=0, EOS=2]
        Assert.Equal([1L, 10L, 0L, 11L, 0L, 2L], phonemeIds);
    }

    // ----------------------------------------------------------------
    // 10. NullPhonemizer_ThrowsArgumentNullException
    // ----------------------------------------------------------------

    [Fact]
    public void Encode_NullPhonemizer_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => PhonemeEncoder.Encode(null!, "text", MakeMap()));
    }

    // ----------------------------------------------------------------
    // 11. LargeProsodyValues_EncodedCorrectly
    // ----------------------------------------------------------------

    [Fact]
    public void EncodeDirect_LargeProsodyValues_EncodedCorrectly()
    {
        var pMax = new ProsodyInfo(int.MaxValue, int.MaxValue, int.MaxValue);

        var phonemizer = new StubPhonemizer(
            ["a"],
            [pMax]);

        var (phonemeIds, prosodyFlat) = PhonemeEncoder.EncodeDirect(phonemizer, "dummy", MakeMap());

        Assert.Equal([10L], phonemeIds);
        Assert.NotNull(prosodyFlat);
        Assert.Equal(3, prosodyFlat!.Length);
        Assert.Equal((long)int.MaxValue, prosodyFlat[0]);
        Assert.Equal((long)int.MaxValue, prosodyFlat[1]);
        Assert.Equal((long)int.MaxValue, prosodyFlat[2]);
    }
}
