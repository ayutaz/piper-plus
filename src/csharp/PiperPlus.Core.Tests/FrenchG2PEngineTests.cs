using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="FrenchG2PEngine"/>. The expected tokens are the
/// output of Python <c>phonemize_french()</c> (french.py) for the same input;
/// the full comparison with the Python golden is in PiperPlus.Cli.Tests
/// (G2pGoldenParityTests).
/// </summary>
public sealed class FrenchG2PEngineTests
{
    /// <summary>
    /// y_vowel for [y] (a bare "y" is the Japanese glide in the phoneme_id_map),
    /// elision clitics merged with the rest of the word (a part that is not a
    /// clitic stays a word of its own), and liaison before a vowel-initial word
    /// but not before a consonant or across punctuation; "c'est" is not a
    /// trigger and "un" links before h muet.
    /// </summary>
    [Theory]
    [InlineData("tu", "t|y_vowel")]
    [InlineData("l'ami", "l|a|m|i")]
    [InlineData("l\u2019ami", "l|a|m|i")]
    [InlineData("qu'il", "k|i|l")]
    [InlineData("aujourd'hui", "o|\u0292|u|\u0281| |\u0265|i")]
    [InlineData("les amis", "l|\u0259|z| |a|m|i")]
    [InlineData("les gar\u00e7ons", "l|\u0259| |\u0261|a|\u0281|s|\u0254\u0303")]
    [InlineData("les, amis", "l|\u0259|,| |a|m|i")]
    [InlineData("c'est un homme", "s|\u025b|s| |\u025b\u0303|n| |o|m")]
    [InlineData("Quand il parle", "k|\u0251\u0303|t| |i|l| |p|a|\u0281|l")]
    public void ToPhonemeList_MatchesPython(string text, string expected)
    {
        var engine = new FrenchG2PEngine();

        Assert.Equal(expected.Split('|'), engine.ToPhonemeList(text));
    }

    [Theory]
    [InlineData("feuille", "f|\u0153|j")]
    [InlineData("soleil", "s|o|l|\u025b|j")]
    [InlineData("question", "k|\u025b|s|t|j|\u0254\u0303")]
    [InlineData("nation", "n|a|s|j|\u0254\u0303")]
    [InlineData("ville", "v|i|l")]
    [InlineData("fille", "f|i|j")]
    [InlineData("parler", "p|a|\u0281|l|e")]
    [InlineData("hiver", "i|v|\u025b|\u0281")]
    [InlineData("exil", "\u0259|\u0261|z|i|l")]
    [InlineData("porte", "p|\u0254|\u0281|t")]
    [InlineData("temps", "t|\u0251\u0303")]
    [InlineData("maison", "m|\u025b|z|\u0254\u0303")]
    [InlineData("huit", "\u0265|i")]
    public void ConvertWord_MatchesPython(string word, string expected)
    {
        Assert.Equal(expected.Split('|'), FrenchG2PEngine.ConvertWord(word));
    }

    [Fact]
    public void ToPhonemeList_EmptyText_ReturnsEmpty()
    {
        var engine = new FrenchG2PEngine();

        Assert.Empty(engine.ToPhonemeList(string.Empty));
        Assert.Empty(engine.ToPhonemeList("   "));
    }
}
