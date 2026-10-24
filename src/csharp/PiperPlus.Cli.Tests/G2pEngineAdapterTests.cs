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
}
