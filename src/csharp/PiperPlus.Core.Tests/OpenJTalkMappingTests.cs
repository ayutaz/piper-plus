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
}
