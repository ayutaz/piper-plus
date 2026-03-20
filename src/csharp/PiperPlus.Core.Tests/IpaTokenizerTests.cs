using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="IpaTokenizer"/>.
/// Covers simple tokenization, space handling, combining marks,
/// digraph matching, and language-specific IPA patterns.
/// </summary>
public sealed class IpaTokenizerTests
{
    // ================================================================
    // Basic tokenization (no digraphs)
    // ================================================================

    [Fact]
    public void Tokenize_SimpleChars_NoDigraphs()
    {
        var result = IpaTokenizer.Tokenize("abc");

        Assert.Equal(["a", "b", "c"], result);
    }

    [Fact]
    public void Tokenize_SpaceBecomesStandaloneToken()
    {
        var result = IpaTokenizer.Tokenize("a b");

        Assert.Equal(["a", " ", "b"], result);
    }

    [Fact]
    public void Tokenize_EmptyString_ReturnsEmpty()
    {
        var result = IpaTokenizer.Tokenize("");

        Assert.Empty(result);
    }

    [Fact]
    public void Tokenize_OnlySpaces_EachIsToken()
    {
        var result = IpaTokenizer.Tokenize("  ");

        Assert.Equal([" ", " "], result);
    }

    // ================================================================
    // Combining marks
    // ================================================================

    [Fact]
    public void Tokenize_CombiningTilde_MergesWithBase()
    {
        // U+025B (ɛ) + U+0303 (combining tilde) -> single token "ɛ̃"
        var result = IpaTokenizer.Tokenize("\u025b\u0303");

        Assert.Single(result);
        Assert.Equal("\u025b\u0303", result[0]);
    }

    [Fact]
    public void Tokenize_MultipleCombiningMarks_SingleToken()
    {
        // base + 2 combining marks -> single token
        // e.g. "a" + U+0303 (combining tilde) + U+0301 (combining acute)
        var result = IpaTokenizer.Tokenize("a\u0303\u0301");

        Assert.Single(result);
        Assert.Equal("a\u0303\u0301", result[0]);
    }

    [Fact]
    public void Tokenize_FrenchNasalVowel_CombiningMark()
    {
        // U+025B (ɛ) + U+0303 (combining tilde) -> single token
        // French nasal vowel; no digraph needed because combining mark is auto-merged
        var result = IpaTokenizer.Tokenize("\u025b\u0303");

        Assert.Single(result);
        Assert.Equal("\u025b\u0303", result[0]);
    }

    [Fact]
    public void Tokenize_PortugueseNFC_PrecomposedNasal()
    {
        // U+00E3 "ã" is a precomposed character (NFC), not base + combining mark.
        // It should be emitted as a single token.
        var result = IpaTokenizer.Tokenize("\u00e3");

        Assert.Single(result);
        Assert.Equal("\u00e3", result[0]);
    }

    // ================================================================
    // Digraph handling
    // ================================================================

    [Fact]
    public void Tokenize_SpanishDigraph_rr()
    {
        var digraphs = new HashSet<string> { "rr" };

        var result = IpaTokenizer.Tokenize("rr", digraphs);

        Assert.Single(result);
        Assert.Equal("rr", result[0]);
    }

    [Fact]
    public void Tokenize_Affricate_tesh()
    {
        // "tʃ" = "t" + U+0283 (ʃ), treated as digraph
        var digraphs = new HashSet<string> { "t\u0283" };

        var result = IpaTokenizer.Tokenize("t\u0283", digraphs);

        Assert.Single(result);
        Assert.Equal("t\u0283", result[0]);
    }

    [Fact]
    public void Tokenize_Affricate_dezh()
    {
        // "dʒ" = "d" + U+0292 (ʒ), treated as digraph
        var digraphs = new HashSet<string> { "d\u0292" };

        var result = IpaTokenizer.Tokenize("d\u0292", digraphs);

        Assert.Single(result);
        Assert.Equal("d\u0292", result[0]);
    }

    [Fact]
    public void Tokenize_MixedDigraphsAndSingles()
    {
        // "atʃo" -> ["a", "tʃ", "o"]
        var digraphs = new HashSet<string> { "t\u0283" };

        var result = IpaTokenizer.Tokenize("at\u0283o", digraphs);

        Assert.Equal(["a", "t\u0283", "o"], result);
    }

    [Fact]
    public void Tokenize_DigraphAtEnd()
    {
        // "arr" with {"rr"} -> ["a", "rr"]
        var digraphs = new HashSet<string> { "rr" };

        var result = IpaTokenizer.Tokenize("arr", digraphs);

        Assert.Equal(["a", "rr"], result);
    }

    [Fact]
    public void Tokenize_DigraphAtStart()
    {
        // "rra" with {"rr"} -> ["rr", "a"]
        var digraphs = new HashSet<string> { "rr" };

        var result = IpaTokenizer.Tokenize("rra", digraphs);

        Assert.Equal(["rr", "a"], result);
    }

    [Fact]
    public void Tokenize_NonMatchingPair()
    {
        // "rs" with {"rr"} -> ["r", "s"] (no digraph match)
        var digraphs = new HashSet<string> { "rr" };

        var result = IpaTokenizer.Tokenize("rs", digraphs);

        Assert.Equal(["r", "s"], result);
    }

    [Fact]
    public void Tokenize_NullDigraphSet_SameAsNoDigraphs()
    {
        var result = IpaTokenizer.Tokenize("abc", null);

        Assert.Equal(["a", "b", "c"], result);
    }

    // ================================================================
    // Stress markers and suprasegmentals
    // ================================================================

    [Fact]
    public void Tokenize_StressMarker_StandaloneToken()
    {
        // U+02C8 (ˈ) primary stress marker -> standalone token
        var result = IpaTokenizer.Tokenize("\u02c8");

        Assert.Single(result);
        Assert.Equal("\u02c8", result[0]);
    }

    // ================================================================
    // Complex realistic inputs
    // ================================================================

    [Fact]
    public void Tokenize_ComplexFrenchSequence()
    {
        // "bɔ̃ʒuʁ" = b + ɔ̃ (U+0254 + U+0303) + ʒ (U+0292) + u + ʁ (U+0281)
        // No digraphs needed; combining mark handles the nasal vowel
        var result = IpaTokenizer.Tokenize("b\u0254\u0303\u0292u\u0281");

        Assert.Equal(["b", "\u0254\u0303", "\u0292", "u", "\u0281"], result);
    }

    // ================================================================
    // Theory: parameterized edge cases
    // ================================================================

    [Theory]
    [InlineData("a", new[] { "a" })]
    [InlineData("ab", new[] { "a", "b" })]
    [InlineData(" ", new[] { " " })]
    [InlineData("a b c", new[] { "a", " ", "b", " ", "c" })]
    public void Tokenize_VariousSimpleInputs(string input, string[] expected)
    {
        var result = IpaTokenizer.Tokenize(input);

        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData("rr", new[] { "rr" })]
    [InlineData("rrr", new[] { "rr", "r" })]
    [InlineData("arrab", new[] { "a", "rr", "a", "b" })]
    public void Tokenize_DigraphTheory(string input, string[] expected)
    {
        var digraphs = new HashSet<string> { "rr" };

        var result = IpaTokenizer.Tokenize(input, digraphs);

        Assert.Equal(expected, result);
    }
}
