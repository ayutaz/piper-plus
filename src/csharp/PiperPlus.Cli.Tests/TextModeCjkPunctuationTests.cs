using System.Linq;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// <c>--language en</c> (and the other Latin-script languages) reads the text
/// with that language's phonemizer alone, without
/// <see cref="PiperPlus.Core.Phonemize.MultilingualPhonemizer"/>, so it must
/// rewrite CJK punctuation as ASCII itself (Issue #823,
/// <c>docs/spec/cjk-punctuation-contract.toml</c>). Otherwise DotNetG2P drops
/// <c>，</c> and joins the words around it.
/// </summary>
public class TextModeCjkPunctuationTests
{
#pragma warning disable IL2026 // the CLI suppresses the same warning at its call sites
    private static IPhonemizer CliPhonemizer(string language) =>
        Program.ResolveTextModePhonemizer(language);
#pragma warning restore IL2026

    [Theory]
    [InlineData("en", "Hello，world", "Hello,world")]
    [InlineData("en", "Hello、world。", "Hello,world.")]
    [InlineData("en", "I have ３ cats．", "I have 3 cats.")]
    [InlineData("es", "Hola，amigo！", "Hola,amigo!")]
    [InlineData("fr", "Bonjour，le monde！", "Bonjour,le monde!")]
    [InlineData("pt", "Olá，mundo！", "Olá,mundo!")]
    [InlineData("sv", "Hej，världen！", "Hej,världen!")]
    public void LatinLanguage_ReadsCjkPunctuationLikeAscii(string language, string cjk, string ascii)
    {
        var phonemizer = CliPhonemizer(language);

        Assert.Equal(phonemizer.Phonemize(ascii), phonemizer.Phonemize(cjk));
    }

    [Fact]
    public void NonLatinLanguage_IsNotRewritten()
    {
        // Chinese maps ，。 to , . itself.
        var phonemizer = CliPhonemizer("zh");

        Assert.Equal(1, phonemizer.Phonemize("你好，今天天气很好。").Count(t => t == ","));
    }
}
