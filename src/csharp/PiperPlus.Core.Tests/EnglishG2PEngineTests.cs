using System.IO;
using System.Linq;
using System.Text;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="EnglishG2PEngine"/>, the port of the C++ / Rust /
/// Go English G2P (g2p_en's normalization, the CMU dictionary and the
/// fallbacks for words missing from it). Most cases use a small dictionary and
/// follow the Rust tests in <c>src/rust/piper-plus-g2p/src/english.rs</c>;
/// the full comparison with the Python golden is in PiperPlus.Cli.Tests
/// (G2pGoldenParityTests).
/// </summary>
public sealed class EnglishG2PEngineTests
{
    private static EnglishPhonemizer Phonemizer(params (string Word, string Arpabet)[] entries) =>
        new(Engine(entries));

    private static EnglishG2PEngine Engine(params (string Word, string Arpabet)[] entries) =>
        new(entries.ToDictionary(e => e.Word, e => e.Arpabet));

    /// <summary>Splits a space-joined phoneme string; "_" is the word boundary " ".</summary>
    private static List<string> Tokens(string s) =>
        s.Split(' ').Select(t => t == "_" ? " " : t).ToList();

    private static List<string> Words(List<List<string>> groups) =>
        groups.Select(g => string.Join(" ", g)).ToList();

    private static string RepoRoot()
    {
        DirectoryInfo? d = new(AppContext.BaseDirectory);
        for (int i = 0; i < 8 && d is not null; i++)
        {
            if (Directory.Exists(Path.Join(d.FullName, "tests", "fixtures", "g2p")))
            {
                return d.FullName;
            }

            d = d.Parent;
        }

        throw new DirectoryNotFoundException(
            "Could not locate repo root from " + AppContext.BaseDirectory);
    }

    private static readonly Lazy<EnglishG2PEngine> S_realEngine = new(() =>
    {
        using FileStream stream = File.OpenRead(
            Path.Join(RepoRoot(), "src", "rust", "piper-plus-g2p", "data", "cmudict_data.json"));
        return EnglishG2PEngine.FromJson(stream);
    });

    // ================================================================
    // Dictionary and normalization
    // ================================================================
    [Fact]
    public void ConvertToArpabet_LooksUpWordsIgnoringCase()
    {
        EnglishG2PEngine engine = Engine(("hello", "HH AH0 L OW1"), ("world", "W ER1 L D"));

        Assert.Equal(["HH AH0 L OW1", ",", "W ER1 L D", "!"], Words(engine.ConvertToArpabet("Hello, WORLD!")));
    }

    [Fact]
    public void ConvertToArpabet_DropsCharactersOutsideTheFilter()
    {
        // g2p_en removes characters outside [a-z'.,?!-] before tokenizing.
        EnglishG2PEngine engine = Engine(("quoted", "K W OW1 T IH0 D"), ("text", "T EH1 K S T"));

        Assert.Equal(Words(engine.ConvertToArpabet("quoted text")), Words(engine.ConvertToArpabet("\"quoted\" text")));
    }

    [Fact]
    public void ConvertToArpabet_FoldsAccentsAndExpandsNumbersAndAbbreviations()
    {
        EnglishPhonemizer p = Phonemizer(
            ("cafe", "K AH0 F EY1"),
            ("for", "F AO1 R"),
            ("example", "IH0 G Z AE1 M P AH0 L"),
            ("one", "W AH1 N"),
            ("hundred", "HH AH1 N D R AH0 D"));

        Assert.Equal(Tokens("k ə f ˈ e ɪ"), p.Phonemize("café"));
        Assert.Equal(Tokens("f ˈ ɔ ː ɹ _ ɪ ɡ z ˈ æ m p ə l"), p.Phonemize("e.g."));
        Assert.Equal(Tokens("w ˈ ʌ n _ h ˈ ʌ n d ɹ ə d"), p.Phonemize("100"));
    }

    [Fact]
    public void ConvertToArpabet_KeepsWordsWithoutLettersAsTheyAre()
    {
        // A word without a letter ("-", "'", ". . .") is kept, one phoneme per
        // character; only , . ; : ! ? attach to the preceding word.
        EnglishPhonemizer p = Phonemizer(("wait", "W EY1 T"), ("now", "N AW1"), ("quote", "K W OW1 T"));

        (List<string> tokens, List<ProsodyInfo?> prosody) = p.PhonemizeWithProsody("wait . . . now");
        Assert.Equal(Tokens("w ˈ e ɪ t _ . _ . _ . _ n ˈ a ʊ"), tokens);
        Assert.Equal([4, 4, 4, 4, 4, 0, 5, 5, 5, 5, 5, 0, 3, 3, 3, 3], prosody.Select(x => x!.Value.A3));
        Assert.Equal(Tokens("' _ k w ˈ o ʊ t _ '"), p.Phonemize("'quote'"));
    }

