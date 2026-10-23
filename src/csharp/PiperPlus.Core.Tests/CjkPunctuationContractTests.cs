using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// CJK punctuation contract (Issue #823).
/// <para>
/// Reads <c>tests/fixtures/g2p/cjk_punctuation_cases.json</c>, which
/// <c>scripts/build_cjk_punctuation_fixture.py</c> builds from
/// <c>docs/spec/cjk-punctuation-contract.toml</c>. Every runtime has the same
/// test, so a detector or Latin-segment rewrite that drifts from the contract
/// fails in the runtime that drifted.
/// </para>
/// <para>
/// The phonemization checks run the real <see cref="ChinesePhonemizer"/>
/// (small pinyin dictionary) and echo phonemizers for the other languages:
/// the Latin G2P engines live in <c>PiperPlus.Cli</c>, and what matters here
/// is the text <see cref="MultilingualPhonemizer"/> hands to each of them.
/// </para>
/// </summary>
public sealed class CjkPunctuationContractTests
{
    private static readonly string[] Languages = ["en", "es", "fr", "ja", "ko", "pt", "sv", "zh"];

    private static readonly Lazy<Fixture> S_fixture = new(LoadFixture);

    private sealed record CodePoint(string Id, char Char, string? Latin);

    private sealed record Fixture(
        string[] DetectorLanguages,
        string DefaultLatin,
        List<CodePoint> Neutral,
        List<CodePoint> FullwidthLatin);

    /// <summary>Returns each character of the text as one token.</summary>
    private sealed class EchoPhonemizer : IPhonemizer
    {
        public List<string> Phonemize(string text) => text.Select(c => c.ToString()).ToList();

        public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
        {
            List<string> tokens = Phonemize(text);
            return (tokens, tokens.Select(_ => (ProsodyInfo?)null).ToList());
        }

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;
    }

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

    private static List<CodePoint> ReadCodePoints(JsonElement array) =>
        array.EnumerateArray()
            .Select(e => new CodePoint(
                e.GetProperty("code_point").GetString()!,
                e.GetProperty("char").GetString()!.Single(),
                e.TryGetProperty("latin", out JsonElement latin) ? latin.GetString() : null))
            .ToList();

