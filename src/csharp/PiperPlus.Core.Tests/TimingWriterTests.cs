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
    // 4. WriteJson_ValidOutput (snake_case ms keys per spec)
    // ================================================================

    [Fact]
    public void WriteJson_ValidOutput()
    {
        var map = MakeMap();
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        using var ms = new MemoryStream();
        TimingWriter.WriteJson(ms, entries);

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;

        // Output is a JSON array of timing objects.
        Assert.Equal(JsonValueKind.Array, root.ValueKind);
        Assert.Equal(2, root.GetArrayLength());

        // First element — spec field names
        var first = root[0];
        Assert.Equal("a", first.GetProperty("phoneme").GetString());
        Assert.True(first.TryGetProperty("start_ms", out _));
        Assert.True(first.TryGetProperty("end_ms", out _));
        Assert.True(first.TryGetProperty("duration_ms", out _));
        // Legacy field names must NOT appear (spec compliance)
        Assert.False(first.TryGetProperty("start", out _));
        Assert.False(first.TryGetProperty("end", out _));
        Assert.False(first.TryGetProperty("duration", out _));

        // Second element
        var second = root[1];
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
        TimingWriter.WriteJson(ms, entries);

        // Verify valid JSON was written to the stream.
        Assert.True(ms.Length > 0, "Stream should contain JSON data");

        ms.Position = 0;
        using var doc = JsonDocument.Parse(ms);
        var root = doc.RootElement;
        Assert.Equal(JsonValueKind.Array, root.ValueKind);
        Assert.Equal(1, root.GetArrayLength());
        Assert.Equal("a", root[0].GetProperty("phoneme").GetString());
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
}
