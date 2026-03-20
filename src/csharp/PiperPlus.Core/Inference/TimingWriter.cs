using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Computes per-phoneme timing from the ONNX <c>durations</c> output tensor and
/// writes the result as JSON or TSV.
/// </summary>
/// <remarks>
/// <para>
/// This mirrors the C++ implementation in <c>piper.cpp:extractTimingsFromDurations</c>
/// and <c>outputTimingsAsJSON</c> / <c>outputTimingsAsTSV</c>.
/// </para>
/// <para>
/// Each element <c>durations[i]</c> is the number of spectrogram frames assigned to
/// <c>phonemeIds[i]</c>. Multiplying by <c>hopSize / sampleRate</c> converts frames
/// to seconds.
/// </para>
/// </remarks>
public static class TimingWriter
{
    // ------------------------------------------------------------------
    // Data types
    // ------------------------------------------------------------------

    /// <summary>
    /// One phoneme's start / end timing, calculated from the model's duration output.
    /// </summary>
    /// <param name="Phoneme">Human-readable phoneme string (PUA codepoints are resolved to multi-char tokens like <c>a:</c>).</param>
    /// <param name="StartSeconds">Start time in seconds from the beginning of the utterance.</param>
    /// <param name="EndSeconds">End time in seconds from the beginning of the utterance.</param>
    /// <param name="DurationSeconds">Duration in seconds (<c>EndSeconds - StartSeconds</c>).</param>
    public record PhonemeTimingEntry(
        string Phoneme,
        float StartSeconds,
        float EndSeconds,
        float DurationSeconds);

    // ------------------------------------------------------------------
    // Calculation
    // ------------------------------------------------------------------

    /// <summary>
    /// Converts per-phoneme frame counts into absolute timestamps.
    /// </summary>
    /// <param name="phonemeIds">
    /// Phoneme ID sequence that was fed to the model (same order as <paramref name="durations"/>).
    /// </param>
    /// <param name="durations">
    /// Frame-count array produced by the ONNX model's <c>durations</c> output tensor.
    /// <c>durations[i]</c> is the number of spectrogram frames for <c>phonemeIds[i]</c>.
    /// </param>
    /// <param name="phonemeIdMap">
    /// The <c>phoneme_id_map</c> from <c>config.json</c>.
    /// Keys are phoneme strings; values are arrays whose first element is the integer ID.
    /// </param>
    /// <param name="sampleRate">Audio sample rate in Hz (e.g. 22050).</param>
    /// <param name="hopSize">
    /// Spectrogram hop size in samples. Defaults to 256, matching the standard Piper config.
    /// </param>
    /// <returns>Ordered list of <see cref="PhonemeTimingEntry"/> for non-special phonemes.</returns>
    /// <remarks>
    /// Special tokens (PAD=0, BOS=1, EOS=2) are skipped — their frame durations still
    /// advance the clock but produce no output entry, matching the C++ behaviour.
    /// </remarks>
    public static List<PhonemeTimingEntry> CalculateTiming(
        long[] phonemeIds,
        float[] durations,
        Dictionary<string, int[]> phonemeIdMap,
        int sampleRate,
        int hopSize = 256)
    {
        ArgumentNullException.ThrowIfNull(phonemeIds);
        ArgumentNullException.ThrowIfNull(durations);
        ArgumentNullException.ThrowIfNull(phonemeIdMap);

        if (sampleRate <= 0)
            throw new ArgumentOutOfRangeException(nameof(sampleRate), "Sample rate must be positive.");
        if (hopSize <= 0)
            throw new ArgumentOutOfRangeException(nameof(hopSize), "Hop size must be positive.");

        // Build reverse map: phoneme ID -> human-readable string.
        var idToString = BuildReverseIdMap(phonemeIdMap);

        float frameLength = (float)hopSize / sampleRate;
        float currentTime = 0f;
        int count = Math.Min(phonemeIds.Length, durations.Length);
        var entries = new List<PhonemeTimingEntry>(count);

        for (int i = 0; i < count; i++)
        {
            long id = phonemeIds[i];
            float frameDuration = durations[i];

            // Skip special tokens (PAD=0, BOS=1, EOS=2) — advance clock only.
            if (id is 0 or 1 or 2)
            {
                currentTime += frameDuration * frameLength;
                continue;
            }

            float startTime = currentTime;
            currentTime += frameDuration * frameLength;
            float endTime = currentTime;

            string phonemeStr = ResolvePhonemeString(id, idToString);

            entries.Add(new PhonemeTimingEntry(
                phonemeStr,
                startTime,
                endTime,
                endTime - startTime));
        }

        return entries;
    }

    // ------------------------------------------------------------------
    // JSON output
    // ------------------------------------------------------------------

    /// <summary>
    /// Writes timing entries as a JSON array to the specified file path.
    /// </summary>
    /// <remarks>
    /// Format:
    /// <code>
    /// [
    ///   {"phoneme": "^", "start": 0.0, "end": 0.058, "duration": 0.058},
    ///   ...
    /// ]
    /// </code>
    /// Uses the source-generated <see cref="TimingJsonContext"/> for trim-safe serialization.
    /// </remarks>
    public static void WriteJson(string filePath, List<PhonemeTimingEntry> entries)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("File path must not be empty.", nameof(filePath));
        ArgumentNullException.ThrowIfNull(entries);

