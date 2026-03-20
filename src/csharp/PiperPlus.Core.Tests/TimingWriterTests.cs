using System.Text;
using System.Text.Json;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="TimingWriter"/>.
/// Covers timing calculation, special-token skipping, PUA reverse mapping,
/// JSON/TSV serialization, and edge cases.
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
        ["\uE000"] = [17], // PUA for "a:"
        ["\uE019"] = [40], // PUA for "N_m"
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
        float frameLength = (float)HopSize / SampleRate;

        // Two regular phonemes: a (10 frames), k (5 frames)
        long[] phonemeIds = [10, 12];
        float[] durations = [10f, 5f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        Assert.Equal(2, entries.Count);

        // First entry: "a", starts at 0, ends at 10 * frameLength
        Assert.Equal("a", entries[0].Phoneme);
        Assert.Equal(0f, entries[0].StartSeconds, precision: 5);
        Assert.Equal(10f * frameLength, entries[0].EndSeconds, precision: 5);
        Assert.Equal(10f * frameLength, entries[0].DurationSeconds, precision: 5);

        // Second entry: "k", starts where "a" ended
        Assert.Equal("k", entries[1].Phoneme);
        Assert.Equal(10f * frameLength, entries[1].StartSeconds, precision: 5);
        Assert.Equal(15f * frameLength, entries[1].EndSeconds, precision: 5);
        Assert.Equal(5f * frameLength, entries[1].DurationSeconds, precision: 5);
    }

    // ================================================================
    // 2. CalculateTiming_SkipsSpecialTokens
    // ================================================================

    [Fact]
    public void CalculateTiming_SkipsSpecialTokens()
    {
        var map = MakeMap();
        float frameLength = (float)HopSize / SampleRate;

        // Sequence: PAD(0), BOS(1), a(10), EOS(2)
        long[] phonemeIds = [0, 1, 10, 2];
        float[] durations = [2f, 3f, 4f, 1f];

        var entries = TimingWriter.CalculateTiming(phonemeIds, durations, map, SampleRate, HopSize);

        // Only "a" should appear -- PAD, BOS, EOS are skipped.
        Assert.Single(entries);
        Assert.Equal("a", entries[0].Phoneme);

        // "a" starts after PAD (2 frames) + BOS (3 frames) = 5 frames
        float expectedStart = 5f * frameLength;
        Assert.Equal(expectedStart, entries[0].StartSeconds, precision: 5);
        Assert.Equal(expectedStart + 4f * frameLength, entries[0].EndSeconds, precision: 5);
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
    // 4. WriteJson_ValidOutput
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

        // First element
        var first = root[0];
        Assert.Equal("a", first.GetProperty("phoneme").GetString());
        Assert.True(first.TryGetProperty("start", out _));
        Assert.True(first.TryGetProperty("end", out _));
        Assert.True(first.TryGetProperty("duration", out _));

        // Second element
        var second = root[1];
        Assert.Equal("k", second.GetProperty("phoneme").GetString());
        Assert.True(second.GetProperty("end").GetSingle() > second.GetProperty("start").GetSingle());
    }

    // ================================================================
    // 5. WriteTsv_ValidOutput
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

        // Header columns
        Assert.Equal("start\tend\tduration\tphoneme", lines[0].TrimEnd('\r'));

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
}
