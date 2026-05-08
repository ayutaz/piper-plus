using System.Text;
using System.Text.Json;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="TimingWriter"/>.
/// Covers timing calculation, special-token skipping, PUA reverse mapping,
/// JSON/TSV/SRT serialization, and edge cases. Conforms to
/// <c>docs/spec/phoneme-timing-contract.toml</c> v1.0 (millisecond units,
/// snake_case JSON keys, 3 output formats).
/// </summary>
public sealed class TimingWriterTests
{
    // ================================================================
    // Shared phoneme_id_map
    // ================================================================

    /// <summary>
    /// Minimal map for timing tests.
    /// PAD=0, BOS=1, EOS=2 are special and skipped by CalculateTiming.
    /// </summary>
    private static Dictionary<string, int[]> MakeMap() => new()
    {
        ["_"] = [0],   // PAD
        ["^"] = [1],   // BOS
        ["$"] = [2],   // EOS
        ["a"] = [10],
        ["k"] = [12],
        [""] = [17], // PUA for "a:"
        [""] = [40], // PUA for "N_m"
    };

    private const int SampleRate = 22050;
    private const int HopSize = 256;

    // ================================================================
    // 1. CalculateTiming_BasicDurations
    // ================================================================

    [Fact]
    public void CalculateTiming_BasicDurations()
    {
        var map = MakeMap();
        // frame_time_ms = (hop_size / sample_rate) * 1000 (spec)
        float frameLengthMs = (float)HopSize / SampleRate * 1000f;

        // Two regular phonemes: a (10 frames), k (5 frames)
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        Assert.Equal(2, entries.Count);

        // First entry: "a", starts at 0, ends at 10 * frameLengthMs
        Assert.Equal("a", entries[0].Phoneme);
        Assert.Equal(0f, entries[0].StartMs, precision: 3);
        Assert.Equal(10f * frameLengthMs, entries[0].EndMs, precision: 3);
        Assert.Equal(10f * frameLengthMs, entries[0].DurationMs, precision: 3);

        // Second entry: "k", starts where "a" ended
        Assert.Equal("k", entries[1].Phoneme);
        Assert.Equal(10f * frameLengthMs, entries[1].StartMs, precision: 3);
        Assert.Equal(15f * frameLengthMs, entries[1].EndMs, precision: 3);
        Assert.Equal(5f * frameLengthMs, entries[1].DurationMs, precision: 3);
    }

    // ================================================================
    // 2. CalculateTiming_SkipsSpecialTokens
    // ================================================================

