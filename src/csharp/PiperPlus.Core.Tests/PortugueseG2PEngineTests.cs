using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PortugueseG2PEngine"/>. The expected tokens are the
/// output of Python <c>_convert_word()</c> / <c>phonemize_portuguese()</c>
/// (portuguese.py, Brazilian) for the same input; the full comparison with the
/// Python golden is in PiperPlus.Cli.Tests (G2pGoldenParityTests).
/// </summary>
public sealed class PortugueseG2PEngineTests
{
    /// <summary>
    /// The engine marks the stressed phoneme with a preceding <c>ˈ</c>, which
    /// <see cref="PortuguesePhonemizer"/> strips and turns into A2=2 (Python
    /// keeps the stress index next to the phonemes). Covered: ʁ for initial,
    /// doubled and coda r and ɾ between vowels, the reduction of unstressed
    /// final e/o to i/u, t/d palatalized before i, coda l as w, nasal vowels
    /// with the nasal consonant absorbed, qu + a/o as kw, and a space before
    /// every word after the first token, punctuation included.
    /// </summary>
    [Theory]
    [InlineData("Brasil", "b|ʁ|a|z|ˈ|i|w")]
    [InlineData("bom", "b|ˈ|õ")]
    [InlineData("sim", "s|ˈ|ĩ")]
    [InlineData("não", "n|ˈ|ã|u")]
    [InlineData("noite", "n|o|ˈ|i|tʃ|i")]
    [InlineData("carro", "k|ˈ|a|ʁ|u")]
    [InlineData("filho", "f|ˈ|i|ʎ|u")]
    [InlineData("manhã", "m|a|ɲ|ˈ|ã")]
    [InlineData("Boa tarde", "b|ˈ|o|a| |t|ˈ|a|ʁ|dʒ|i")]
    [InlineData("comê-lo", "k|o|m|ˈ|e| |l|ˈ|o")]
    [InlineData("quando", "k|w|ˈ|ã|d|u")]
    [InlineData("guerra", "ɡ|ˈ|e|ʁ|a")]
    [InlineData("exemplo", "e|z|ˈ|ẽ|p|l|u")]
    [InlineData("açúcar", "a|s|ˈ|u|k|a|ʁ")]
    [InlineData("São Paulo", "s|ˈ|ã|u| |p|a|ˈ|u|l|u")]
    [InlineData("Eu te amo.", "e|ˈ|u| |t|ˈ|e| |ˈ|a|m|u|.")]
    [InlineData("¿Como", "¿| |k|ˈ|o|m|u")]
    [InlineData("limões", "l|i|m|ˈ|õ|e|s")]
    [InlineData("cantam", "k|ˈ|ã|t|ã")]
    public void ToPhonemeList_MatchesPython(string text, string expected)
    {
        var engine = new PortugueseG2PEngine();

        Assert.Equal(expected.Split('|'), engine.ToPhonemeList(text));
    }

    [Theory]
    [InlineData("0")]
    [InlineData("100")]
    [InlineData("")]
    [InlineData("   ")]
    public void ToPhonemeList_NoPortugueseLetters_ReturnsEmpty(string text)
    {
        var engine = new PortugueseG2PEngine();

        Assert.Empty(engine.ToPhonemeList(text));
    }

    /// <summary>
    /// <see cref="PortuguesePhonemizer"/> over the engine gives Python's
    /// <c>phonemize_portuguese()</c> (no stress marks; tʃ / dʒ as PUA) and puts
    /// A2=2 on the stressed vowel.
    /// </summary>
    [Theory]
    [InlineData("noite", "n|o|i|tʃ|i")]
    [InlineData("Boa tarde", "b|o|a| |t|a|ʁ|dʒ|i")]
    [InlineData("dias", "dʒ|i|a|s")]
    public void Phonemizer_MatchesPython(string text, string expected)
    {
        var phonemizer = new PortuguesePhonemizer(new PortugueseG2PEngine());

        Assert.Equal(PiperPhonemeConverter.MapSequence([.. expected.Split('|')]), phonemizer.Phonemize(text));
    }

    [Fact]
    public void Phonemizer_StressedVowelProsody_MatchesPython()
    {
        var phonemizer = new PortuguesePhonemizer(new PortugueseG2PEngine());

        (List<string> tokens, List<ProsodyInfo?> prosody) = phonemizer.PhonemizeWithProsody("carro");

        Assert.Equal(["k", "a", "ʁ", "u"], tokens);
        Assert.Equal([0, 2, 0, 0], prosody.Select(p => p!.Value.A2));
        Assert.All(prosody, p => Assert.Equal(4, p!.Value.A3));
    }

    /// <summary>
    /// <see cref="EuropeanPortuguesePhonemizer"/> rewrites the BR output of the
    /// engine like Python <c>phonemize_european_portuguese()</c>.
    /// </summary>
    [Theory]
    [InlineData("noite", "n|o|i|t|ɨ")]
    [InlineData("Boa tarde", "b|o|a| |t|a|ʁ|d|ɨ")]
    [InlineData("Brasil", "b|ʁ|a|z|i|ɫ")]
    [InlineData("dias", "dʒ|i|a|ʃ")]
    [InlineData("os amigos", "o|ʒ| |a|m|i|ɡ|o|ʃ")]
    [InlineData("cidade", "s|i|d|a|d|ɨ")]
    public void EuropeanPhonemizer_MatchesPython(string text, string expected)
    {
        var phonemizer = new EuropeanPortuguesePhonemizer(new PortugueseG2PEngine());

        Assert.Equal(PiperPhonemeConverter.MapSequence([.. expected.Split('|')]), phonemizer.Phonemize(text));
    }
}
