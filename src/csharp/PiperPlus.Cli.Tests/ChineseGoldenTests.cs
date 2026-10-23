using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Cli;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// Compares the CLI's Chinese G2P with the Python (pypinyin) golden in
/// <c>tests/fixtures/g2p/phoneme_test_cases_golden.json</c>.
/// </summary>
/// <remarks>
/// The other runtimes only checked that Chinese output was non-empty, so
/// shipped dictionaries that dropped every tone passed for months (issue
/// #790). <see cref="BundledChineseG2PEngine"/> is <c>internal</c> to
/// <c>PiperPlus.Cli</c>, which exposes its internals to this test project, so
/// this exercises the exact engine the CLI uses.
/// </remarks>
public class ChineseGoldenTests
{
    // Python's MultilingualPhonemizer drops the sentence punctuation that
    // the per-language phonemizers keep; compare the spoken tokens only.
    private static readonly HashSet<string> Skipped =
        ["^", "$", "_", " ", ".", ",", "!", "?", ";", ":"];

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

    private static Dictionary<string, string> LoadTokenToPua(string root)
    {
        using JsonDocument pua = JsonDocument.Parse(File.ReadAllText(
            Path.Join(root, "src", "python", "g2p", "piper_plus_g2p", "data", "pua.json")));
        var map = new Dictionary<string, string>();
        foreach (JsonElement entry in pua.RootElement.GetProperty("entries").EnumerateArray())
        {
            int codepoint = System.Convert.ToInt32(entry.GetProperty("codepoint").GetString(), 16);
            map[entry.GetProperty("token").GetString()!] = char.ConvertFromUtf32(codepoint);
        }

        return map;
    }

    [Fact]
    public void BundledChineseEngine_MatchesPythonGolden()
    {
        string root = RepoRoot();
        Dictionary<string, string> tokenToPua = LoadTokenToPua(root);
        using JsonDocument golden = JsonDocument.Parse(File.ReadAllText(
            Path.Join(root, "tests", "fixtures", "g2p", "phoneme_test_cases_golden.json")));

        var phonemizer = new ChinesePhonemizer(new BundledChineseG2PEngine());
        var mismatches = new List<string>();
        int checkedCases = 0;
        foreach (JsonElement c in golden.RootElement.GetProperty("test_cases").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString()!;

            // Latin letters and digits go through the ZH-EN / number handling.
            if (c.GetProperty("language").GetString() != "zh" || input.Any(char.IsAsciiLetterOrDigit))
            {
                continue;
            }

            string[] expected = c.GetProperty("expected_phonemes").GetString()!
                .Split(' ', StringSplitOptions.RemoveEmptyEntries)
                .Select(t => tokenToPua.TryGetValue(t, out string? pua) ? pua : t)
                .Where(t => !Skipped.Contains(t))
                .ToArray();
            string[] actual = phonemizer.Phonemize(input)
                .Where(t => !Skipped.Contains(t))
                .ToArray();
            if (!actual.SequenceEqual(expected))
            {
                mismatches.Add(
                    $"{input}\n  expected: {Describe(expected)}\n  actual:   {Describe(actual)}");
            }

            checkedCases++;
        }

        Assert.True(checkedCases >= 40, $"too few zh cases in the golden fixture: {checkedCases}");
        Assert.True(
            mismatches.Count == 0,
            $"{mismatches.Count} zh cases differ from Python:\n" + string.Join("\n", mismatches));
    }

    private static string Describe(IEnumerable<string> tokens) =>
        string.Join(" ", tokens.Select(t => string.Concat(t.Select(ch =>
            ch is >= '' and <= '' ? $"U+{(int)ch:X4}" : ch.ToString()))));
}