    [Fact]
    public void CalculateTiming_SkipsSpecialTokens()
    {
        var map = MakeMap();
        float frameLengthMs = (float)HopSize / SampleRate * 1000f;

        // Sequence: PAD(0), BOS(1), a(10), EOS(2)
        long[] phonemeIds = [0, 1, 10, 2];
        float[] durations = [2f, 3f, 4f, 1f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        // Only "a" should appear -- PAD, BOS, EOS are skipped.
        Assert.Single(entries);
        Assert.Equal("a", entries[0].Phoneme);

        // "a" starts after PAD (2 frames) + BOS (3 frames) = 5 frames
        float expectedStartMs = 5f * frameLengthMs;
        Assert.Equal(expectedStartMs, entries[0].StartMs, precision: 3);
        Assert.Equal(expectedStartMs + 4f * frameLengthMs, entries[0].EndMs, precision: 3);
    }

    // ================================================================
    // 3. CalculateTiming_PuaReverseMapping
    // ================================================================

    [Fact]
    public void CalculateTiming_PuaReverseMapping()
    {
        var map = MakeMap();

        // PUA phoneme ID 17 (U+E000) should resolve to "a:" via CharToToken.
        long[] phonemeIds = [17, 40];
        float[] durations = [3f, 2f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        Assert.Equal(2, entries.Count);
        Assert.Equal("a:", entries[0].Phoneme);
        Assert.Equal("N_m", entries[1].Phoneme);
    }

    // ================================================================
    // 4. WriteJson_ValidOutput (spec-conforming object shape)
    // ================================================================

    [Fact]
    public void WriteJson_ValidOutput()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        // Spec shape: top-level object {phonemes, total_duration_ms, sample_rate}.
        Assert.Equal(JsonValueKind.Object, root.ValueKind);
        Assert.True(root.TryGetProperty("phonemes", out var phonemes));
        Assert.True(root.TryGetProperty("total_duration_ms", out _));
        Assert.True(root.TryGetProperty("sample_rate", out var sampleRateProp));
        Assert.Equal(SampleRate, sampleRateProp.GetInt32());

        Assert.Equal(JsonValueKind.Array, phonemes.ValueKind);
        Assert.Equal(2, phonemes.GetArrayLength());

        // First element — spec per-phoneme field names.
        var first = phonemes[0];
        Assert.Equal("a", first.GetProperty("phoneme").GetString());
        Assert.True(first.TryGetProperty("start_ms", out _));
        Assert.True(first.TryGetProperty("end_ms", out _));
        Assert.True(first.TryGetProperty("duration_ms", out _));
        // Legacy field names must NOT appear (spec compliance).
        Assert.False(first.TryGetProperty("start", out _));
        Assert.False(first.TryGetProperty("end", out _));
        Assert.False(first.TryGetProperty("duration", out _));

        // Second element
        var second = phonemes[1];
        Assert.Equal("k", second.GetProperty("phoneme").GetString());
        Assert.True(second.GetProperty("end_ms").GetSingle() > second.GetProperty("start_ms").GetSingle());
    }

    // ================================================================
    // 5. WriteTsv_ValidOutput (snake_case ms header per spec)
    // ================================================================

    [Fact]
    public void WriteTsv_ValidOutput()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        using var ms = new MemoryStream();
        TimingWriter.WriteTsv(ms, entries);

        ms.Position = 0;
        using var reader = new StreamReader(ms, Encoding.UTF8);
        string tsv = reader.ReadToEnd();

        var lines = tsv.Split('\n', StringSplitOptions.RemoveEmptyEntries);

        // Header + 2 data lines
        Assert.True(lines.Length >= 3, $"Expected at least 3 lines, got {lines.Length}");

        // Spec column header
        Assert.Equal("start_ms\tend_ms\tduration_ms\tphoneme", lines[0].TrimEnd('\r'));

        // First data row
        var cols1 = lines[1].TrimEnd('\r').Split('\t');
        Assert.Equal(4, cols1.Length);
        Assert.Equal("a", cols1[3]);

        // Second data row
        var cols2 = lines[2].TrimEnd('\r').Split('\t');
        Assert.Equal(4, cols2.Length);
        Assert.Equal("k", cols2[3]);

        // Verify numeric values parse correctly
        Assert.True(float.TryParse(cols1[0], System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture, out float start1));
        Assert.True(float.TryParse(cols1[1], System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture, out float end1));
        Assert.True(end1 > start1 || (start1 == 0f && end1 > 0f));
    }

    // ================================================================
    // 6. CalculateTiming_EmptyInput
    // ================================================================

    [Fact]
    public void CalculateTiming_EmptyInput()
    {
        var map = MakeMap();

        var entries = TimingWriter.CalculateTiming([], [], map, SampleRate, HopSize);

        Assert.Empty(entries);
    }

    // ================================================================
    // 7. WriteJson_ToStream
    // ================================================================

    [Fact]
    public void WriteJson_ToStream()
    {
        var map = MakeMap();
        long[] phonemeIds = [1, 10, 2]; // BOS, a, EOS
        float[] durations = [2f, 8f, 1f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        // Only "a" should be in the output (BOS/EOS skipped).
        Assert.Single(entries);
        Assert.Equal("a", entries[0].Phoneme);

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        // Verify valid JSON was written to the stream.
        Assert.True(ms.Length > 0, "Stream should contain JSON data");

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;
        // Spec shape — top-level object with `phonemes` array.
        Assert.Equal(JsonValueKind.Object, root.ValueKind);
        var phonemes = root.GetProperty("phonemes");
        Assert.Equal(1, phonemes.GetArrayLength());
        Assert.Equal("a", phonemes[0].GetProperty("phoneme").GetString());
        Assert.Equal(SampleRate, root.GetProperty("sample_rate").GetInt32());
    }

    // ================================================================
    // 8. WriteSrt_ValidOutput (HH:MM:SS,mmm cue format per spec)
    // ================================================================

    [Fact]
    public void WriteSrt_ValidOutput()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        using var ms = new MemoryStream();
        TimingWriter.WriteSrt(ms, entries);

        ms.Position = 0;
        using var reader = new StreamReader(ms, Encoding.UTF8);
        string srt = reader.ReadToEnd();

        // Cue 1: index "1" + timestamp + phoneme + blank line
        Assert.Contains("1\n", srt.Replace("\r\n", "\n"));
        Assert.Contains("2\n", srt.Replace("\r\n", "\n"));

        // Timestamp format: HH:MM:SS,mmm with " --> " separator (spec).
        Assert.Matches(@"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}", srt);

        // First cue starts at 00:00:00,000.
        Assert.Contains("00:00:00,000 --> ", srt);

        // Phonemes appear after their timestamp lines.
        Assert.Contains("\na\n", srt.Replace("\r\n", "\n"));
        Assert.Contains("\nk\n", srt.Replace("\r\n", "\n"));
    }