    [Fact]
    public void PunctuationProsody_CountsTheCharacter()
    {
        // Python counts the punctuation character itself: a3 = 1.
        EnglishPhonemizer p = Phonemizer(("hello", "HH AH0 L OW1"));

        (List<string> tokens, List<ProsodyInfo?> prosody) = p.PhonemizeWithProsody("hello,");
        Assert.Equal(",", tokens[^1]);
        Assert.Equal<ProsodyInfo?>(new ProsodyInfo(0, 0, 1), prosody[^1]);
    }

    [Fact]
    public void FunctionWords_AlignWithSourceWordsBeforeNumberExpansion()
    {
        // Python: the source words of "the 3 of us" are [the, of, us], aligned
        // with the spoken words [the, three, of, us]. "three" takes "of" and
        // "of" takes "us", so both lose their stress and "us" keeps it.
        EnglishPhonemizer p = Phonemizer(("the", "DH AH0"), ("three", "TH R IY1"), ("of", "AH1 V"), ("us", "AH1 S"));

        (List<string> tokens, List<ProsodyInfo?> prosody) = p.PhonemizeWithProsody("the 3 of us");
        Assert.Equal(Tokens("ð ə _ θ ɹ i ː _ ʌ v _ ˈ ʌ s"), tokens);
        Assert.Equal([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0], prosody.Select(x => x!.Value.A2));
        Assert.Equal([2, 2, 0, 4, 4, 4, 4, 0, 2, 2, 0, 2, 2, 2], prosody.Select(x => x!.Value.A3));
    }

    [Theory]
    [InlineData("hello\tworld")]
    [InlineData("hello\nworld")]
    [InlineData("hello\r\nworld")]
    [InlineData("hello world")]
    public void Whitespace_SeparatesWordsLikeASpace(string text)
    {
        // g2p_en removes tabs and newlines, joining the words around them into
        // one it reads with its neural predictor, which is not ported.
        EnglishPhonemizer p = Phonemizer(("hello", "HH AH0 L OW1"), ("world", "W ER1 L D"));

        Assert.Equal(p.Phonemize("hello world"), p.Phonemize(text));
    }

    [Theory]
    [InlineData("xyz hello")]
    [InlineData("'quote'")]
    [InlineData("...hello")]
    [InlineData("  hello")]
    [InlineData("3 hello")]
    public void Output_NeverStartsWithAWordBoundary(string text)
    {
        EnglishPhonemizer p = Phonemizer(("hello", "HH AH0 L OW1"));

        Assert.NotEqual(" ", p.Phonemize(text).FirstOrDefault());
    }

    [Fact]
    public void EmptyText_GivesNoWord()
    {
        Assert.Empty(Engine().ConvertToArpabet(string.Empty));
    }

    // ================================================================
    // Morphological fallback (C++ tryMorphologicalFallback)
    // ================================================================
    [Theory]
    [InlineData("cats", "cat", "K AE1 T", "K AE1 T Z")]
    [InlineData("boxes", "box", "B AA1 K S", "B AA1 K S IH0 Z")]
    [InlineData("countries", "country", "K AH1 N T R IY0", "K AH1 N T R IY0 Z")]
    [InlineData("running", "run", "R AH1 N", "R AH1 N IH0 NG")]
    [InlineData("making", "make", "M EY1 K", "M EY1 K IH0 NG")]
    [InlineData("walked", "walk", "W AO1 K", "W AO1 K D")]
    [InlineData("stopped", "stop", "S T AA1 P", "S T AA1 P D")]
    [InlineData("loved", "love", "L AH1 V", "L AH1 V D")]
    [InlineData("runner", "run", "R AH1 N", "R AH1 N ER0")]
    [InlineData("quickly", "quick", "K W IH1 K", "K W IH1 K L IY0")]
    [InlineData("happily", "happy", "HH AE1 P IY0", "HH AE1 P IY0 L IY0")]
    [InlineData("fastest", "fast", "F AE1 S T", "F AE1 S T AH0 S T")]
    public void MissingWord_IsReadFromItsStem(string word, string stem, string stemArpabet, string expected)
    {
        EnglishG2PEngine engine = Engine((stem, stemArpabet));

        Assert.Equal([expected], Words(engine.ConvertToArpabet(word)));
    }

    // ================================================================
    // Words missing from the dictionary are never dropped
    // ================================================================
    [Fact]
    public void MissingWord_IsSpelledAsOneWord()
    {
        EnglishPhonemizer p = Phonemizer(("hello", "HH AH0 L OW1"));

        // x = EH1 K S, y = W AY1, z = Z IY1, read as one word.
        Assert.Equal(Tokens("h ə l ˈ o ʊ _ ˈ ɛ k s w ˈ a ɪ z ˈ i ː"), p.Phonemize("hello xyz"));
        Assert.Equal(Tokens("t ˈ i ː t ˈ i ː ˈ ɛ s"), Phonemizer().Phonemize("TTS"));
    }

