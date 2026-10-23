using System.Collections.Generic;
using System.Linq;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// The CLI's adapters around DotNetG2P must hand the phonemizers tokens in
/// the form their engine interfaces promise (and Python produces); found by
/// <see cref="G2pGoldenParityTests"/>.
/// </summary>
public class G2pEngineAdapterTests
{
    private static List<string> Words(List<List<string>> groups) =>
        groups.Select(g => string.Join(" ", g)).ToList();

    [Fact]
    public void English_SplitsPunctuationOffWords()
    {
        // LookupWord("Hello,") finds nothing, so the word used to be passed
        // through as raw letters "H e l l o ,".
        var engine = new DotNetEnglishG2PEngine();

        Assert.Equal(
            [.. Words(engine.ConvertToArpabet("Hello")), ",", .. Words(engine.ConvertToArpabet("world")), "!"],
            Words(engine.ConvertToArpabet("Hello, world!")));
    }

    [Fact]
    public void English_DropsDoubleQuotes()
    {
        // g2p_en removes characters outside [a-z'.,?!-] before tokenizing.
        var engine = new DotNetEnglishG2PEngine();

        Assert.Equal(
            Words(engine.ConvertToArpabet("quoted text")),
            Words(engine.ConvertToArpabet("\"quoted\" text")));
    }

    [Fact]
    public void English_FoldsAccentsBeforeLookup()
    {
        // g2p_en folds accents (unidecode), so "café" is looked up as "cafe".
        var engine = new DotNetEnglishG2PEngine();

        Assert.Equal(
            Words(engine.ConvertToArpabet("cafe")),
            Words(engine.ConvertToArpabet("café")));
    }

    [Fact]
    public void English_ExpandsLatinAbbreviations()
    {
        // g2p_en replaces "i.e." and "e.g." before tokenizing.
        var engine = new DotNetEnglishG2PEngine();

        Assert.Equal(
            Words(engine.ConvertToArpabet("for example and that is")),
            Words(engine.ConvertToArpabet("e.g. and i.e.")));
    }

    [Fact]
    public void French_ReturnsYVowelToken()
    {
        // IFrenchG2PEngine promises "y_vowel" for [y]; a bare "y" is the
        // Japanese glide in the phoneme_id_map.
        var engine = new DotNetFrenchG2PEngine();

        Assert.Equal(["t", "y_vowel"], engine.ToPhonemeList("tu"));
    }

    [Fact]
    public void Portuguese_KeepsAffricatesWhole()
    {
        // DotNetG2P.Portuguese writes the tie bar (d͡ʒ); without removing it
        // the tokenizer emitted "d͡" + "ʒ", and "d͡" is not in the map.
        var engine = new DotNetPortugueseG2PEngine();

        List<string> dia = engine.ToPhonemeList("dia");
        List<string> noite = engine.ToPhonemeList("noite");

        Assert.Contains("d\u0292", dia);
        Assert.Contains("t\u0283", noite);
        Assert.DoesNotContain(dia.Concat(noite), t => t.Contains('\u0361'));
    }

    [Fact]
    public void Portuguese_ComposesNasalVowels()
    {
        // IPortugueseG2PEngine promises NFC nasal vowels (U+0129), which
        // is how the phoneme_id_map spells them; "i" + U+0303 is not in it.
        var engine = new DotNetPortugueseG2PEngine();

        List<string> sim = engine.ToPhonemeList("sim");

        Assert.Contains("\u0129", sim);
        Assert.DoesNotContain(sim, t => t.Contains('\u0303'));
    }

    [Fact]
    public void Spanish_PutsStressBeforeTheVowel()
    {
        // DotNetG2P.Spanish marks stress at the start of the syllable
        // ("ˈkasa"); Python, and SpanishPhonemizer's A2 rule ("the vowel
        // immediately after ˈ"), put it right before the stressed vowel.
        var engine = new DotNetSpanishG2PEngine();

        Assert.Equal(["k", "\u02C8", "a", "s", "a"], engine.ToPhonemeList("casa"));
        Assert.Equal(["\u02C8", "a", "s", "t", "a"], engine.ToPhonemeList("hasta"));
    }
}