    // ================================================================
    // 9. WriteSrt_EmptyEntriesEmitsNothing
    // ================================================================

    [Fact]
    public void WriteSrt_EmptyEntriesEmitsNothing()
    {
        using var ms = new MemoryStream();
        TimingWriter.WriteSrt(ms, []);
        Assert.Equal(0, ms.Length);
    }

    // ================================================================
    // 10. SrtTimestampRollsOverHoursMinutesSeconds
    // ================================================================

    [Fact]
    public void SrtTimestamp_RollsOverHoursMinutesSeconds()
    {
        // Synthesize entries with very long durations to force HH:MM:SS rollover.
        var entries = new List<TimingWriter.PhonemeTimingEntry>
        {
            new("a", 0f, 3_661_500f, 3_661_500f), // 1h 01m 01.500s
        };

        using var ms = new MemoryStream();
        TimingWriter.WriteSrt(ms, entries);

        ms.Position = 0;
        using var reader = new StreamReader(ms, Encoding.UTF8);
        string srt = reader.ReadToEnd();

        Assert.Contains("00:00:00,000 --> 01:01:01,500", srt);
    }

    // ================================================================
    // Spec-conformance tests for WriteJson
    // (docs/spec/phoneme-timing-contract.toml v1.0)
    // ================================================================