    [Fact]
    public void LetterNames_CoverTheAlphabet()
    {
        string[] names =
        [
            "EY1", "B IY1", "S IY1", "D IY1", "IY1", "EH1 F", "JH IY1", "EY1 CH", "AY1",
            "JH EY1", "K EY1", "EH1 L", "EH1 M", "EH1 N", "OW1", "P IY1", "K Y UW1", "AA1 R",
            "EH1 S", "T IY1", "Y UW1", "V IY1", "D AH1 B AH0 L Y UW0", "EH1 K S", "W AY1", "Z IY1",
        ];
        EnglishG2PEngine engine = Engine();

        for (int i = 0; i < 26; i++)
        {
            string lower = ((char)('a' + i)).ToString();
            Assert.Equal([names[i]], Words(engine.ConvertToArpabet(lower)));
            Assert.Equal([names[i]], Words(engine.ConvertToArpabet(lower.ToUpperInvariant())));
        }
    }

    [Fact]
    public void MissingWord_IsSplitAtCamelCase()
    {
        EnglishPhonemizer p = Phonemizer(("chat", "CH AE1 T"), ("phone", "F OW1 N"), ("i", "AY1"));

        // Chat + G P T (spelled), with no word boundary in between.
        Assert.Equal(Tokens("t ʃ ˈ æ t d ʒ ˈ i ː p ˈ i ː t ˈ i ː"), p.Phonemize("ChatGPT"));

        // i (dictionary) + Phone.
        Assert.Equal(Tokens("ˈ a ɪ f ˈ o ʊ n"), p.Phonemize("iPhone"));
    }

    [Theory]
    [InlineData("ChatGPT", "Chat|GPT")]
    [InlineData("iPhone", "i|Phone")]
    [InlineData("GitHub", "Git|Hub")]
    [InlineData("MixedCase", "Mixed|Case")]
    [InlineData("HTMLParser", "HTML|Parser")]
    [InlineData("RtwoDtwo", "Rtwo|Dtwo")]
    [InlineData("UPPERCASE", "UPPERCASE")]
    [InlineData("lower", "lower")]
    [InlineData("A", "A")]
    public void SplitCamelCase_MatchesPythonRegex(string word, string expected)
    {
        Assert.Equal(expected.Split('|'), EnglishG2PEngine.SplitCamelCase(word));
    }

    [Fact]
    public void MissingWord_IsSplitAtHyphensAndDots()
    {
        EnglishPhonemizer p = Phonemizer(("foo", "F UW1"), ("bar", "B AA1 R"));

        List<string> expected = Tokens("f ˈ u ː b ˈ ɑ ː ɹ");
        Assert.Equal(expected, p.Phonemize("foo-bar"));

        // "foo.bar" is one token (TweetTokenizer domain form).
        Assert.Equal(expected, p.Phonemize("foo.bar"));
    }

    [Fact]
    public void HyphenatedDictionaryWord_IsNotSplit()
    {
        EnglishPhonemizer p = Phonemizer(("uh-huh", "AH1 HH AH1"), ("uh", "AH1"), ("huh", "HH AH1"));

        Assert.Equal(Tokens("ˈ ʌ h ˈ ʌ"), p.Phonemize("uh-huh"));
    }

    [Fact]
    public void MissingWord_IsRetriedWithoutApostrophes()
    {
        Assert.Equal(
            Tokens("ɹ ˈ ɑ k n ɹ ˈ o ʊ l"),
            Phonemizer(("rocknroll", "R AA1 K N R OW1 L")).Phonemize("rock'n'roll"));

        // Not found without the apostrophe either: spell the letters.
        Assert.Equal(Tokens("ˈ ɛ k s w ˈ a ɪ"), Phonemizer().Phonemize("x'y"));
    }

    [Theory]
    [InlineData("ChatGPT")]
    [InlineData("TTS")]
    [InlineData("xyz")]
    [InlineData("aaaaa")]
    [InlineData("UPPERCASE")]
    [InlineData("MixedCase")]
    [InlineData("iPhone")]
    [InlineData("GitHub")]
    [InlineData("COVID-19")]
    [InlineData("R2D2")]
    [InlineData("'90s")]
    public void RealDictionary_NeverDropsAWord(string word)
    {
        var p = new EnglishPhonemizer(S_realEngine.Value);

        (List<string> tokens, List<ProsodyInfo?> prosody) = p.PhonemizeWithProsody(word);
        string[] silent = [" ", ".", ",", "!", "?", ";", ":", "'", "\"", "-"];
        Assert.Contains(tokens, t => !silent.Contains(t));
        Assert.NotEqual(" ", tokens[0]);
        Assert.Equal(tokens.Count, prosody.Count);
    }

    [Fact]
    public void FromJson_SkipsNonStringValues()
    {
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes("{\"cat\":\"K AE1 T\",\"bad\":1}"));
        EnglishG2PEngine engine = EnglishG2PEngine.FromJson(stream);

        Assert.Equal(["K AE1 T"], Words(engine.ConvertToArpabet("cat")));
        Assert.Equal(["B IY1 EY1 D IY1"], Words(engine.ConvertToArpabet("bad")));
    }
}
