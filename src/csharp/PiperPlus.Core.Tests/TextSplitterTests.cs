using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

public class TextSplitterTests
{
    // ================================================================
    // Basic splitting
    // ================================================================

    [Fact]
    public void SingleSentence_NoSplitting()
    {
        var result = TextSplitter.SplitSentences("Hello world.");
        Assert.Single(result);
        Assert.Equal("Hello world.", result[0]);
    }

    [Fact]
    public void MultipleEnglishSentences()
    {
        var result = TextSplitter.SplitSentences("Hello. How are you? Fine!");
        Assert.Equal(3, result.Count);
        Assert.Equal("Hello.", result[0]);
        Assert.Equal("How are you?", result[1]);
        Assert.Equal("Fine!", result[2]);
    }

    [Fact]
    public void JapaneseSentences()
    {
        var result = TextSplitter.SplitSentences(
            "\u3053\u3093\u306b\u3061\u306f\u3002\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3067\u3059\u306d\u3002");
        Assert.Equal(2, result.Count);
        Assert.Equal("\u3053\u3093\u306b\u3061\u306f\u3002", result[0]);
        Assert.Equal("\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3067\u3059\u306d\u3002", result[1]);
    }

    [Fact]
    public void MixedLanguageSentences()
    {
        var result = TextSplitter.SplitSentences(
            "\u65e5\u672c\u8a9e\u306e\u30c6\u30b9\u30c8\u3002English test! \u6df7\u5408\u30c6\u30b9\u30c8\uff1f");
        Assert.Equal(3, result.Count);
        Assert.Equal("\u65e5\u672c\u8a9e\u306e\u30c6\u30b9\u30c8\u3002", result[0]);
        Assert.Equal("English test!", result[1]);
        Assert.Equal("\u6df7\u5408\u30c6\u30b9\u30c8\uff1f", result[2]);
    }

    // ================================================================
    // Closing punctuation
    // ================================================================

    [Fact]
    public void ClosingPunctuation_JapaneseQuotes()
    {
        // 「こんにちは。」次の文。
        var result = TextSplitter.SplitSentences(
            "\u300c\u3053\u3093\u306b\u3061\u306f\u3002\u300d\u6b21\u306e\u6587\u3002");
        Assert.Equal(2, result.Count);
        Assert.Equal("\u300c\u3053\u3093\u306b\u3061\u306f\u3002\u300d", result[0]);
        Assert.Equal("\u6b21\u306e\u6587\u3002", result[1]);
    }

    [Fact]
    public void ClosingPunctuation_WesternQuotes()
    {
        var result = TextSplitter.SplitSentences("She said \"Hello.\" Then left.");
        Assert.Equal(2, result.Count);
        Assert.Equal("She said \"Hello.\"", result[0]);
        Assert.Equal("Then left.", result[1]);
    }

    [Fact]
    public void ClosingPunctuation_RightDoubleQuotationMark()
    {
        // U+201D right double quotation mark
        var result = TextSplitter.SplitSentences("She said \u201CHello.\u201D Then left.");
        Assert.Equal(2, result.Count);
        Assert.Equal("She said \u201CHello.\u201D", result[0]);
        Assert.Equal("Then left.", result[1]);
    }

    [Fact]
    public void ClosingPunctuation_RightSingleQuotationMark()
    {
        // U+2019 right single quotation mark
        var result = TextSplitter.SplitSentences("She said \u2018Hello.\u2019 Then left.");
        Assert.Equal(2, result.Count);
        Assert.Equal("She said \u2018Hello.\u2019", result[0]);
        Assert.Equal("Then left.", result[1]);
    }

    [Fact]
    public void ClosingPunctuation_RightPointingDoubleAngleQuotationMark()
    {
        // U+00BB right-pointing double angle quotation mark
        var result = TextSplitter.SplitSentences("\u00ABBonjour.\u00BB Au revoir.");
        Assert.Equal(2, result.Count);
        Assert.Equal("\u00ABBonjour.\u00BB", result[0]);
        Assert.Equal("Au revoir.", result[1]);
    }

    // ================================================================
    // Edge cases: empty and whitespace
    // ================================================================

    [Fact]
    public void EmptyInput_ReturnsEmptyList()
    {
        var result = TextSplitter.SplitSentences("");
        Assert.Empty(result);
    }

    [Fact]
    public void NullInput_ReturnsEmptyList()
    {
        var result = TextSplitter.SplitSentences(null!);
        Assert.Empty(result);
    }

    [Fact]
    public void WhitespaceOnly_ReturnsEmptyList()
    {
        var result = TextSplitter.SplitSentences("   ");
        Assert.Empty(result);
    }

    // ================================================================
    // Edge cases: no terminator
    // ================================================================

    [Fact]
    public void NoTerminator_ReturnsSingleSentence()
    {
        var result = TextSplitter.SplitSentences("This has no ending punctuation");
        Assert.Single(result);
        Assert.Equal("This has no ending punctuation", result[0]);
    }

    // ================================================================
    // Edge cases: consecutive terminators
    // ================================================================

    [Fact]
    public void ConsecutiveTerminators()
    {
        // "Really?! Yes." -- '?' triggers first split, '!' is its own sentence
        var result = TextSplitter.SplitSentences("Really?! Yes.");
        Assert.Equal(3, result.Count);
        Assert.Equal("Really?", result[0]);
        Assert.Equal("!", result[1]);
        Assert.Equal("Yes.", result[2]);
    }

    // ================================================================
    // Edge cases: trailing spaces
    // ================================================================

    [Fact]
    public void TrailingSpaces_Trimmed()
    {
        var result = TextSplitter.SplitSentences("Hello.   World.   ");
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello.", result[0]);
        Assert.Equal("World.", result[1]);
    }

    [Fact]
    public void LeadingSpaces_Trimmed()
    {
        var result = TextSplitter.SplitSentences("   Hello. World.");
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello.", result[0]);
        Assert.Equal("World.", result[1]);
    }

    // ================================================================
    // Fullwidth punctuation
    // ================================================================

    [Fact]
    public void FullwidthPunctuation()
    {
        // すごい！本当ですか？はい。
        var result = TextSplitter.SplitSentences(
            "\u3059\u3054\u3044\uff01\u672c\u5f53\u3067\u3059\u304b\uff1f\u306f\u3044\u3002");
        Assert.Equal(3, result.Count);
        Assert.Equal("\u3059\u3054\u3044\uff01", result[0]);
        Assert.Equal("\u672c\u5f53\u3067\u3059\u304b\uff1f", result[1]);
        Assert.Equal("\u306f\u3044\u3002", result[2]);
    }

    // ================================================================
    // Newline as whitespace
    // ================================================================

    [Fact]
    public void NewlineSeparator_TreatedAsWhitespace()
    {
        var result = TextSplitter.SplitSentences("Hello.\nWorld.");
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello.", result[0]);
        Assert.Equal("World.", result[1]);
    }

    // ================================================================
    // Single character sentence
    // ================================================================

    [Fact]
    public void SingleCharSentences()
    {
        var result = TextSplitter.SplitSentences("A. B.");
        Assert.Equal(2, result.Count);
        Assert.Equal("A.", result[0]);
        Assert.Equal("B.", result[1]);
    }
}
