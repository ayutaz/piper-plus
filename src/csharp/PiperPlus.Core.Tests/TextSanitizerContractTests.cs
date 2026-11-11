using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Control characters are stripped before a text is read.
/// <para>
/// Contract: <c>docs/spec/input-sanitize-contract.toml</c> (runtime
/// <c>csharp</c>). Cases: <c>tests/fixtures/g2p/input_sanitize_cases.json</c>,
/// read by every runtime.
/// </para>
/// <para>
/// Regression focus: #934 (2026-11) stripped control characters in the
/// Python G2P only. Here a NUL inside "hola" split the word in two, and the
/// Japanese phonemizer took the question type from the raw text, so
/// "本当?" followed by a NUL ended as a statement.
/// </para>
/// </summary>
public sealed class TextSanitizerContractTests
{
    private sealed record StripCase(string Name, string Input, string Expected);

    public sealed record TextCase(string Language, string Control, string Clean, string Dirty)
    {
        public override string ToString() => $"{Language} {Control} {Clean}";
    }

    private static readonly Lazy<(List<StripCase> Strip, List<TextCase> Words)> S_cases = new(LoadCases);

    internal static string RepoRoot()
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

        throw new DirectoryNotFoundException("Could not locate repo root from " + AppContext.BaseDirectory);
    }

    private static (List<StripCase> Strip, List<TextCase> Words) LoadCases()
    {
        string path = Path.Join(RepoRoot(), "tests", "fixtures", "g2p", "input_sanitize_cases.json");
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path));
        List<StripCase> strip = doc.RootElement.GetProperty("strip_cases").EnumerateArray()
            .Select(e => new StripCase(
                e.GetProperty("name").GetString()!,
                e.GetProperty("input").GetString()!,
                e.GetProperty("expected").GetString()!))
            .ToList();
        List<TextCase> words = doc.RootElement.GetProperty("word_cases").EnumerateArray()
            .Select(e => new TextCase(
                e.GetProperty("language").GetString()!,
                e.GetProperty("control").GetString()!,
                e.GetProperty("clean").GetString()!,
                e.GetProperty("dirty").GetString()!))
            .ToList();
        Assert.NotEmpty(strip);
        Assert.NotEmpty(words);
        return (strip, words);
    }

    public static TheoryData<TextCase> WordCases()
    {
        var data = new TheoryData<TextCase>();
        foreach (TextCase c in S_cases.Value.Words)
        {
            data.Add(c);
        }

        return data;
    }

    private static string OnlyControls => S_cases.Value.Strip.Single(c => c.Name == "only_controls").Input;

    [Fact]
    public void StripControlChars_MatchesEveryStripCase()
    {
        foreach (StripCase c in S_cases.Value.Strip)
        {
            Assert.True(
                string.Equals(TextSanitizer.StripControlChars(c.Input), c.Expected, StringComparison.Ordinal),
                $"{c.Name}: got \"{TextSanitizer.StripControlChars(c.Input)}\"");
        }
    }

    [Fact]
    public void StripControlChars_IsIdempotent()
    {
        foreach (StripCase c in S_cases.Value.Strip)
        {
            string once = TextSanitizer.StripControlChars(c.Input);
            Assert.Equal(once, TextSanitizer.StripControlChars(once));
        }
    }

    [Fact]
    public void StripControlChars_KeepsLoneSurrogates()
    {
        // Only control characters change; a lone surrogate is not one.
        Assert.Equal("a\uD800b", TextSanitizer.StripControlChars("a\uD800b\u0000"));
    }

    [Fact]
    public void StripControlChars_ReturnsTheSameStringWhenClean()
    {
        string clean = "hola\nadiós";
        Assert.Same(clean, TextSanitizer.StripControlChars(clean));
    }

    /// <summary>Records each text the phonemizer hands to its engine.</summary>
    private sealed class Recorder
    {
        public List<string> Texts { get; } = [];

        public List<string> Take()
        {
            List<string> copy = [.. Texts];
            Texts.Clear();
            return copy;
        }
    }

    private sealed class RecordingJapaneseEngine(Recorder r) : IJapaneseG2PEngine
    {
        public G2PResult Convert(string text)
        {
            r.Texts.Add(text);
            return new G2PResult(["sil", "k", "a", "sil"], [0, -1, 0, 0], [0, 1, 2, 0], [0, 2, 2, 0]);
        }
    }

    private sealed class RecordingEnglishEngine(Recorder r) : IEnglishG2PEngine
    {
        public List<List<string>> ConvertToArpabet(string text)
        {
            r.Texts.Add(text);
            return [["HH", "AH0"]];
        }
    }

    private sealed class RecordingChineseEngine(Recorder r) : IChineseG2PEngine
    {
        public ChineseG2PResult Convert(string text)
        {
            r.Texts.Add(text);
            return new ChineseG2PResult(["n", "i"], [3, 3], [1, 1], [1, 1]);
        }
    }

    private sealed class RecordingKoreanEngine(Recorder r) : IKoreanG2PEngine
    {
        public KoreanG2PResult Convert(string text)
        {
            r.Texts.Add(text);
            return new KoreanG2PResult(["a"], [0], [0], [0]);
        }
    }

    private sealed class RecordingLatinEngine(Recorder r)
        : ISpanishG2PEngine, IFrenchG2PEngine, IPortugueseG2PEngine, ISwedishG2PEngine
    {
        public List<string> ToPhonemeList(string text)
        {
            r.Texts.Add(text);
            return ["a"];
        }
    }

    /// <summary>
    /// Every public phonemizer of PiperPlus.Core, built on recording engines.
    /// A new phonemizer type fails <see cref="EveryPhonemizerType_IsListed"/>
    /// until it is added here, so it cannot skip these tests.
    /// </summary>
    private static readonly Dictionary<Type, Func<Recorder, IPhonemizer>> S_factories = new()
    {
        [typeof(JapanesePhonemizer)] = r => new JapanesePhonemizer(new RecordingJapaneseEngine(r)),
        [typeof(EnglishPhonemizer)] = r => new EnglishPhonemizer(new RecordingEnglishEngine(r)),
        [typeof(ChinesePhonemizer)] = r => new ChinesePhonemizer(new RecordingChineseEngine(r)),
        [typeof(KoreanPhonemizer)] = r => new KoreanPhonemizer(new RecordingKoreanEngine(r)),
        [typeof(SpanishPhonemizer)] = r => new SpanishPhonemizer(new RecordingLatinEngine(r)),
        [typeof(FrenchPhonemizer)] = r => new FrenchPhonemizer(new RecordingLatinEngine(r)),
        [typeof(PortuguesePhonemizer)] = r => new PortuguesePhonemizer(new RecordingLatinEngine(r)),
        [typeof(EuropeanPortuguesePhonemizer)] = r => new EuropeanPortuguesePhonemizer(new RecordingLatinEngine(r)),
        [typeof(SwedishPhonemizer)] = r => new SwedishPhonemizer(new RecordingLatinEngine(r)),
        [typeof(MultilingualPhonemizer)] = r => new MultilingualPhonemizer(
            new Dictionary<string, IPhonemizer>
            {
                ["ja"] = new JapanesePhonemizer(new RecordingJapaneseEngine(r)),
                ["en"] = new EnglishPhonemizer(new RecordingEnglishEngine(r)),
                ["zh"] = new ChinesePhonemizer(new RecordingChineseEngine(r)),
                ["ko"] = new KoreanPhonemizer(new RecordingKoreanEngine(r)),
                ["es"] = new SpanishPhonemizer(new RecordingLatinEngine(r)),
            },
            defaultLatinLanguage: "es"),
    };

    [Fact]
    public void EveryPhonemizerType_IsListed()
    {
#pragma warning disable IL2026 // the tests are not trimmed
        List<Type> types = typeof(IPhonemizer).Assembly.GetTypes()
            .Where(t => t.IsClass && !t.IsAbstract && typeof(IPhonemizer).IsAssignableFrom(t))
            .ToList();
#pragma warning restore IL2026
        Assert.True(types.Count >= 10, $"found only {types.Count} phonemizer types");
        List<string> missing = types.Where(t => !S_factories.ContainsKey(t)).Select(t => t.Name).ToList();
        Assert.True(missing.Count == 0, "not in S_factories: " + string.Join(", ", missing));
    }

    public static TheoryData<string, TextCase> PhonemizerCases()
    {
        var data = new TheoryData<string, TextCase>();
        foreach (Type type in S_factories.Keys)
        {
            foreach (TextCase c in S_cases.Value.Words)
            {
                data.Add(type.Name, c);
            }
        }

        return data;
    }

    private static Func<Recorder, IPhonemizer> Factory(string typeName) =>
        S_factories.Single(kv => kv.Key.Name == typeName).Value;

    [Theory]
    [MemberData(nameof(PhonemizerCases))]
    public void Phonemizer_ReadsDirtyLikeClean(string typeName, TextCase c)
    {
        var recorder = new Recorder();
        IPhonemizer p = Factory(typeName)(recorder);

        List<string> dirtyTokens = p.Phonemize(c.Dirty);
        List<string> dirtyTexts = recorder.Take();
        List<string> cleanTokens = p.Phonemize(c.Clean);
        List<string> cleanTexts = recorder.Take();
        Assert.Equal(cleanTexts, dirtyTexts);
        Assert.Equal(cleanTokens, dirtyTokens);

        (List<string> dirtyProsodyTokens, List<ProsodyInfo?> dirtyProsody) = p.PhonemizeWithProsody(c.Dirty);
        dirtyTexts = recorder.Take();
        (List<string> cleanProsodyTokens, List<ProsodyInfo?> cleanProsody) = p.PhonemizeWithProsody(c.Clean);
        cleanTexts = recorder.Take();
        Assert.Equal(cleanTexts, dirtyTexts);
        Assert.Equal(cleanProsodyTokens, dirtyProsodyTokens);
        Assert.Equal(cleanProsody, dirtyProsody);
    }

    [Fact]
    public void Phonemizer_ReadsOnlyControlsLikeEmptyText()
    {
        foreach (Func<Recorder, IPhonemizer> factory in S_factories.Values)
        {
            var recorder = new Recorder();
            IPhonemizer p = factory(recorder);
            List<string> dirty = p.Phonemize(OnlyControls);
            List<string> dirtyTexts = recorder.Take();
            Assert.Equal(p.Phonemize(string.Empty), dirty);
            Assert.Equal(recorder.Take(), dirtyTexts);
        }
    }

    private static IPhonemizer RealPhonemizer(string language)
    {
        var pinyin = new PinyinDictionaryChineseG2PEngine(
            new Dictionary<int, string> { ['你'] = "ni3", ['好'] = "hao3", ['我'] = "wo3", ['用'] = "yong4" },
            new Dictionary<string, string[]>());
        EnglishG2PEngine english;
        using (FileStream stream = File.OpenRead(
            Path.Join(RepoRoot(), "src", "rust", "piper-plus-g2p", "data", "cmudict_data.json")))
        {
            english = EnglishG2PEngine.FromJson(stream);
        }

        return language switch
        {
            "en" => new EnglishPhonemizer(english),
            "zh" => new ChinesePhonemizer(pinyin),
            "es" => new SpanishPhonemizer(new SpanishG2PEngine()),
            "fr" => new FrenchPhonemizer(new FrenchG2PEngine()),
            "pt" => new PortuguesePhonemizer(new PortugueseG2PEngine()),
            "pt-PT" => new EuropeanPortuguesePhonemizer(new PortugueseG2PEngine()),
            "sv" => new SwedishPhonemizer(new SwedishG2PEngine()),
            "multilingual" => new MultilingualPhonemizer(
                new Dictionary<string, IPhonemizer>
                {
                    ["en"] = new EnglishPhonemizer(english),
                    ["es"] = new SpanishPhonemizer(new SpanishG2PEngine()),
                    ["zh"] = new ChinesePhonemizer(pinyin),
                },
                defaultLatinLanguage: "en"),
            _ => throw new ArgumentException(language),
        };
    }

    [Theory]
    [MemberData(nameof(WordCases))]
    public void RealEngine_ReadsDirtyLikeClean(TextCase c)
    {
        if (c.Language is "ja" or "ko")
        {
            return; // OpenJTalk / g2pk engines live in PiperPlus.Cli; covered above with recording engines.
        }

        IPhonemizer p = RealPhonemizer(c.Language);
        (List<string> dirtyTokens, List<ProsodyInfo?> dirtyProsody) = p.PhonemizeWithProsody(c.Dirty);
        (List<string> cleanTokens, List<ProsodyInfo?> cleanProsody) = p.PhonemizeWithProsody(c.Clean);
        Assert.Equal(cleanTokens, dirtyTokens);
        Assert.Equal(cleanProsody, dirtyProsody);
    }

    /// <summary>A third-party phonemizer that strips nothing itself.</summary>
    private sealed class RecordingPhonemizer : IPhonemizer
    {
        public List<string> Texts { get; } = [];

        public List<string> Phonemize(string text) => PhonemizeWithProsody(text).Tokens;

        public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
        {
            Texts.Add(text);
            return (["a"], [null]);
        }

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;
    }

    [Theory]
    [MemberData(nameof(WordCases))]
    public void PhonemeEncoder_StripsBeforeAnyPhonemizer(TextCase c)
    {
        var p = new RecordingPhonemizer();
        var map = new Dictionary<string, int[]> { ["a"] = [1] };
        PhonemeEncoder.Encode(p, c.Dirty, map);
        PhonemeEncoder.EncodeDirect(p, c.Dirty, map);
        Assert.Equal([c.Clean, c.Clean], p.Texts);
    }

    /// <summary>
    /// The English run between Chinese text is read as pinyin, as in the
    /// Python and Rust G2P. A NUL inside "Python" split it into two tokens,
    /// and the letters were spelled out one by one.
    /// </summary>
    [Theory]
    [InlineData("Py\u0000thon")]
    [InlineData("\u0007Python\u001b")]
    [InlineData("Pyth\u009fon")]
    public void ChineseEmbeddedEnglish_ReadsDirtyLikeClean(string dirty)
    {
        ChineseG2PResult clean = ChineseEmbeddedEnglish.Convert("Python");
        Assert.NotEmpty(clean.Phonemes);
        ChineseG2PResult got = ChineseEmbeddedEnglish.Convert(dirty);
        Assert.Equal(clean.Phonemes, got.Phonemes);
        Assert.Equal(clean.A1, got.A1);
    }
}
