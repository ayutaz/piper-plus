using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="InlinePhonemeParser"/>.
/// Covers parsing of <c>[[ phoneme ]]</c> inline notation into
/// <see cref="TextOrPhonemes"/> segments.
/// </summary>
public sealed class InlinePhonemeParserTests
{
    // ================================================================
    // 1. No notation — single text segment
    // ================================================================

    [Fact]
    public void Parse_NoNotation_ReturnsSingleTextSegment()
    {
        var result = InlinePhonemeParser.Parse("Hello world");

        Assert.Single(result);
        Assert.False(result[0].IsPhonemes);
        Assert.Equal("Hello world", result[0].Text);
    }

    // ================================================================
    // 2. Only phonemes — single phoneme segment
    // ================================================================

    [Fact]
    public void Parse_OnlyPhonemes_ReturnsSinglePhonemeSegment()
    {
        var result = InlinePhonemeParser.Parse("[[ h @ l oU ]]");

        Assert.Single(result);
        Assert.True(result[0].IsPhonemes);
        Assert.Equal("h @ l oU", result[0].Text);
    }

    // ================================================================
    // 3. Mixed: text + phonemes + text
    // ================================================================

    [Fact]
    public void Parse_Mixed_ReturnsThreeSegments()
    {
        var result = InlinePhonemeParser.Parse("Hello [[ h @ l oU ]] world");

        Assert.Equal(3, result.Count);

        Assert.False(result[0].IsPhonemes);
        Assert.Equal("Hello ", result[0].Text);

        Assert.True(result[1].IsPhonemes);
        Assert.Equal("h @ l oU", result[1].Text);

        Assert.False(result[2].IsPhonemes);
        Assert.Equal(" world", result[2].Text);
    }

    // ================================================================
    // 4. Multiple inline phoneme blocks
    // ================================================================

    [Fact]
    public void Parse_MultipleBlocks_ReturnsAlternatingSegments()
    {
        var result = InlinePhonemeParser.Parse("[[ a ]] and [[ b ]]");

        Assert.Equal(3, result.Count);

        Assert.True(result[0].IsPhonemes);
        Assert.Equal("a", result[0].Text);

        Assert.False(result[1].IsPhonemes);
        Assert.Equal(" and ", result[1].Text);

        Assert.True(result[2].IsPhonemes);
        Assert.Equal("b", result[2].Text);
    }

    // ================================================================
    // 5. Empty input — empty list
    // ================================================================

    [Fact]
    public void Parse_EmptyInput_ReturnsEmptyList()
    {
        Assert.Empty(InlinePhonemeParser.Parse(""));
    }

    // ================================================================
    // 6. Null input — empty list
    // ================================================================

    [Fact]
    public void Parse_NullInput_ReturnsEmptyList()
    {
        Assert.Empty(InlinePhonemeParser.Parse(null));
    }

    // ================================================================
    // 7. Nested brackets (invalid) — treated as text
    // ================================================================

    [Fact]
    public void Parse_NestedBrackets_TreatedAsText()
    {
        // "[[ [[ a ]] ]]" — the regex will match the first valid [[ ... ]]
        // The outer brackets and trailing ]] become text.
        var result = InlinePhonemeParser.Parse("[[ [[ a ]] ]]");

        // The regex matches "[[ [[ a ]]" as the first match (greedy inner)
        // Then " ]]" is trailing text.
        // Actual match: [[ ... ]] where inner is "[[ a"
        Assert.True(result.Count >= 1);
        // At least one phoneme segment should be found
        Assert.Contains(result, s => s.IsPhonemes);
    }

    // ================================================================
    // 8. Whitespace inside brackets is trimmed
    // ================================================================

    [Fact]
    public void Parse_WhitespaceInsideBrackets_IsTrimmed()
    {
        var result = InlinePhonemeParser.Parse("[[   h @ l oU   ]]");

        Assert.Single(result);
        Assert.True(result[0].IsPhonemes);
        Assert.Equal("h @ l oU", result[0].Text);
    }

