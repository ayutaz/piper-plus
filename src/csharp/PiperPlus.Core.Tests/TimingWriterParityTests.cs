using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Cross-runtime parity test for <see cref="TimingWriter.CalculateTiming"/>
/// using <c>tests/fixtures/phoneme_timing/golden_matrix.json</c> (canonical
/// Python output from <c>piper.timing.durations_to_timing</c>).
/// Mirrors the Rust / Go / C++ / WASM-JS parity tests added in commit 6667ca8b.
/// </summary>
public sealed class TimingWriterParityTests
{
    public static IEnumerable<object[]> CaseNames()
    {
        yield return ["basic_konnichiwa"];
        yield return ["single_phoneme"];
        yield return ["negative_clamped"];
        yield return ["high_sample_rate"];
        yield return ["pua_phoneme"];
        yield return ["empty"];
        yield return ["all_zero_durations"];
    }

    [Theory]
    [MemberData(nameof(CaseNames))]
    public void Parity_GoldenMatrix(string caseName)
    {
        JsonElement fixture = LoadFixture();
        JsonElement caseElement = FindCase(fixture, caseName);

        JsonElement inputs = caseElement.GetProperty("inputs");
        JsonElement expected = caseElement.GetProperty("expected");

        var phonemeTokens = inputs.GetProperty("phoneme_tokens")
            .EnumerateArray()
            .Select(e => e.GetString()!)
            .ToArray();
        var durations = inputs.GetProperty("durations")
            .EnumerateArray()
            .Select(e => (float)e.GetDouble())
            .ToArray();
        int sampleRate = inputs.GetProperty("sample_rate").GetInt32();
        int hopLength = inputs.GetProperty("hop_length").GetInt32();

        BuildIdMapping(phonemeTokens, out var phonemeIds, out Dictionary<string, int[]>? phonemeIdMap);

        List<TimingWriter.PhonemeTimingEntry> entries = TimingWriter.CalculateTiming(
            phonemeIds, durations, phonemeIdMap, sampleRate, hopLength);

        var expectedPhonemes = expected.GetProperty("phonemes").EnumerateArray().ToList();
        Assert.Equal(expectedPhonemes.Count, entries.Count);

        for (int i = 0; i < entries.Count; i++)
        {
            TimingWriter.PhonemeTimingEntry actual = entries[i];
            JsonElement exp = expectedPhonemes[i];

            Assert.Equal(exp.GetProperty("phoneme").GetString(), actual.Phoneme);
            Assert.Equal(
                (float)exp.GetProperty("start_ms").GetDouble(),
                actual.StartMs,
                precision: 3);
            Assert.Equal(
                (float)exp.GetProperty("end_ms").GetDouble(),
                actual.EndMs,
                precision: 3);
            Assert.Equal(
                (float)exp.GetProperty("duration_ms").GetDouble(),
                actual.DurationMs,
                precision: 3);
        }

        // Formatted-output parity, byte for byte.
        //
        // The fixture held only float milliseconds until spec_version 1.2, so
        // the FORMATTING layer went unchecked in every runtime. Three defects
        // were found there one at a time by reading code rather than by a
        // failing test: rounding at .5 (#681), CRLF on Windows (#683), a
        // thousands separator in the cue index (#684). This is also the
        // assertion that fails on Windows if ForceLf is ever dropped, since it
        // compares bytes instead of normalising them away.
        using var tsvStream = new MemoryStream();
        TimingWriter.WriteTsv(tsvStream, entries);
        Assert.Equal(
            expected.GetProperty("tsv").GetString(),
            Encoding.UTF8.GetString(tsvStream.ToArray()));

        using var srtStream = new MemoryStream();
        TimingWriter.WriteSrt(srtStream, entries);
        Assert.Equal(
            expected.GetProperty("srt").GetString(),
            Encoding.UTF8.GetString(srtStream.ToArray()));
    }

    [Fact]
    public void Parity_TotalDuration_MatchesAllCases()
    {
        JsonElement fixture = LoadFixture();
        foreach (JsonElement caseElement in fixture.GetProperty("cases").EnumerateArray())
        {
            string name = caseElement.GetProperty("name").GetString()!;
            JsonElement inputs = caseElement.GetProperty("inputs");
            JsonElement expected = caseElement.GetProperty("expected");

            var phonemeTokens = inputs.GetProperty("phoneme_tokens")
                .EnumerateArray()
                .Select(e => e.GetString()!)
                .ToArray();
            var durations = inputs.GetProperty("durations")
                .EnumerateArray()
                .Select(e => (float)e.GetDouble())
                .ToArray();
            int sampleRate = inputs.GetProperty("sample_rate").GetInt32();
            int hopLength = inputs.GetProperty("hop_length").GetInt32();

            BuildIdMapping(phonemeTokens, out var phonemeIds, out Dictionary<string, int[]>? phonemeIdMap);

            List<TimingWriter.PhonemeTimingEntry> entries = TimingWriter.CalculateTiming(
                phonemeIds, durations, phonemeIdMap, sampleRate, hopLength);

            float expectedTotal = (float)expected.GetProperty("total_duration_ms").GetDouble();
            float actualTotal = entries.Count > 0 ? entries[^1].EndMs : 0f;
            Assert.Equal(expectedTotal, actualTotal, precision: 3);
            Assert.True(actualTotal >= 0f, $"case {name}: total must be non-negative");
        }
    }

