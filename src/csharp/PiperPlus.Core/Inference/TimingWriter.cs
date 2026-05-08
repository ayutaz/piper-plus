using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Computes per-phoneme timing from the ONNX <c>durations</c> output tensor and
/// writes the result as JSON, TSV, or SRT.
/// </summary>
/// <remarks>
/// <para>
/// Conforms to <c>docs/spec/phoneme-timing-contract.toml</c> v1.0:
/// fields are <c>start_ms</c>, <c>end_ms</c>, <c>duration_ms</c> (snake_case,
/// milliseconds) and three output formats — JSON, TSV, SRT.
/// </para>
/// <para>
/// Each element <c>durations[i]</c> is the number of spectrogram frames
/// assigned to <c>phonemeIds[i]</c>. <c>hopSize / sampleRate * 1000</c>
/// converts a frame count to milliseconds.
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
    /// <param name="StartMs">Start time in milliseconds from the beginning of the utterance.</param>
    /// <param name="EndMs">End time in milliseconds from the beginning of the utterance.</param>
    /// <param name="DurationMs">Duration in milliseconds (<c>EndMs - StartMs</c>).</param>
    public record PhonemeTimingEntry(
        string Phoneme,
        float StartMs,
        float EndMs,
        float DurationMs);

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

        // spec [validation.length_consistency]: phoneme_tokens (when provided)
        // and durations must have the same length. Cross-runtime parity:
        //   - Rust:   src/rust/piper-core/src/timing.rs:95-99
        //   - Python: src/python_run/piper/timing.py:99-101 (ValueError)
        //   - Go:     src/go/piperplus/timing.go:33-34
        // ArgumentException is the .NET equivalent of Python ValueError.
        if (phonemeIds.Length != durations.Length)
            throw new ArgumentException(
                $"durations length ({durations.Length}) != phoneme_tokens length ({phonemeIds.Length})",
                nameof(durations));

        if (sampleRate <= 0)
            throw new ArgumentOutOfRangeException(nameof(sampleRate), "Sample rate must be positive.");
        if (hopSize <= 0)
            throw new ArgumentOutOfRangeException(nameof(hopSize), "Hop size must be positive.");

        // Build reverse map: phoneme ID -> human-readable string.
        var idToString = BuildReverseIdMap(phonemeIdMap);

        // frame_time_ms = (hop_size / sample_rate) * 1000
        // — see docs/spec/phoneme-timing-contract.toml [calculation].
        float frameLengthMs = (float)hopSize / sampleRate * 1000f;
        float currentTimeMs = 0f;
        int count = phonemeIds.Length;
        var entries = new List<PhonemeTimingEntry>(count);

        for (int i = 0; i < count; i++)
        {
            long id = phonemeIds[i];
            // Negative durations are clamped to 0 — matches Python canonical
            // (durations_to_timing) and the cross-runtime golden fixture.
            float frameDuration = Math.Max(0f, durations[i]);

            // Skip special tokens (PAD=0, BOS=1, EOS=2) — advance clock only.
            if (id is 0 or 1 or 2)
            {
                currentTimeMs += frameDuration * frameLengthMs;
                continue;
            }

            float startMs = currentTimeMs;
            currentTimeMs += frameDuration * frameLengthMs;
            float endMs = currentTimeMs;

            string phonemeStr = ResolvePhonemeString(id, idToString);

            entries.Add(new PhonemeTimingEntry(
                phonemeStr,
                startMs,
                endMs,
                endMs - startMs));
        }

        return entries;
    }

    // ------------------------------------------------------------------
    // JSON output
    // ------------------------------------------------------------------

    /// <summary>
    /// Sentinel sample-rate value used by the legacy 2-arg
    /// <see cref="WriteJson(string, List{PhonemeTimingEntry})"/> /
    /// <see cref="WriteJson(Stream, List{PhonemeTimingEntry})"/> overloads
    /// when the caller did not supply a sample rate. Encoded as
    /// <c>"sample_rate": 0</c> in the output JSON to signal "unknown".
    /// </summary>
    public const int UnknownSampleRate = 0;

    /// <summary>
    /// Writes timing entries to the specified file path as spec-conforming JSON.
    /// </summary>
    /// <remarks>
    /// Spec-conforming object shape (<c>docs/spec/phoneme-timing-contract.toml</c>
    /// <c>[output_formats.json_pretty]</c>, snake_case, milliseconds):
    /// <code>
    /// {
    ///   "phonemes": [
    ///     {"phoneme": "^", "start_ms": 0.0, "end_ms": 58.0, "duration_ms": 58.0},
    ///     ...
    ///   ],
    ///   "total_duration_ms": 580.4988,
    ///   "sample_rate": 22050
    /// }
    /// </code>
    /// <para>
    /// <c>total_duration_ms</c> is the maximum <c>end_ms</c> across the entries
    /// (cursor-walk semantics), or <c>0</c> when the list is empty.
    /// </para>
    /// <para>
    /// Uses the source-generated <see cref="TimingJsonContext"/> for trim-safe serialization.
    /// </para>
    /// </remarks>
    public static void WriteJson(string filePath, List<PhonemeTimingEntry> entries, int sampleRate)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("File path must not be empty.", nameof(filePath));
        ArgumentNullException.ThrowIfNull(entries);

        var result = ConvertToResultDto(entries, sampleRate);
        using var stream = new FileStream(filePath, FileMode.Create, FileAccess.Write);
        JsonSerializer.Serialize(stream, result, TimingJsonContext.Default.TimingResultDto);
    }

    /// <summary>
    /// Writes timing entries to the given stream as spec-conforming JSON
    /// (<c>{phonemes, total_duration_ms, sample_rate}</c>).
    /// </summary>
    public static void WriteJson(Stream stream, List<PhonemeTimingEntry> entries, int sampleRate)
    {
        ArgumentNullException.ThrowIfNull(stream);
        ArgumentNullException.ThrowIfNull(entries);

        var result = ConvertToResultDto(entries, sampleRate);
        JsonSerializer.Serialize(stream, result, TimingJsonContext.Default.TimingResultDto);
    }

    /// <summary>
    /// Backward-compatible overload: emits spec-conforming JSON with
    /// <c>sample_rate</c> set to the <see cref="UnknownSampleRate"/> sentinel.
    /// </summary>
    /// <remarks>
    /// Existing pre-spec callers used the 2-argument signature without a sample
    /// rate. To avoid a breaking change, the call still emits the canonical
    /// <c>{phonemes, total_duration_ms, sample_rate}</c> shape, but with
    /// <c>"sample_rate": 0</c>. New code should pass an explicit sample rate.
    /// </remarks>
    public static void WriteJson(string filePath, List<PhonemeTimingEntry> entries)
        => WriteJson(filePath, entries, UnknownSampleRate);

    /// <inheritdoc cref="WriteJson(string, List{PhonemeTimingEntry})"/>
    public static void WriteJson(Stream stream, List<PhonemeTimingEntry> entries)
        => WriteJson(stream, entries, UnknownSampleRate);

    // ------------------------------------------------------------------
    // TSV output
    // ------------------------------------------------------------------

    /// <summary>
    /// Writes timing entries as a TSV (tab-separated values) file.
    /// </summary>
    /// <remarks>
    /// Spec-conforming format (column header in milliseconds):
    /// <code>
    /// start_ms	end_ms	duration_ms	phoneme
    /// 0.000	58.000	58.000	^
    /// 58.000	150.800	92.800	k
    /// </code>
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
                StartMs = MathF.Round(e.StartMs, 3),
                EndMs = MathF.Round(e.EndMs, 3),
                DurationMs = MathF.Round(e.DurationMs, 3),
            });
        }

        return dtos;
    }

    /// <summary>
    /// Builds the spec-conforming <see cref="TimingResultDto"/>:
    /// <c>{phonemes:[…], total_duration_ms, sample_rate}</c>.
    /// </summary>
    /// <remarks>
    /// <c>total_duration_ms</c> is the maximum <c>end_ms</c> over the
    /// entries (matching the cursor-walk algorithm in
    /// <see cref="CalculateTiming"/> where each phoneme's <c>end_ms</c> is
    /// the running cursor). For an empty list the value is <c>0</c>.
    /// The <c>double</c> field type preserves sub-millisecond precision
    /// (≥ 3 decimal digits) without the <c>float</c> rounding that the
    /// per-phoneme entries undergo.
    /// </remarks>
    private static TimingResultDto ConvertToResultDto(
        List<PhonemeTimingEntry> entries,
        int sampleRate)
    {
        var phonemes = ConvertToDtos(entries);

        double totalDurationMs = 0d;
        foreach (var e in entries)
        {
            // cursor-walk: total = max end_ms (the last non-empty entry's end).
            // Use double to keep sub-ms precision intact.
            double endMs = e.EndMs;
            if (endMs > totalDurationMs)
            {
                totalDurationMs = endMs;
            }
        }

        return new TimingResultDto
        {
            Phonemes = phonemes,
            TotalDurationMs = Math.Round(totalDurationMs, 3),
            SampleRate = sampleRate,
        };
    }

    private static void WriteTsvCore(StreamWriter writer, List<PhonemeTimingEntry> entries)
    {
        // Spec column header (docs/spec/phoneme-timing-contract.toml [output_formats.tsv]).
        writer.WriteLine("start_ms\tend_ms\tduration_ms\tphoneme");

        foreach (var e in entries)
        {
            writer.Write(e.StartMs.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.Write(e.EndMs.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.Write(e.DurationMs.ToString("F3", System.Globalization.CultureInfo.InvariantCulture));
            writer.Write('\t');
            writer.WriteLine(EscapeForTsv(e.Phoneme));
        }
    }

    private static string EscapeForTsv(string phoneme)
    {
        if (string.IsNullOrEmpty(phoneme))
        {
            return phoneme;
        }
        // Spec [output_formats.tsv].escape_tab/newline_in_phoneme.
        if (phoneme.IndexOf('\t') < 0 && phoneme.IndexOf('\n') < 0)
        {
            return phoneme;
        }
        return phoneme.Replace("\t", "\\t").Replace("\n", "\\n");
    }

    // ------------------------------------------------------------------
    // SRT output (docs/spec/phoneme-timing-contract.toml [output_formats.srt])
    // ------------------------------------------------------------------

    /// <summary>
    /// Writes timing entries as SubRip (SRT) subtitle text to the given file.
    /// </summary>
    /// <remarks>
    /// Format (1-indexed cues, <c>HH:MM:SS,mmm</c> timestamps):
    /// <code>
    /// 1
    /// 00:00:00,000 --> 00:00:00,058
    /// ^
    ///
    /// 2
    /// 00:00:00,058 --> 00:00:00,151
    /// k
    /// </code>
    /// </remarks>
    public static void WriteSrt(string filePath, List<PhonemeTimingEntry> entries)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("File path must not be empty.", nameof(filePath));
        ArgumentNullException.ThrowIfNull(entries);

        // Use BOM-less UTF-8 — SRT players often choke on the BOM and the
        // spec output examples are byte-clean.
        using var writer = new StreamWriter(
            filePath,
            append: false,
            encoding: new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        WriteSrtCore(writer, entries);
    }

    /// <summary>
    /// Writes timing entries as SRT subtitle text to the given stream.
    /// </summary>
    public static void WriteSrt(Stream stream, List<PhonemeTimingEntry> entries)
    {
        ArgumentNullException.ThrowIfNull(stream);
        ArgumentNullException.ThrowIfNull(entries);

        using var writer = new StreamWriter(
            stream,
            encoding: new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
            leaveOpen: true);
        WriteSrtCore(writer, entries);
    }

    private static void WriteSrtCore(StreamWriter writer, List<PhonemeTimingEntry> entries)
    {
        for (int i = 0; i < entries.Count; i++)
        {
            var e = entries[i];
            writer.WriteLine((i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture));
            writer.Write(FormatSrtTimestamp(e.StartMs));
            writer.Write(" --> ");
            writer.WriteLine(FormatSrtTimestamp(e.EndMs));
            writer.WriteLine(e.Phoneme);
            writer.WriteLine();
        }
    }

    private static string FormatSrtTimestamp(float ms)
    {
        // Clamp negatives that may have leaked through.
        if (ms < 0f)
        {
            ms = 0f;
        }
        long total_ms = (long)Math.Round(ms);
        long hours = total_ms / 3_600_000L;
        long remainder = total_ms % 3_600_000L;
        long minutes = remainder / 60_000L;
        remainder %= 60_000L;
        long seconds = remainder / 1_000L;
        long millis = remainder % 1_000L;
        return string.Format(
            System.Globalization.CultureInfo.InvariantCulture,
            "{0:D2}:{1:D2}:{2:D2},{3:D3}",
            hours, minutes, seconds, millis);
    }
}

// ------------------------------------------------------------------
// JSON serialization support (source-generated, trim-safe)
// ------------------------------------------------------------------

/// <summary>
/// DTO for a single phoneme entry. Snake_case property names match
/// <c>docs/spec/phoneme-timing-contract.toml</c> v1.0
/// (<c>[types.phoneme_timing_info]</c>).
/// </summary>
internal sealed class TimingDto
{
    [JsonPropertyName("phoneme")]
    public string Phoneme { get; set; } = string.Empty;

    [JsonPropertyName("start_ms")]
    public float StartMs { get; set; }

    [JsonPropertyName("end_ms")]
    public float EndMs { get; set; }

    [JsonPropertyName("duration_ms")]
    public float DurationMs { get; set; }
}

/// <summary>
/// DTO for the top-level timing result, matching the spec
/// <c>{phonemes, total_duration_ms, sample_rate}</c>
/// (<c>docs/spec/phoneme-timing-contract.toml [types.timing_result]</c>).
/// </summary>
internal sealed class TimingResultDto
{
    [JsonPropertyName("phonemes")]
    public List<TimingDto> Phonemes { get; set; } = [];

    [JsonPropertyName("total_duration_ms")]
    public double TotalDurationMs { get; set; }

    [JsonPropertyName("sample_rate")]
    public int SampleRate { get; set; }
}

/// <summary>
/// Source-generated JSON serializer context for <see cref="TimingDto"/>
/// and <see cref="TimingResultDto"/>. Ensures trim-safe / AOT-safe
/// serialization without reflection.
/// </summary>
[JsonSerializable(typeof(List<TimingDto>))]
[JsonSerializable(typeof(TimingResultDto))]
[JsonSourceGenerationOptions(WriteIndented = true)]
internal partial class TimingJsonContext : JsonSerializerContext;
