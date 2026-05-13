using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using PiperPlus.Core.Config;
using Xunit;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Language ID Map parity test (C# mirror).
///
/// <para>
/// Loads <c>docs/spec/language-id-map-contract.toml</c> and pins the
/// canonical <c>{ja=0, en=1, zh=2, es=3, fr=4, pt=5}</c> mapping that all
/// piper-plus checkpoints (and therefore every consumer runtime) must agree
/// on for the v1.11+ pipeline. Drift in any runtime silently misindexes
/// <c>emb_lang</c> and corrupts every multilingual model.
/// </para>
/// <para>
/// C# itself has NO hard-coded language_id_map literal — per the contract
/// file (<c>runtime_sources.entries</c> with <c>kind = "none"</c>), C# is
/// "data-driven: <see cref="PiperConfig.LanguageIdMap"/> is parsed from
/// config JSON". This test therefore verifies two invariants:
/// </para>
/// <list type="number">
///   <item><description>The contract TOML still encodes the expected
///   <c>trained_language_id_map = { ja=0, en=1, zh=2, es=3, fr=4, pt=5 }</c>
///   so a future drift in the canonical source is caught locally before it
///   propagates into model configs.</description></item>
///   <item><description>The <see cref="PiperConfig.LanguageIdMap"/> property
///   is still typed <c>Dictionary&lt;string, int&gt;?</c> — if a future
///   refactor weakens this (e.g. changes the value type), every consumer of
///   the deserialized config breaks silently.</description></item>
/// </list>
/// <para>
/// Sister tests in Python/Rust/Go/WASM consume the same TOML; the global
/// <c>scripts/check_language_id_map_contract.py</c> CI gate compares each
/// runtime's literal against the canonical TOML keys.
/// </para>
/// </summary>
public sealed class LanguageIdMapParityTests
{
    /// <summary>The canonical 6-language trained-model mapping. This is the
    /// shape every checkpoint emitted by <c>prepare_multilingual_dataset.py</c>
    /// uses; runtime config JSON files must agree.</summary>
    private static readonly Dictionary<string, int> ExpectedTrainedMap = new(StringComparer.Ordinal)
    {
        ["ja"] = 0,
        ["en"] = 1,
        ["zh"] = 2,
        ["es"] = 3,
        ["fr"] = 4,
        ["pt"] = 5,
    };

    private static readonly Lazy<Dictionary<string, int>> ParsedTrainedMap = new(
        () => ParseInlineLanguageIdMap(LoadContractToml(), "trained_language_id_map"));

    [Fact]
    public void ContractToml_TrainedMap_MatchesCanonicalSixLangs()
    {
        Dictionary<string, int> parsed = ParsedTrainedMap.Value;

        // Exact match — both keys present and IDs identical. Any deviation
        // (extra key, missing key, swapped ID) means trained checkpoints
        // shipped from the v1.12.0+ pipeline will misindex emb_lang.
        Assert.Equal(ExpectedTrainedMap.Count, parsed.Count);
        foreach (KeyValuePair<string, int> kv in ExpectedTrainedMap)
        {
            Assert.True(
                parsed.TryGetValue(kv.Key, out int got),
                $"contract TOML trained_language_id_map missing key '{kv.Key}'");
            Assert.Equal(kv.Value, got);
        }
    }

    [Fact]
    public void ContractToml_TrainedMap_HasJaIsZeroInvariant()
    {
        // The TOML spec [invariants] section says `ja_is_zero = true`.
        // Re-check at the C# level so a future bump of the canonical map
        // (e.g. someone proposes ja=6 in the 8-lang form) does not silently
        // break legacy ckpts that rely on ja=0.
        Assert.Equal(0, ParsedTrainedMap.Value["ja"]);
    }

    [Fact]
    public void ContractToml_TrainedMap_HasEnIsOneInvariant()
    {
        Assert.Equal(1, ParsedTrainedMap.Value["en"]);
    }

    [Fact]
    public void ContractToml_TrainedMap_ValuesAreConsecutiveFromZero()
    {
        // [invariants] values_consecutive_from_zero = true.
        Dictionary<string, int> parsed = ParsedTrainedMap.Value;
        int[] sorted = parsed.Values.OrderBy(v => v).ToArray();
        for (int i = 0; i < sorted.Length; i++)
        {
            Assert.Equal(i, sorted[i]);
        }
    }

    [Fact]
    public void ContractToml_TrainedMap_ValuesUnique()
    {
        Dictionary<string, int> parsed = ParsedTrainedMap.Value;
        Assert.Equal(parsed.Count, parsed.Values.Distinct().Count());
    }

    [Fact]
    public void PiperConfig_LanguageIdMap_IsDictionaryStringInt()
    {
        // C# is data-driven (kind = "none" in the contract TOML): the
        // LanguageIdMap is parsed from config JSON, not hard-coded. Pin the
        // type so a future refactor cannot silently weaken the contract
        // (e.g. relaxing to Dictionary<string, long> or string keys would
        // break every model config consumer).
        System.Reflection.PropertyInfo? prop = typeof(PiperConfig).GetProperty("LanguageIdMap");
        Assert.NotNull(prop);

        Type t = prop!.PropertyType;

        // Should be Dictionary<string, int> wrapped in Nullable<T> reference
        // semantics (the underlying generic type definition is Dictionary<,>).
        Assert.True(t.IsGenericType, "LanguageIdMap must be a generic Dictionary<,>");
        Assert.Equal(typeof(Dictionary<,>), t.GetGenericTypeDefinition());

        Type[] args = t.GetGenericArguments();
        Assert.Equal(typeof(string), args[0]);
        Assert.Equal(typeof(int), args[1]);
    }

    // Minimal inline TOML parser for the contract file. We deliberately
    // do not pull in a full TOML library (e.g. Tomlyn): the only shape we
    // need is the inline-table line
    //   trained_language_id_map = { ja = 0, en = 1, zh = 2, es = 3, fr = 4, pt = 5 }
    // Adding a runtime dependency for one regex match would be excessive
    // for this targeted parity check.
    private static Dictionary<string, int> ParseInlineLanguageIdMap(string tomlText, string key)
    {
        // Match `<key> = { ja = 0, en = 1, ... }` — allow whitespace and
        // optional trailing commas. The fixture text is hand-curated, so we
        // accept only the canonical inline-table form here.
        Match outer = Regex.Match(
            tomlText,
            $"^\\s*{Regex.Escape(key)}\\s*=\\s*\\{{(?<body>[^}}]*)\\}}",
            RegexOptions.Multiline);

        if (!outer.Success)
        {
            throw new InvalidOperationException(
                $"Could not find inline-table assignment for '{key}' in language-id-map-contract.toml. " +
                "If the canonical TOML was restructured, update LanguageIdMapParityTests.ParseInlineLanguageIdMap.");
        }

        string body = outer.Groups["body"].Value;
        var result = new Dictionary<string, int>(StringComparer.Ordinal);

        foreach (Match entry in Regex.Matches(body, @"(?<k>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?<v>-?\d+)"))
        {
            string entryKey = entry.Groups["k"].Value;
            int entryVal = int.Parse(entry.Groups["v"].Value, System.Globalization.CultureInfo.InvariantCulture);
            result[entryKey] = entryVal;
        }

        if (result.Count == 0)
        {
            throw new InvalidOperationException(
                $"Inline-table for '{key}' produced no entries. Parser likely needs an update.");
        }

        return result;
    }

    private static string LoadContractToml()
    {
        string path = ResolveContractPath();
        return File.ReadAllText(path);
    }

    private static string ResolveContractPath()
    {
        // Walk up from the test bin directory until we find docs/spec.
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            string candidate = Path.Join(
                dir.FullName, "docs", "spec", "language-id-map-contract.toml");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            dir = dir.Parent;
        }

        throw new FileNotFoundException(
            "Could not locate docs/spec/language-id-map-contract.toml. " +
            "Run dotnet test from the repo root or set the working directory accordingly.");
    }
}
