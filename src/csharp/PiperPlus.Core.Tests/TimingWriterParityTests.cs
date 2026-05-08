using System.Collections.Generic;
using System.IO;
using System.Linq;
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
        var fixture = LoadFixture();
        var caseElement = FindCase(fixture, caseName);

        var inputs = caseElement.GetProperty("inputs");
        var expected = caseElement.GetProperty("expected");

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

        BuildIdMapping(phonemeTokens, out var phonemeIds, out var phonemeIdMap);

        var entries = TimingWriter.CalculateTiming(
            phonemeIds, durations, phonemeIdMap, sampleRate, hopLength);

        var expectedPhonemes = expected.GetProperty("phonemes").EnumerateArray().ToList();
        Assert.Equal(expectedPhonemes.Count, entries.Count);

        for (int i = 0; i < entries.Count; i++)
        {
            var actual = entries[i];
            var exp = expectedPhonemes[i];

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
    }

    [Fact]
    public void Parity_TotalDuration_MatchesAllCases()
    {
        var fixture = LoadFixture();
        foreach (var caseElement in fixture.GetProperty("cases").EnumerateArray())
        {
            string name = caseElement.GetProperty("name").GetString()!;
            var inputs = caseElement.GetProperty("inputs");
            var expected = caseElement.GetProperty("expected");

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

            BuildIdMapping(phonemeTokens, out var phonemeIds, out var phonemeIdMap);

            var entries = TimingWriter.CalculateTiming(
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
        var fixture = LoadFixture();
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
        var match = fixture.GetProperty("cases").EnumerateArray()
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

            var parent = Directory.GetParent(dir);
            if (parent is null)
            {
                break;
            }
            dir = parent.FullName;
        }

        throw new FileNotFoundException(
            $"golden_matrix.json not found walking up from {AppContext.BaseDirectory}");
    }
}
