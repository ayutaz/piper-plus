using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for the default <see cref="IPhonemizer.PostProcessIds"/> implementation.
/// Uses a minimal stub that does NOT override PostProcessIds, so the interface
/// default method is exercised.
/// </summary>
public sealed class IPhonemizerDefaultTests
{
    // ================================================================
    // Minimal stub — relies on the default PostProcessIds implementation
    // ================================================================

    /// <summary>
    /// Minimal <see cref="IPhonemizer"/> that does NOT override
    /// <see cref="IPhonemizer.PostProcessIds"/>, exercising the default no-op path.
    /// </summary>
    private sealed class MinimalPhonemizer : IPhonemizer
    {
        public List<string> Phonemize(string text) => [];

        public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
            => ([], []);

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

        // PostProcessIds is intentionally NOT overridden.
    }

    // ================================================================
    // 1. PostProcessIds_DefaultImplementation_ReturnsInputsUnchanged
    // ================================================================

    [Fact]
    public void PostProcessIds_DefaultImplementation_ReturnsInputsUnchanged()
    {
        IPhonemizer phonemizer = new MinimalPhonemizer();

        var ids = new List<int> { 1, 10, 11, 2 };
        var prosody = new List<ProsodyInfo?>
        {
            null,
            new ProsodyInfo(-2, 1, 5),
            new ProsodyInfo(0, 3, 5),
            null,
        };
        var map = new Dictionary<string, int[]> { ["a"] = [10] };

        var (resultIds, resultProsody) = phonemizer.PostProcessIds(ids, prosody, map);

        Assert.Equal([1, 10, 11, 2], resultIds);
        Assert.Equal(4, resultProsody.Count);
        Assert.Null(resultProsody[0]);
        Assert.Equal(new ProsodyInfo(-2, 1, 5), resultProsody[1]);
        Assert.Equal(new ProsodyInfo(0, 3, 5), resultProsody[2]);
        Assert.Null(resultProsody[3]);
    }

    // ================================================================
    // 2. PostProcessIds_DefaultImpl_ReturnsSameReferences
    // ================================================================

    [Fact]
    public void PostProcessIds_DefaultImpl_ReturnsSameReferences()
    {
        IPhonemizer phonemizer = new MinimalPhonemizer();

        var ids = new List<int> { 1, 10, 2 };
        var prosody = new List<ProsodyInfo?> { null, null, null };
        var map = new Dictionary<string, int[]> { ["a"] = [10] };

        var (resultIds, resultProsody) = phonemizer.PostProcessIds(ids, prosody, map);

        // The default implementation returns the exact same list instances.
        Assert.Same(ids, resultIds);
        Assert.Same(prosody, resultProsody);
    }
}