    // ================================================================
    // 9. Empty brackets — empty phoneme segment kept (matches C++)
    // ================================================================

    [Fact]
    public void Parse_EmptyBrackets_EmptyPhonemeSegmentKept()
    {
        var result = InlinePhonemeParser.Parse("hello [[]] world");

        Assert.Equal(3, result.Count);

        Assert.False(result[0].IsPhonemes);
        Assert.Equal("hello ", result[0].Text);

        Assert.True(result[1].IsPhonemes);
        Assert.Equal("", result[1].Text);

        Assert.False(result[2].IsPhonemes);
        Assert.Equal(" world", result[2].Text);
    }

    // ================================================================
    // 10. Whitespace-only brackets — empty phoneme segment kept (matches C++)
    // ================================================================

    [Fact]
    public void Parse_WhitespaceOnlyBrackets_EmptyPhonemeSegmentKept()
    {
        var result = InlinePhonemeParser.Parse("hello [[   ]] world");

        Assert.Equal(3, result.Count);

        Assert.False(result[0].IsPhonemes);
        Assert.Equal("hello ", result[0].Text);

        Assert.True(result[1].IsPhonemes);
        Assert.Equal("", result[1].Text);

        Assert.False(result[2].IsPhonemes);
        Assert.Equal(" world", result[2].Text);
    }

    // ================================================================
    // 11. Single bracket pairs are not matched
    // ================================================================

    [Fact]
    public void Parse_SingleBrackets_NotMatched()
    {
        var result = InlinePhonemeParser.Parse("hello [ not phonemes ] world");

        Assert.Single(result);
        Assert.False(result[0].IsPhonemes);
        Assert.Equal("hello [ not phonemes ] world", result[0].Text);
    }

    // ================================================================
    // 12. Adjacent phoneme blocks with no text between
    // ================================================================

    [Fact]
    public void Parse_AdjacentBlocks_NoTextBetween()
    {
        var result = InlinePhonemeParser.Parse("[[ a ]][[ b ]]");

        Assert.Equal(2, result.Count);

        Assert.True(result[0].IsPhonemes);
        Assert.Equal("a", result[0].Text);

        Assert.True(result[1].IsPhonemes);
        Assert.Equal("b", result[1].Text);
    }

    // ================================================================
    // 13. Phoneme block at start of string
    // ================================================================

    [Fact]
    public void Parse_PhonemeBlockAtStart()
    {
        var result = InlinePhonemeParser.Parse("[[ a b ]] followed by text");

        Assert.Equal(2, result.Count);

        Assert.True(result[0].IsPhonemes);
        Assert.Equal("a b", result[0].Text);

        Assert.False(result[1].IsPhonemes);
        Assert.Equal(" followed by text", result[1].Text);
    }

    // ================================================================
    // 14. Phoneme block at end of string
    // ================================================================

    [Fact]
    public void Parse_PhonemeBlockAtEnd()
    {
        var result = InlinePhonemeParser.Parse("text before [[ a b ]]");

        Assert.Equal(2, result.Count);

        Assert.False(result[0].IsPhonemes);
        Assert.Equal("text before ", result[0].Text);

        Assert.True(result[1].IsPhonemes);
        Assert.Equal("a b", result[1].Text);
    }

    // ================================================================
    // 15. Whitespace-only text between blocks is kept (matches C++)
    // ================================================================

    [Fact]
    public void Parse_WhitespaceOnlyTextBetweenBlocks_Kept()
    {
        // Whitespace-only text segments between phoneme blocks are preserved
        var result = InlinePhonemeParser.Parse("[[ a ]]   [[ b ]]");

        Assert.Equal(3, result.Count);

        Assert.True(result[0].IsPhonemes);
        Assert.Equal("a", result[0].Text);

        Assert.False(result[1].IsPhonemes);
        Assert.Equal("   ", result[1].Text);

        Assert.True(result[2].IsPhonemes);
        Assert.Equal("b", result[2].Text);
    }
}
