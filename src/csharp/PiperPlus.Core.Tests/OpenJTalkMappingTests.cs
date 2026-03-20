using PiperPlus.Core.Mapping;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="OpenJTalkToPiperMapping"/>.
/// Covers round-trip consistency, unknown token pass-through, empty input,
/// and all 29 PUA entries.
/// </summary>
public sealed class OpenJTalkMappingTests
{
    // ================================================================
    // 1. CharToToken_RoundTrip_ConsistentWithTokenToChar
    // ================================================================

    [Fact]
    public void CharToToken_RoundTrip_ConsistentWithTokenToChar()
    {
        // For every (token, char) in TokenToChar, CharToToken[char] must == token.
        foreach (var (token, ch) in OpenJTalkToPiperMapping.TokenToChar)
        {
            Assert.True(
                OpenJTalkToPiperMapping.CharToToken.ContainsKey(ch),
                $"CharToToken missing entry for PUA char U+{(int)ch:X4} (token: {token})");

            Assert.Equal(token, OpenJTalkToPiperMapping.CharToToken[ch]);
        }
    }

    // ================================================================
    // 2. MapToken_UnknownMultiCharToken_PassThrough
    // ================================================================

    [Fact]
    public void MapToken_UnknownMultiCharToken_PassThrough()
    {
        // A multi-character token not in the fixed table is returned unchanged.
        var result = OpenJTalkToPiperMapping.MapToken("xyz");

        Assert.Equal("xyz", result);
    }

    // ================================================================
    // 3. MapSequence_EmptyInput_ReturnsEmpty
    // ================================================================

    [Fact]
    public void MapSequence_EmptyInput_ReturnsEmpty()
    {
        var result = OpenJTalkToPiperMapping.MapSequence(Array.Empty<string>());

        Assert.Empty(result);
    }

    // ================================================================
    // 4. MapToken_AllPuaEntries_ProduceCorrectChar
    // ================================================================

    public static TheoryData<string, char> AllPuaEntries
    {
        get
        {
            var data = new TheoryData<string, char>();
            foreach (var (token, ch) in OpenJTalkToPiperMapping.TokenToChar)
            {
                data.Add(token, ch);
            }
            return data;
        }
    }

    [Theory]
    [MemberData(nameof(AllPuaEntries))]
    public void MapToken_AllPuaEntries_ProduceCorrectChar(string token, char expectedChar)
    {
        var result = OpenJTalkToPiperMapping.MapToken(token);

        Assert.Equal(expectedChar.ToString(), result);
    }

    // ================================================================
    // 5. MapToken_SingleChar_PassThrough
    // ================================================================

    [Theory]
    [InlineData("a")]
    [InlineData("k")]
    [InlineData("o")]
    public void MapToken_SingleChar_PassThrough(string token)
    {
        var result = OpenJTalkToPiperMapping.MapToken(token);

        Assert.Equal(token, result);
    }

    // ================================================================
    // 6. MapSequence_AllSingleChars_AllPassThrough
    // ================================================================

    [Fact]
    public void MapSequence_AllSingleChars_AllPassThrough()
    {
        var input = new[] { "a", "k", "o" };

        var result = OpenJTalkToPiperMapping.MapSequence(input);

        Assert.Equal(input, result);
    }

    // ================================================================
    // 7. MapSequence_MixedTokens_CorrectMapping
    // ================================================================

    [Fact]
    public void MapSequence_MixedTokens_CorrectMapping()
    {
        // Mix of single chars (pass-through) and PUA tokens (mapped)
        var input = new[] { "a", "ch", "o", "N_m" };

        var result = OpenJTalkToPiperMapping.MapSequence(input);

        Assert.Equal(new[] { "a", "\uE00E", "o", "\uE019" }, result);
    }

    // ================================================================
    // 8. ChineseAffricates_MappedCorrectly
    // ================================================================

    [Fact]
    public void ChineseAffricates_MappedCorrectly()
    {
        // tɕ (t\u0255) → U+E023
        var result = OpenJTalkToPiperMapping.MapToken("t\u0255");

        Assert.Equal("\uE023", result);
    }

    // ================================================================
    // 9. FrenchNasalVowels_MappedCorrectly
    // ================================================================

    [Fact]
    public void FrenchNasalVowels_MappedCorrectly()
    {
        // ɛ̃ (\u025B\u0303) → U+E056
        var result = OpenJTalkToPiperMapping.MapToken("\u025B\u0303");

        Assert.Equal("\uE056", result);
    }

    // ================================================================
    // 10. KoreanTensed_MappedCorrectly
    // ================================================================

    [Fact]
    public void KoreanTensed_MappedCorrectly()
    {
        // p͈ (p\u0348) → U+E04B
        var result = OpenJTalkToPiperMapping.MapToken("p\u0348");

        Assert.Equal("\uE04B", result);
    }
}