    private static Fixture LoadFixture()
    {
        string path = Path.Join(RepoRoot(), "tests", "fixtures", "g2p", "cjk_punctuation_cases.json");
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path));
        JsonElement root = doc.RootElement;
        return new Fixture(
            root.GetProperty("detector_languages").EnumerateArray().Select(e => e.GetString()!).ToArray(),
            root.GetProperty("default_latin").GetString()!,
            ReadCodePoints(root.GetProperty("neutral")),
            ReadCodePoints(root.GetProperty("fullwidth_latin")));
    }

    private static UnicodeLanguageDetector MakeDetector(Fixture f) =>
        new(f.DetectorLanguages, f.DefaultLatin);

    private static MultilingualPhonemizer MakePhonemizer()
    {
        var engine = new PinyinDictionaryChineseG2PEngine(
            new Dictionary<int, string>
            {
                ['你'] = "ni3",
                ['好'] = "hao3",
                ['今'] = "jin1",
                ['天'] = "tian1",
                ['气'] = "qi4",
                ['很'] = "hen3",
                ['北'] = "bei3",
                ['京'] = "jing1",
                ['欢'] = "huan1",
                ['迎'] = "ying2",
            },
            new Dictionary<string, string[]>());
        Dictionary<string, IPhonemizer> phonemizers = Languages.ToDictionary(
            l => l,
            l => l == "zh" ? new ChinesePhonemizer(engine) : (IPhonemizer)new EchoPhonemizer());
        return new MultilingualPhonemizer(phonemizers, defaultLatinLanguage: "en");
    }

    [Fact]
    public void Fixture_IsNotEmpty()
    {
        Fixture f = S_fixture.Value;
        Assert.True(f.Neutral.Count > 100, $"too few neutral code points: {f.Neutral.Count}");
        Assert.Equal(52, f.FullwidthLatin.Count);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void NeutralCodePoints_BelongToNoLanguage(bool contextHasKana)
    {
        Fixture f = S_fixture.Value;
        UnicodeLanguageDetector detector = MakeDetector(f);

        List<string> wrong = f.Neutral
            .Select(c => (c.Id, Lang: detector.DetectChar(c.Char, contextHasKana)))
            .Where(r => r.Lang is not null)
            .Select(r => $"{r.Id} -> {r.Lang}")
            .ToList();

        Assert.Empty(wrong);
    }

    [Fact]
    public void FullwidthLatinLetters_StayLatin()
    {
        Fixture f = S_fixture.Value;
        UnicodeLanguageDetector detector = MakeDetector(f);

        List<string> wrong = f.FullwidthLatin
            .Where(c => detector.DetectChar(c.Char) != f.DefaultLatin)
            .Select(c => c.Id)
            .ToList();

        Assert.Empty(wrong);
    }

    [Fact]
    public void LatinSegmentRewrite_FollowsTheContract()
    {
        Fixture f = S_fixture.Value;

        List<string> wrong = f.Neutral
            .Select(c => (c.Id, Actual: MultilingualPhonemizer.NormalizeCjkPunctuationForLatin(c.Char.ToString()), Expected: c.Latin))
            .Where(r => r.Actual != r.Expected)
            .Select(r => $"{r.Id}: '{r.Actual}' (expected '{r.Expected}')")
            .ToList();

        Assert.Empty(wrong);
    }

    [Theory]
    [InlineData("Hello, world!")]
    [InlineData("café")]
    [InlineData("ＡＢＣ")]
    [InlineData("你好")]
    [InlineData("こんにちは")]
    [InlineData("")]
    public void LatinSegmentRewrite_LeavesOtherTextAlone(string text)
    {
        // The fullwidth Latin letters are left alone too.
        Assert.Equal(text, MultilingualPhonemizer.NormalizeCjkPunctuationForLatin(text));
    }

    [Fact]
    public void ChineseSentence_KeepsItsPunctuation()
    {
        MultilingualPhonemizer phonemizer = MakePhonemizer();

        List<string> tokens = phonemizer.Phonemize("你好，今天天气很好。");
        Assert.Equal(1, tokens.Count(t => t == ","));
        Assert.Equal(".", tokens[^1]);
        Assert.Equal(".", phonemizer.Phonemize("北京欢迎你。")[^1]);

        UnicodeLanguageDetector detector = new(Languages, "en");
        Assert.Equal(["zh"], detector.SegmentText("你好，今天天气很好。").Select(s => s.Lang));
    }

    [Fact]
    public void EnglishAfterChineseComma_IsReadAsALoanword()
    {
        // The ZH-EN dispatch needs the Chinese segment right before the English
        // one; a Japanese segment for "，" used to sit between them.
        MultilingualPhonemizer phonemizer = MakePhonemizer();

        List<string> withComma = phonemizer.Phonemize("你好，GPS");
        List<string> without = phonemizer.Phonemize("你好GPS");

        Assert.Equal(without, withComma.Where(t => t != ","));
    }

    [Theory]
    [InlineData("Hello，world", "Hello,world")]
    [InlineData("Hello、world。", "Hello,world.")]
    [InlineData("Hola，amigo！", "Hola,amigo!")]
    [InlineData("I have ３ cats．", "I have 3 cats.")]
    public void LatinTextWithCjkPunctuation_ReadsLikeAscii(string cjk, string asciiText)
    {
        // The Latin G2P deletes characters it does not know, which used to
        // join "Hello，world" into one word.
        MultilingualPhonemizer phonemizer = MakePhonemizer();

        Assert.Equal(phonemizer.Phonemize(asciiText), phonemizer.Phonemize(cjk));
    }
}
