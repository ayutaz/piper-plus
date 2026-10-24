using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="SpanishG2PEngine"/>. The expected tokens are the
/// output of Python <c>phonemize_spanish()</c> (spanish.py) for the same input;
/// the full comparison with the Python golden is in PiperPlus.Cli.Tests
/// (G2pGoldenParityTests).
/// </summary>
public sealed class SpanishG2PEngineTests
{
    /// <summary>
    /// The trill rr (doubled, word-initial, after n), the β/ð/ɣ fricatives
    /// between vowels, the stress mark right before the stressed vowel (accent
    /// mark or the vowel / n / s ending rule), no stress on function words,
    /// gü + e/i as ɡw, x as ks, word-final y as i, and punctuation kept as
    /// tokens without a space before it (a space precedes every word but the
    /// first, even after an opening ¿).
    /// </summary>
    [Theory]
    [InlineData("casa", "k|ˈ|a|s|a")]
    [InlineData("hasta", "ˈ|a|s|t|a")]
    [InlineData("Hola", "ˈ|o|l|a")]
    [InlineData("perro grande", "p|ˈ|e|rr|o| |ɡ|ɾ|ˈ|a|n|d|e")]
    [InlineData("¿Cómo estás?", "¿|k|ˈ|o|m|o| |e|s|t|ˈ|a|s|?")]
    [InlineData("hola ¿qué?", "ˈ|o|l|a|¿| |k|ˈ|e|?")]
    [InlineData("guerra", "ɡ|ˈ|e|rr|a")]
    [InlineData("el gato", "e|l| |ɡ|ˈ|a|t|o")]
    [InlineData("todo", "t|ˈ|o|ð|o")]
    [InlineData("llave", "ʝ|ˈ|a|β|e")]
    [InlineData("discípulo", "d|i|s|ˈ|i|p|u|l|o")]
    [InlineData("enrique honra rosa", "e|n|rr|ˈ|i|k|e| |ˈ|o|n|rr|a| |rr|ˈ|o|s|a")]
    [InlineData("pingüino", "p|i|n|ɡ|w|ˈ|i|n|o")]
    [InlineData("excelente", "e|k|s|e|ˈ|l|e|n|t|e")]
    [InlineData("Muchas gracias", "m|ˈ|u|tʃ|a|s| |ɡ|ɾ|ˈ|a|s|i|a|s")]
    [InlineData("niño", "n|ˈ|i|ɲ|o")]
    [InlineData("rey", "rr|ˈ|e|i")]
    public void ToPhonemeList_MatchesPython(string text, string expected)
    {
        var engine = new SpanishG2PEngine();

        Assert.Equal(expected.Split('|'), engine.ToPhonemeList(text));
    }

    /// <summary>
    /// Characters outside the Spanish letters and <c>,.;:!?¡¿</c> are dropped,
    /// so digits produce nothing (Python does not expand numbers either).
    /// </summary>
    [Theory]
    [InlineData("0")]
    [InlineData("100")]
    [InlineData("")]
    [InlineData("   ")]
    public void ToPhonemeList_NoSpanishLetters_ReturnsEmpty(string text)
    {
        var engine = new SpanishG2PEngine();

        Assert.Empty(engine.ToPhonemeList(text));
    }

    [Fact]
    public void ToPhonemeList_DigitsAroundPunctuation_KeepOnlyThePunctuation()
    {
        var engine = new SpanishG2PEngine();

        Assert.Equal(["."], engine.ToPhonemeList("3.14"));
    }

    /// <summary>
    /// Through <see cref="SpanishPhonemizer"/>, the stress mark and the vowel
    /// after it get A2=2 and every phoneme of a word gets the word's phoneme
    /// count (without the mark) as A3, like Python's
    /// <c>phonemize_spanish_with_prosody()</c>.
    /// </summary>
    [Fact]
    public void Phonemizer_StressedVowelProsody_MatchesPython()
    {
        var phonemizer = new SpanishPhonemizer(new SpanishG2PEngine());

        (List<string> tokens, List<ProsodyInfo?> prosody) = phonemizer.PhonemizeWithProsody("casa");

        Assert.Equal(["k", "ˈ", "a", "s", "a"], tokens);
        Assert.Equal([0, 2, 2, 0, 0], prosody.Select(p => p!.Value.A2));
        Assert.All(prosody, p => Assert.Equal(4, p!.Value.A3));
    }
}
