using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// Compares the phonemes the C# CLI produces with the Python golden in
/// <c>tests/fixtures/g2p/phoneme_test_cases_golden.json</c>, for every
/// en / es / fr / pt / sv / zh case.
/// </summary>
/// <remarks>
/// <para>
/// The golden is Python's <c>MultilingualPhonemizer</c> with the case language
/// as the Latin default. The CLI's equivalent is <c>--text ... --language xx</c>:
/// <see cref="Program.ResolveTextModePhonemizer"/> then returns a
/// <c>MultilingualPhonemizer</c> with that language as the Latin default (zh
/// also registers en for the ZH-EN loanword reading). That method and the engine adapters
/// it constructs come from the referenced <c>PiperPlus.Cli</c> assembly, so this
/// is the exact phonemizer a CLI user gets. The comparison is on <see cref="IPhonemizer.Phonemize"/>, the
/// token list the CLI maps to IDs with the model's <c>phoneme_id_map</c>.
/// </para>
/// <para>
/// Cases known to differ are listed in
/// <c>tests/fixtures/g2p/known_divergences.json</c> for the <c>csharp</c>
/// runtime. A difference that is not listed fails, and so does a listed case
/// that now matches, so the list shrinks as the linked issues are fixed.
/// English words that must never phonemize to nothing are listed in
/// <c>tests/fixtures/g2p/english_no_drop_words.json</c> and follow the same rule.
/// </para>
/// <para>
/// Two representation differences are not divergences:
/// multi-codepoint phonemes (rr, tʃ, tone3) are one PUA character in the C#
/// output and spelled out in the golden. Only the golden side is mapped
/// (<c>pua.json</c>), so output that forgets the PUA encoding still fails, as
/// it would at the ID lookup.
/// </para>
/// <para>
/// Nothing is skipped: a missing golden, registry or dictionary fails the test.
/// English uses the embedded <c>cmudict_data.json</c> and Chinese the
/// embedded <c>pinyin_*.json</c>, which is what the CLI ships. Japanese needs
/// OpenJTalk and Korean is absent from the golden, so both are left out.
/// </para>
/// </remarks>
public class G2pGoldenParityTests
{
    private const string Runtime = "csharp";

    private static readonly string[] Languages = ["en", "es", "fr", "pt", "sv", "zh"];

    // Tokens that carry no sound: a word made only of these was dropped.
    private static readonly HashSet<string> Silent =
        ["^", "$", "_", " ", ".", ",", "!", "?", ";", ":", "'", "\"", "-"];