    [Fact]
    public void Fixture_SchemaVersion_IsOne()
    {
        JsonElement fixture = LoadFixture();
        Assert.Equal(1, fixture.GetProperty("schema_version").GetInt32());
    }

    /// <summary>
    /// Builds a synthetic <c>phoneme_id_map</c> for the parity test.
    /// IDs start at 3 to avoid the special tokens PAD=0 / BOS=1 / EOS=2.
    /// PUA tokens like <c>"U+E019"</c> are passed through verbatim — they
    /// have <c>Length &gt; 1</c>, so the C# reverse map will not try to
    /// decode them as single-char PUA codepoints.
    /// </summary>
    private static void BuildIdMapping(
        string[] phonemeTokens,
        out long[] phonemeIds,
        out Dictionary<string, int[]> phonemeIdMap)
    {
        phonemeIdMap = new Dictionary<string, int[]>(StringComparer.Ordinal);
        phonemeIds = new long[phonemeTokens.Length];
        for (int i = 0; i < phonemeTokens.Length; i++)
        {
            string token = phonemeTokens[i];
            if (!phonemeIdMap.TryGetValue(token, out var existing))
            {
                int newId = 3 + phonemeIdMap.Count;
                existing = [newId];
                phonemeIdMap[token] = existing;
            }

            phonemeIds[i] = existing[0];
        }
    }

    private static JsonElement LoadFixture()
    {
        var path = ResolveFixturePath();
        var json = File.ReadAllText(path);
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }

    private static JsonElement FindCase(JsonElement fixture, string caseName)
    {
        JsonElement? match = fixture.GetProperty("cases").EnumerateArray()
            .Where(c => c.GetProperty("name").GetString() == caseName)
            .Select(c => (JsonElement?)c.Clone())
            .FirstOrDefault();

        return match ?? throw new KeyNotFoundException(
            $"case not found in fixture: {caseName}");
    }