        var dtos = ConvertToDtos(entries);
        using var stream = new FileStream(filePath, FileMode.Create, FileAccess.Write);
        JsonSerializer.Serialize(stream, dtos, TimingJsonContext.Default.ListTimingDto);
    }

    /// <summary>
    /// Writes timing entries as a JSON array to the given stream.
    /// </summary>
    public static void WriteJson(Stream stream, List<PhonemeTimingEntry> entries)
    {
        ArgumentNullException.ThrowIfNull(stream);
        ArgumentNullException.ThrowIfNull(entries);

        var dtos = ConvertToDtos(entries);
        JsonSerializer.Serialize(stream, dtos, TimingJsonContext.Default.ListTimingDto);
    }

    // ------------------------------------------------------------------
    // TSV output
    // ------------------------------------------------------------------

    /// <summary>
    /// Writes timing entries as a TSV (tab-separated values) file.
    /// </summary>
    /// <remarks>
    /// Format:
    /// <code>
    /// start	end	duration	phoneme
    /// 0.000	0.058	0.058	^
    /// 0.058	0.116	0.058	k
    /// </code>
    /// Matches the C++ <c>outputTimingsAsTSV</c> column order.
    /// </remarks>
    public static void WriteTsv(string filePath, List<PhonemeTimingEntry> entries)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("File path must not be empty.", nameof(filePath));
        ArgumentNullException.ThrowIfNull(entries);

        using var writer = new StreamWriter(filePath, append: false, encoding: System.Text.Encoding.UTF8);
        WriteTsvCore(writer, entries);
    }

    /// <summary>
    /// Writes timing entries as TSV to the given stream.
    /// </summary>
    public static void WriteTsv(Stream stream, List<PhonemeTimingEntry> entries)
    {
        ArgumentNullException.ThrowIfNull(stream);
        ArgumentNullException.ThrowIfNull(entries);

        using var writer = new StreamWriter(stream, encoding: System.Text.Encoding.UTF8, leaveOpen: true);
        WriteTsvCore(writer, entries);
    }

    // ------------------------------------------------------------------
    // Static caches
    // ------------------------------------------------------------------

    private static readonly string[] s_asciiStrings = InitAsciiStrings();

    private static string[] InitAsciiStrings()
    {
        var arr = new string[128];
        for (int i = 0; i < 128; i++)
            arr[i] = ((char)i).ToString();
        return arr;
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Builds a reverse lookup from integer phoneme ID to display string.
    /// PUA codepoints (U+E000..U+E01C) are decoded to their multi-character
    /// equivalents using <see cref="Mapping.OpenJTalkToPiperMapping.CharToToken"/>.
    /// </summary>
    private static Dictionary<long, string> BuildReverseIdMap(
        Dictionary<string, int[]> phonemeIdMap)
    {
        var reverse = new Dictionary<long, string>(phonemeIdMap.Count);
        foreach (var (phonemeStr, ids) in phonemeIdMap)
        {
            if (ids is { Length: > 0 })
            {
                // Resolve PUA single-char keys to human-readable multi-char tokens.
                string display = phonemeStr;
                if (phonemeStr.Length == 1)
                {
                    char ch = phonemeStr[0];
                    if (Mapping.OpenJTalkToPiperMapping.CharToToken.TryGetValue(ch, out var token))
                    {
                        display = token;
                    }
                }

                reverse.TryAdd(ids[0], display);
            }
        }

        return reverse;
    }

    /// <summary>
    /// Resolves a phoneme ID to its display string.
    /// Falls back to <c>"?"</c> for unknown IDs, matching the C++ <c>UNKNOWN_PHONEME</c>.
    /// </summary>
    private static string ResolvePhonemeString(long id, Dictionary<long, string> idToString)
    {
        if (idToString.TryGetValue(id, out var str))
        {
            return str;
        }

        // Fallback: printable ASCII characters (cached to avoid per-call allocation).
        return id is > 2 and < 128 ? s_asciiStrings[id] : "?";
    }

    private static List<TimingDto> ConvertToDtos(List<PhonemeTimingEntry> entries)
    {
        var dtos = new List<TimingDto>(entries.Count);
        foreach (var e in entries)
        {
            dtos.Add(new TimingDto
            {
                Phoneme = e.Phoneme,
                Start = MathF.Round(e.StartSeconds, 3),
                End = MathF.Round(e.EndSeconds, 3),
                Duration = MathF.Round(e.DurationSeconds, 3),
            });
        }

        return dtos;
    }

    private static void WriteTsvCore(StreamWriter writer, List<PhonemeTimingEntry> entries)
    {
        writer.WriteLine("start\tend\tduration\tphoneme");

        foreach (var e in entries)
        {
            writer.Write(e.StartSeconds.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.Write(e.EndSeconds.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.Write(e.DurationSeconds.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.WriteLine(e.Phoneme);
        }
    }
}

// ------------------------------------------------------------------
// JSON serialization support (source-generated, trim-safe)
// ------------------------------------------------------------------

/// <summary>
/// DTO for JSON serialization with snake_case property names.
/// </summary>
internal sealed class TimingDto
{
    [JsonPropertyName("phoneme")]
    public string Phoneme { get; set; } = string.Empty;

    [JsonPropertyName("start")]
    public float Start { get; set; }

    [JsonPropertyName("end")]
    public float End { get; set; }

    [JsonPropertyName("duration")]
    public float Duration { get; set; }
}

/// <summary>
/// Source-generated JSON serializer context for <see cref="TimingDto"/>.
/// Ensures trim-safe / AOT-safe serialization without reflection.
/// </summary>
[JsonSerializable(typeof(List<TimingDto>))]
[JsonSourceGenerationOptions(WriteIndented = true)]
internal partial class TimingJsonContext : JsonSerializerContext;