    /// <summary>
    /// The phoneme_id_map of the checked-in 6-language test model (173 symbols).
    /// The CLI drops a token that is not in the model's map (PhonemeEncoder only
    /// logs it), so a word counts as spoken only if one of its tokens is there:
    /// raw text passed through as "phonemes" (digits, capitals, accented
    /// letters) is silent for the user.
    /// </summary>
    private static HashSet<string> LoadModelPhonemes()
    {
        using JsonDocument config = LoadJson("test", "models", "multilingual-test-medium.onnx.json");
        HashSet<string> phonemes = config.RootElement.GetProperty("phoneme_id_map")
            .EnumerateObject()
            .Select(p => p.Name)
            .ToHashSet();
        Assert.NotEmpty(phonemes);
        return phonemes;
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

    private static JsonDocument LoadJson(params string[] relative)
    {
        string path = Path.Join([RepoRoot(), .. relative]);
        return JsonDocument.Parse(File.ReadAllText(path));
    }

    /// <summary>Maps the golden spelling of multi-codepoint phonemes to their PUA character.</summary>
    private static Dictionary<string, string> LoadTokenToPua()
    {
        using JsonDocument pua = LoadJson("src", "python", "g2p", "piper_plus_g2p", "data", "pua.json");
        var map = new Dictionary<string, string>();
        foreach (JsonElement entry in pua.RootElement.GetProperty("entries").EnumerateArray())
        {
            int codepoint = Convert.ToInt32(entry.GetProperty("codepoint").GetString(), 16);
            map[entry.GetProperty("token").GetString()!] = char.ConvertFromUtf32(codepoint);
        }

        Assert.NotEmpty(map);
        return map;
    }

    private static bool ListsRuntime(JsonElement entry) =>
        entry.GetProperty("runtimes").EnumerateArray().Any(r => r.GetString() == Runtime);

    /// <summary>
    /// Tokens are joined with one space; a word boundary token " " therefore
    /// appears as three spaces (two empty parts when split).
    /// </summary>
    private static List<string> SplitPhonemes(string s)
    {
        var tokens = new List<string>();
        int emptyParts = 0;
        foreach (string part in s.Split(' '))
        {
            if (part.Length > 0)
            {
                emptyParts = 0;
                tokens.Add(part);
            }
            else if (++emptyParts == 2)
            {
                emptyParts = 0;
                tokens.Add(" ");
            }
        }

        return tokens;
    }

    /// <summary>Joins like the golden and spells PUA characters as U+XXXX.</summary>
    private static string Describe(IEnumerable<string> tokens)
    {
        var sb = new StringBuilder();
        foreach (string t in tokens)
        {
            if (sb.Length > 0)
            {
                sb.Append(' ');
            }

            foreach (char ch in t)
            {
                sb.Append(ch is >= '\uE000' and <= '\uF8FF' ? $"U+{(int)ch:X4}" : ch.ToString());
            }
        }

        return sb.ToString();
    }

#pragma warning disable IL2026 // the CLI suppresses the same warning at its call sites
    private static IPhonemizer CliPhonemizer(string language) =>
        Program.ResolveTextModePhonemizer(language);
#pragma warning restore IL2026

    [Fact]
    public void CliPhonemes_MatchPythonGolden_ExceptListedDivergences()
    {
        Dictionary<string, string> tokenToPua = LoadTokenToPua();
        using JsonDocument registry = LoadJson("tests", "fixtures", "g2p", "known_divergences.json");
        using JsonDocument golden = LoadJson("tests", "fixtures", "g2p", "phoneme_test_cases_golden.json");
        HashSet<(string Lang, string Input)> known = registry.RootElement.GetProperty("divergences")
            .EnumerateArray()
            .Where(ListsRuntime)
            .Select(e => (e.GetProperty("language").GetString()!, e.GetProperty("input").GetString()!))
            .ToHashSet();
        Dictionary<string, IPhonemizer> phonemizers = Languages.ToDictionary(l => l, CliPhonemizer);

        int verified = 0;
        int knownCount = 0;
        var failures = new List<string>();
        foreach (JsonElement c in golden.RootElement.GetProperty("test_cases").EnumerateArray())
        {
            string lang = c.GetProperty("language").GetString()!;
            if (!phonemizers.TryGetValue(lang, out IPhonemizer? phonemizer))
            {
                continue;
            }

            string input = c.GetProperty("input").GetString()!;
            string goldenPhonemes = c.GetProperty("expected_phonemes").GetString()!;
            List<string> expected = SplitPhonemes(goldenPhonemes)
                .Select(t => tokenToPua.TryGetValue(t, out string? pua) ? pua : t)
                .ToList();

            List<string>? actual = null;
            string? error = null;
            try
            {
                actual = phonemizer.Phonemize(input);
            }
            catch (Exception ex)
            {
                error = $"(phonemize failed: {ex.GetType().Name}: {ex.Message})";
            }

            bool matches = actual is not null
                && expected.SequenceEqual(actual);
            verified++;

            string label = $"[{lang}] '{input}'";
            bool listed = known.Contains((lang, input));
            if (matches && listed)
            {
                failures.Add($"{label} now matches; remove it from known_divergences.json");
            }
            else if (!matches && listed)
            {
                knownCount++;
            }
            else if (!matches)
            {
                failures.Add(
                    $"{label}\n  expected: {Describe(expected)}\n  actual:   {error ?? Describe(actual!)}");
            }
        }

        Assert.True(verified > 0, "no golden case compared");
        Assert.True(
            failures.Count == 0,
            $"{failures.Count} failure(s), {knownCount} known, {verified} cases:\n" + string.Join("\n", failures));
    }

    /// <summary>
    /// Every token the CLI produces for the golden inputs of a language is in
    /// the model's <c>phoneme_id_map</c>, listed divergences included. A token
    /// outside the map is dropped at the ID lookup without an error, so the
    /// phoneme is silently lost: DotNetG2P.Portuguese emitted ɐ, w̃ and j̃
    /// (Issue #832), and the English adapter passed digits and unknown words
    /// through as raw characters (Issue #821).
    /// </summary>
    [Theory]
    [InlineData("en")]
    [InlineData("es")]
    [InlineData("pt")]
    [InlineData("fr")]
    public void CliPhonemes_ForGoldenInputs_AreAllInModelPhonemeIdMap(string language)
    {
        HashSet<string> modelPhonemes = LoadModelPhonemes();
        using JsonDocument golden = LoadJson("tests", "fixtures", "g2p", "phoneme_test_cases_golden.json");
        IPhonemizer phonemizer = CliPhonemizer(language);

        int checkedCases = 0;
        var failures = new List<string>();
        foreach (JsonElement c in golden.RootElement.GetProperty("test_cases").EnumerateArray())
        {
            if (c.GetProperty("language").GetString() != language)
            {
                continue;
            }

            string input = c.GetProperty("input").GetString()!;
            List<string> unknown = phonemizer.Phonemize(input)
                .Where(t => !modelPhonemes.Contains(t))
                .Distinct()
                .ToList();
            checkedCases++;
            if (unknown.Count > 0)
            {
                failures.Add($"'{input}': {Describe(unknown)}");
            }
        }

        Assert.True(checkedCases > 0, $"no {language} golden case");
        Assert.True(failures.Count == 0, "tokens not in phoneme_id_map:\n" + string.Join("\n", failures));
    }

    [Fact]
    public void CliEnglish_DoesNotDropWords_ExceptKnownDrops()
    {
        using JsonDocument list = LoadJson("tests", "fixtures", "g2p", "english_no_drop_words.json");
        HashSet<string> knownDrops = list.RootElement.GetProperty("known_drops")
            .EnumerateArray()
            .Where(ListsRuntime)
            .Select(e => e.GetProperty("word").GetString()!)
            .ToHashSet();
        HashSet<string> modelPhonemes = LoadModelPhonemes();
        IPhonemizer phonemizer = CliPhonemizer("en");

        int checkedWords = 0;
        var failures = new List<string>();
        foreach (JsonElement w in list.RootElement.GetProperty("words").EnumerateArray())
        {
            string word = w.GetString()!;
            List<string> tokens;
            try
            {
                tokens = phonemizer.Phonemize(word);
            }
            catch (Exception ex)
            {
                tokens = [];
                failures.Add($"'{word}' threw {ex.GetType().Name}: {ex.Message}");
            }

            bool spoken = tokens.Any(t => !Silent.Contains(t) && modelPhonemes.Contains(t));
            checkedWords++;
            bool listed = knownDrops.Contains(word);
            if (spoken && listed)
            {
                failures.Add($"'{word}' is now spoken; remove it from known_drops");
            }
            else if (!spoken && !listed)
            {
                failures.Add($"'{word}' produced no phoneme: '{Describe(tokens)}'");
            }
        }

        Assert.True(checkedWords > 0, "english_no_drop_words.json has no words");
        Assert.True(failures.Count == 0, string.Join("\n", failures));
    }
}