    /// <summary>
    /// Helper: synthesize 2 simple entries (a=10 frames, k=5 frames at 22050/256).
    /// </summary>
    private static List<TimingWriter.PhonemeTimingEntry> SampleEntries()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];
        return TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);
    }

    /// <summary>
    /// Spec key 1: top-level <c>phonemes</c> field is present and an array.
    /// </summary>
    [Fact]
    public void WriteJson_OutputHasPhonemesField()
    {
        var entries = SampleEntries();

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        Assert.Equal(JsonValueKind.Object, root.ValueKind);
        Assert.True(root.TryGetProperty("phonemes", out var phonemes),
            "spec field 'phonemes' must be present");
        Assert.Equal(JsonValueKind.Array, phonemes.ValueKind);
        Assert.Equal(entries.Count, phonemes.GetArrayLength());
    }

    /// <summary>
    /// Spec key 2: top-level <c>total_duration_ms</c> field is present and numeric.
    /// </summary>
    [Fact]
    public void WriteJson_OutputHasTotalDurationMs()
    {
        var entries = SampleEntries();

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        Assert.True(root.TryGetProperty("total_duration_ms", out var total),
            "spec field 'total_duration_ms' must be present");
        Assert.Equal(JsonValueKind.Number, total.ValueKind);
        Assert.True(total.GetDouble() > 0d, "non-empty entries should yield positive total");
    }

    /// <summary>
    /// Spec key 3: top-level <c>sample_rate</c> field round-trips the value passed in.
    /// </summary>
    [Fact]
    public void WriteJson_OutputHasSampleRate()
    {
        var entries = SampleEntries();

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        Assert.True(root.TryGetProperty("sample_rate", out var sr),
            "spec field 'sample_rate' must be present");
        Assert.Equal(JsonValueKind.Number, sr.ValueKind);
        Assert.Equal(SampleRate, sr.GetInt32());
    }

    /// <summary>
    /// Spec key 4: each phoneme entry uses snake_case <c>start_ms / end_ms / duration_ms</c>
    /// (not <c>start / end / duration</c>).
    /// </summary>
    [Fact]
    public void WriteJson_PhonemeFieldsAreStartMsEndMsDurationMs()
    {
        var entries = SampleEntries();

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var phonemes = doc.RootElement.GetProperty("phonemes");

        for (int i = 0; i < phonemes.GetArrayLength(); i++)
        {
            var p = phonemes[i];
            Assert.True(p.TryGetProperty("phoneme", out _), $"entry[{i}] missing 'phoneme'");
            Assert.True(p.TryGetProperty("start_ms", out _), $"entry[{i}] missing 'start_ms'");
            Assert.True(p.TryGetProperty("end_ms", out _), $"entry[{i}] missing 'end_ms'");
            Assert.True(p.TryGetProperty("duration_ms", out _), $"entry[{i}] missing 'duration_ms'");
            // Legacy short names must NOT be present.
            Assert.False(p.TryGetProperty("start", out _), $"entry[{i}] has legacy 'start'");
            Assert.False(p.TryGetProperty("end", out _), $"entry[{i}] has legacy 'end'");
            Assert.False(p.TryGetProperty("duration", out _), $"entry[{i}] has legacy 'duration'");
        }
    }

    /// <summary>
    /// Spec requirement: serialized millisecond fields preserve at least
    /// 3 decimal digits of precision (matches Python <c>{:.3f}</c> and Rust
    /// <c>{:.3}</c> contracts).
    /// </summary>
    [Fact]
    public void WriteJson_MillisecondPrecision()
    {
        // Hand-craft an entry with sub-millisecond fractional times so that
        // dropping precision (e.g. integer rounding) would be detectable.
        var entries = new List<TimingWriter.PhonemeTimingEntry>
        {
            new("a", 11.609f, 23.219f, 11.610f), // 22050/256 ≈ 11.6099 ms/frame
        };

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var first = doc.RootElement.GetProperty("phonemes")[0];

        // Each ms field must keep ≥ 3 decimals of fidelity (within 0.0005 ms).
        Assert.Equal(11.609f, first.GetProperty("start_ms").GetSingle(), precision: 3);
        Assert.Equal(23.219f, first.GetProperty("end_ms").GetSingle(), precision: 3);
        Assert.Equal(11.610f, first.GetProperty("duration_ms").GetSingle(), precision: 3);

        // The serialized text must contain a decimal point — guards against
        // any future regression that emits integer-only timestamps.
        ms.Position = 0;
        using var reader = new StreamReader(ms, Encoding.UTF8);
        string json = reader.ReadToEnd();
        Assert.Contains(".", json);
    }

    /// <summary>
    /// Spec [calculation.cursor_walk]: <c>total_duration_ms</c> equals the
    /// last (max) <c>end_ms</c> — the cursor's final position.
    /// </summary>
    [Fact]
    public void WriteJson_TotalDurationMs_EqualsLastEndMs()
    {
        var entries = SampleEntries();
        Assert.NotEmpty(entries);
        float expectedTotal = entries[^1].EndMs;

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries, SampleRate);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        double actualTotal = root.GetProperty("total_duration_ms").GetDouble();
        Assert.Equal(expectedTotal, (float)actualTotal, precision: 3);

        // And the last phoneme's end_ms in the JSON must match.
        var phonemes = root.GetProperty("phonemes");
        double lastEndMs = phonemes[phonemes.GetArrayLength() - 1]
            .GetProperty("end_ms").GetDouble();
        Assert.Equal(expectedTotal, (float)lastEndMs, precision: 3);
        Assert.Equal(actualTotal, lastEndMs, precision: 3);
    }

    // ================================================================
    // Length-mismatch validation (spec [validation.length_consistency]):
    // phoneme_tokens.Length != durations.Length must throw, not silent
    // truncate. Cross-runtime parity with Rust/Python/Go.
    // ================================================================

    [Fact]
    public void CalculateTiming_LengthMismatch_DurationsShorter_Throws()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12, 10];
        float[] durations = [5f, 3f]; // intentionally shorter

        var ex = Assert.Throws<ArgumentException>(() =>
            TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize));

        Assert.Equal("durations", ex.ParamName);
        Assert.Contains("durations length (2)", ex.Message);
        Assert.Contains("phoneme_tokens length (3)", ex.Message);
    }

    [Fact]
    public void CalculateTiming_LengthMismatch_PhonemesShorter_Throws()
    {
        var map = MakeMap();
        long[] phonemeIds = [10];
        float[] durations = [5f, 3f, 2f]; // intentionally longer

        var ex = Assert.Throws<ArgumentException>(() =>
            TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize));

        Assert.Equal("durations", ex.ParamName);
        Assert.Contains("durations length (3)", ex.Message);
        Assert.Contains("phoneme_tokens length (1)", ex.Message);
    }
}
