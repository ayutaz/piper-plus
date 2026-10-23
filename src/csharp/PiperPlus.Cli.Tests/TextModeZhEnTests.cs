using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// <c>--language zh</c> reads the English letters in a Chinese sentence as
/// Mandarin pinyin (ZH-EN loanword reading, Issue #384), like Python's
/// <c>MultilingualPhonemizer</c> and <c>--language zh-en</c>, instead of
/// passing them through as raw letters that are not in the model's
/// <c>phoneme_id_map</c> (Issue #833).
/// </summary>
public class TextModeZhEnTests
{
    // The Chinese golden cases with English letters (Issue #833).
    public static TheoryData<string> ZhEnInputs =>
    [
        "Hello你好",
        "Hello, 你好!",
        "我用 GPS 导航",
        "我喜欢 Python",
        "ChatGPT 很厉害",
        "Apple 公司",
        "你好，GPS",
        "你好，Hello",
        "Hello，你好",
        "Hello、世界",
    ];

#pragma warning disable IL2026 // the CLI suppresses the same warning at its call sites
    private static IPhonemizer CliPhonemizer(string language) =>
        Program.ResolveTextModePhonemizer(language);
#pragma warning restore IL2026

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

    private static JsonDocument LoadJson(params string[] relative) =>
        JsonDocument.Parse(File.ReadAllText(Path.Join([RepoRoot(), .. relative])));

    /// <summary>Maps the Python spelling of multi-codepoint phonemes to their PUA character.</summary>
    private static Dictionary<string, string> LoadTokenToPua()
    {
        using JsonDocument pua = LoadJson("src", "python", "g2p", "piper_plus_g2p", "data", "pua.json");
        var map = new Dictionary<string, string>();
        foreach (JsonElement entry in pua.RootElement.GetProperty("entries").EnumerateArray())
        {
            int codepoint = Convert.ToInt32(entry.GetProperty("codepoint").GetString(), 16);
            map[entry.GetProperty("token").GetString()!] = char.ConvertFromUtf32(codepoint);
        }

        return map;
    }

    /// <summary>
    /// Python's <c>MultilingualPhonemizer</c> output, tokens separated by '|'
    /// so that the word boundary token " " can be written.
    /// </summary>
    [Theory]
    [InlineData(
        "Hello你好",
        "aɪ|tone1|tʂʰ|ɻ̩|tone4|i|tone1|aɪ|tone1|ɚ|tone2|aɪ|tone1|ɚ|tone2|oʊ|tone1|n|i|tone2|x|aʊ|tone3")]
    [InlineData(
        "我用 GPS 导航",
        "uo|tone3|iuŋ|tone4| |tɕ|i|tone4|pʰ|i|tone4|aɪ|tone1|s|ɨ|tone4|t|aʊ|tone3|x|aŋ|tone2")]
    [InlineData(
        "Hello你好?",
        "aɪ|tone1|tʂʰ|ɻ̩|tone4|i|tone1|aɪ|tone1|ɚ|tone2|aɪ|tone1|ɚ|tone2|oʊ|tone1|n|i|tone2|x|aʊ|tone3|?")]
    [InlineData("你好吗？", "n|i|tone2|x|aʊ|tone3|m|a|tone5|?")]
    public void SingleChinese_MatchesPython(string input, string python)
    {
        Dictionary<string, string> tokenToPua = LoadTokenToPua();
        List<string> expected = python.Split('|')
            .Select(t => tokenToPua.TryGetValue(t, out string? pua) ? pua : t)
            .ToList();

        Assert.Equal(expected, CliPhonemizer("zh").Phonemize(input));
    }

    [Theory]
    [MemberData(nameof(ZhEnInputs))]
    public void SingleChinese_ReadsLettersLikeZhEn(string input)
    {
        Assert.Equal(CliPhonemizer("zh-en").Phonemize(input), CliPhonemizer("zh").Phonemize(input));
    }

    [Theory]
    [MemberData(nameof(ZhEnInputs))]
    public void SingleChinese_EmitsOnlyModelPhonemes(string input)
    {
        using JsonDocument config = LoadJson("test", "models", "multilingual-test-medium.onnx.json");
        HashSet<string> modelPhonemes = config.RootElement.GetProperty("phoneme_id_map")
            .EnumerateObject()
            .Select(p => p.Name)
            .ToHashSet();

        List<string> unknown = CliPhonemizer("zh").Phonemize(input)
            .Where(t => !modelPhonemes.Contains(t))
            .ToList();

        Assert.Empty(unknown);
    }
}