    /// <summary>
    /// Walks up from <see cref="AppContext.BaseDirectory"/> until it finds the
    /// repo root that contains <c>tests/fixtures/phoneme_timing/golden_matrix.json</c>.
    /// </summary>
    private static string ResolveFixturePath()
    {
        var dir = AppContext.BaseDirectory;
        for (int i = 0; i < 12; i++)
        {
            var candidate = Path.Join(
                dir, "tests", "fixtures", "phoneme_timing", "golden_matrix.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            DirectoryInfo? parent = Directory.GetParent(dir);
            if (parent is null)
            {
                break;
            }

            dir = parent.FullName;
        }

        throw new FileNotFoundException(
            $"golden_matrix.json not found walking up from {AppContext.BaseDirectory}");
    }

    /// <summary>
    /// Reverse-map parity (issue #698).
    ///
    /// The timing cases above start from resolved token strings, so nothing in
    /// them says how phoneme_id_map is turned back into names. The contract
    /// said first-wins without defining "first", and the runtimes split
    /// three/three -- Python / JS / C# iterated in insertion order, C++ / Rust
    /// / Go sorted. Every shipped model is collision-free, so all six agreed
    /// byte-for-byte and no test could see it.
    ///
    /// C# sources PUA names from its own <see
    /// cref="Mapping.OpenJTalkToPiperMapping.CharToToken"/> table rather than
    /// from an injected dictionary, so a fixture case is comparable only when
    /// its <c>pua_names</c> agrees with that table (or it has no PUA key at
    /// all). That is asserted rather than assumed: the table is pinned
    /// byte-for-byte to the canonical pua.json by the PUA consistency gate, so
    /// a case that violates it means the fixture and the gate disagree, which
    /// this test should report rather than skip.
    /// </summary>
    [Fact]
    public void ReverseMapParity_GoldenMatrix()
    {
        JsonElement fixture = LoadFixture();
        Assert.True(
            fixture.TryGetProperty("reverse_map_cases", out JsonElement cases),
            "fixture has no reverse_map_cases; regenerate with scripts/regenerate_timing_fixture.py");
        Assert.True(cases.GetArrayLength() > 0, "reverse_map_cases is empty");

        foreach (JsonElement caseElement in cases.EnumerateArray())
        {
            string name = caseElement.GetProperty("name").GetString()!;
            JsonElement inputs = caseElement.GetProperty("inputs");
            JsonElement idMapElement = inputs.GetProperty("phoneme_id_map");

            var phonemeIdMap = new Dictionary<string, int[]>();
            foreach (JsonProperty entry in idMapElement.EnumerateObject())
            {
                phonemeIdMap[entry.Name] = entry.Value.EnumerateArray()
                    .Select(e => e.GetInt32())
                    .ToArray();
            }

            AssertPuaNamesMatchBuiltInTable(name, inputs, phonemeIdMap);

            Dictionary<long, string> got = TimingWriter.BuildReverseIdMap(phonemeIdMap);

            JsonElement expected = caseElement.GetProperty("expected");
            int expectedCount = expected.EnumerateObject().Count();
            Assert.Equal(expectedCount, got.Count);
            foreach (JsonProperty entry in expected.EnumerateObject())
            {
                long id = long.Parse(entry.Name, System.Globalization.CultureInfo.InvariantCulture);
                Assert.True(
                    got.TryGetValue(id, out string? actual),
                    $"case {name}: id {id} is missing from the reverse map");
                Assert.Equal(entry.Value.GetString(), actual);
            }
        }
    }

    private static void AssertPuaNamesMatchBuiltInTable(
        string caseName, JsonElement inputs, Dictionary<string, int[]> phonemeIdMap)
    {
        var declared = new Dictionary<string, string>();
        if (inputs.TryGetProperty("pua_names", out JsonElement puaNames)
            && puaNames.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty entry in puaNames.EnumerateObject())
            {
                declared[entry.Name] = entry.Value.GetString()!;
            }
        }

        foreach (string key in phonemeIdMap.Keys)
        {
            if (key.Length != 1)
            {
                continue;
            }

            char ch = key[0];
            bool inTable = Mapping.OpenJTalkToPiperMapping.CharToToken
                .TryGetValue(ch, out string? builtIn);
            bool inFixture = declared.TryGetValue(key, out string? fromFixture);

            if (inTable && inFixture)
            {
                Assert.Equal(fromFixture, builtIn);
            }
            else if (inTable != inFixture)
            {
                Assert.Fail(
                    $"case {caseName}: PUA key U+{(int)ch:X4} is "
                    + (inTable ? "named by C#'s CharToToken but not by the fixture"
                               : "named by the fixture but not by C#'s CharToToken")
                    + " -- the fixture and the PUA consistency gate disagree, so the "
                    + "comparison would be meaningless rather than merely inapplicable");
            }
        }
    }

    /// <summary>
    /// Anti-vacuity: without a MIRRORED colliding case, key order is
    /// unobservable. A collision-free map resolves identically under any
    /// iteration order, and a single colliding map can be satisfied by a
    /// runtime that happens to receive its keys already sorted.
    /// </summary>
    [Fact]
    public void ReverseMapParity_IncludesAMirroredCollision()
    {
        JsonElement fixture = LoadFixture();
        Assert.True(fixture.TryGetProperty("reverse_map_cases", out JsonElement cases));

        var ordersByKeySet = new Dictionary<string, HashSet<string>>();
        foreach (JsonElement caseElement in cases.EnumerateArray())
        {
            JsonElement idMap = caseElement.GetProperty("inputs").GetProperty("phoneme_id_map");
            var seen = new HashSet<int>();
            bool collides = false;
            var keys = new List<string>();
            foreach (JsonProperty entry in idMap.EnumerateObject())
            {
                keys.Add(entry.Name);
                foreach (JsonElement id in entry.Value.EnumerateArray())
                {
                    if (!seen.Add(id.GetInt32()))
                    {
                        collides = true;
                    }
                }
            }

            if (!collides)
            {
                continue;
            }

            string keySet = string.Join("\u0000", keys.OrderBy(k => k, StringComparer.Ordinal));
            string order = string.Join("\u0000", keys);
            if (!ordersByKeySet.TryGetValue(keySet, out HashSet<string>? orders))
            {
                orders = [];
                ordersByKeySet[keySet] = orders;
            }

            orders.Add(order);
        }

        Assert.True(
            ordersByKeySet.Values.Any(orders => orders.Count >= 2),
            "no colliding key set is written in two different orders, so these cases "
            + "cannot detect a runtime that iterates phoneme_id_map in insertion order");
    }
}
