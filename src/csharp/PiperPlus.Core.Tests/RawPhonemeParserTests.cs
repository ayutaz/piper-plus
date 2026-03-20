using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="RawPhonemeParser"/>.
/// Covers direct lookup, PUA fallback, unknown-token skipping, edge cases,
/// and argument validation.
/// </summary>
public sealed class RawPhonemeParserTests
{
    // ================================================================
    // Shared phoneme_id_map used by most tests
    // ================================================================

    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],
        ["^"] = [1],
        ["$"] = [2],
        ["a"] = [10],
        ["i"] = [11],
        ["k"] = [12],
        ["N"] = [13],
        ["\uE000"] = [17], // a: PUA
        ["\uE00E"] = [30], // ch PUA
        ["\uE019"] = [40], // N_m PUA
    };

    // ================================================================
    // 1. Parse_ValidTokens
    // ================================================================

    [Fact]
    public void Parse_ValidTokens()
    {
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("^ a i $", map);

        Assert.Equal([1L, 10L, 11L, 2L], result);
    }

    // ================================================================
    // 2. Parse_PuaFallback
    // ================================================================

    [Fact]
    public void Parse_PuaFallback()
    {
        // Multi-char tokens resolved via OpenJTalkToPiperMapping -> PUA -> map.
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("a: ch N_m", map);

        Assert.Equal([17L, 30L, 40L], result);
    }

    // ================================================================
    // 3. Parse_UnknownToken_Skipped
    // ================================================================

    [Fact]
    public void Parse_UnknownToken_Skipped()
    {
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("^ xyz $", map);

        // "xyz" is not in the map nor in PUA mapping, so it is skipped.
        Assert.Equal([1L, 2L], result);
    }

    // ================================================================
    // 4. Parse_EmptyString
    // ================================================================

    [Fact]
    public void Parse_EmptyString()
    {
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("", map);

        Assert.Empty(result);
    }

    // ================================================================
    // 5. Parse_NullString_ReturnsEmpty
    // ================================================================

    [Fact]
    public void Parse_NullString_ReturnsEmpty()
    {
        // The implementation treats null the same as empty/whitespace (returns []).
        var map = MakeMap();

        var result = RawPhonemeParser.Parse(null!, map);

        Assert.Empty(result);
    }

    // ================================================================
    // 6. Parse_NullMap_Throws
    // ================================================================

    [Fact]
    public void Parse_NullMap_Throws()
    {
        Assert.Throws<ArgumentNullException>(
            () => RawPhonemeParser.Parse("^ a $", null!));
    }

    // ================================================================
    // 7. Parse_SingleCharTokens
    // ================================================================

    [Fact]
    public void Parse_SingleCharTokens()
    {
        // Single-character tokens are looked up directly in the map.
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("a k N", map);

        Assert.Equal([10L, 12L, 13L], result);
    }

    // ================================================================
    // 8. Parse_MixedKnownUnknown
    // ================================================================

    [Fact]
    public void Parse_MixedKnownUnknown()
    {
        // Mix of direct-lookup tokens, PUA tokens, and unknown tokens.
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("^ a zzz ch $ qqq i", map);

        // "zzz" and "qqq" are unknown and skipped.
        Assert.Equal([1L, 10L, 30L, 2L, 11L], result);
    }

    // ================================================================
    // 9. Parse_WhitespaceOnlyString_ReturnsEmpty
    // ================================================================

    [Fact]
    public void Parse_WhitespaceOnlyString_ReturnsEmpty()
    {
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("   \t  ", map);

        Assert.Empty(result);
    }

    // ================================================================
    // 10. Parse_MultipleSpacesBetweenTokens_Handled
    // ================================================================

    [Fact]
    public void Parse_MultipleSpacesBetweenTokens_Handled()
    {
        // Multiple spaces between tokens should be treated like single spaces.
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("^   a    $", map);

        Assert.Equal([1L, 10L, 2L], result);
    }

    // ================================================================
    // 11. Parse_MultiIdPhoneme_AllIdsFlattened
    // ================================================================

    [Fact]
    public void Parse_MultiIdPhoneme_AllIdsFlattened()
    {
        // A phoneme mapped to multiple IDs should produce all IDs in order.
        var map = MakeMap();
        map["x"] = [10, 11];

        var result = RawPhonemeParser.Parse("^ x $", map);

        Assert.Equal([1L, 10L, 11L, 2L], result);
    }

    // ================================================================
    // 12. Parse_TokenCase_MustBeExact
    // ================================================================

    [Fact]
    public void Parse_TokenCase_MustBeExact()
    {
        // "a" is in the map but "A" is not — case-sensitive lookup must skip "A".
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("a A i", map);

        // "A" is skipped because the map only has lowercase "a".
        Assert.Equal([10L, 11L], result);
    }

    // ================================================================
    // 13. Parse_OrderPreserved
    // ================================================================

    [Fact]
    public void Parse_OrderPreserved()
    {
        // Verify the exact output order matches the input token order.
        var map = MakeMap();

        var result = RawPhonemeParser.Parse("$ a ^ a $", map);

        Assert.Equal([2L, 10L, 1L, 10L, 2L], result);
    }
}
