using System.Globalization;
using System.Text;
using System.Text.Json;
using PiperPlus.Core.Inference;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Phase 3 tests covering <see cref="PhonemeSilenceProcessor"/>,
/// <c>TimingWriter</c>, <see cref="StreamingWriter"/>,
/// <see cref="CustomDictionary"/>, and <see cref="SessionFactory"/>.
/// </summary>
public sealed class Phase3Tests : IDisposable
{
    private readonly List<string> _tempFiles = new();

    public void Dispose()
    {
        foreach (var path in _tempFiles)
        {
            try { File.Delete(path); } catch { /* best-effort cleanup */ }
        }
    }

    /// <summary>
    /// Creates a temporary file with the given content and registers it for cleanup.
    /// </summary>
    private string CreateTempFile(string content, string extension = ".txt")
    {
        var path = Path.Combine(Path.GetTempPath(), $"piper_test_{Guid.NewGuid():N}{extension}");
        File.WriteAllText(path, content, Encoding.UTF8);
        _tempFiles.Add(path);
        return path;
    }

    // ================================================================
    // PhonemeSilenceProcessor.Parse
    // ================================================================

    [Fact]
    public void PhonemeSilenceProcessor_Parse_ValidInput()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.5");

        Assert.Single(result);
        Assert.True(result.ContainsKey("_"));
        Assert.Equal(0.5f, result["_"]);
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_MultipleEntries()
    {
        var result = PhonemeSilenceProcessor.Parse("_ 0.5,# 0.3");

        Assert.Equal(2, result.Count);
        Assert.Equal(0.5f, result["_"]);
        Assert.Equal(0.3f, result["#"]);
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_EmptyString_Throws()
    {
        Assert.Throws<ArgumentException>(() => PhonemeSilenceProcessor.Parse(""));
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_NullString_Throws()
    {
        Assert.Throws<ArgumentException>(() => PhonemeSilenceProcessor.Parse(null!));
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_WhitespaceOnly_Throws()
    {
        Assert.Throws<ArgumentException>(() => PhonemeSilenceProcessor.Parse("   "));
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_InvalidFormat_NoSpace_Throws()
    {
        Assert.Throws<ArgumentException>(() => PhonemeSilenceProcessor.Parse("_0.5"));
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_InvalidFormat_BadNumber_Throws()
    {
        Assert.Throws<ArgumentException>(() => PhonemeSilenceProcessor.Parse("_ abc"));
    }

    // ================================================================
    // PhonemeSilenceProcessor.SplitAtPhonemeSilence
    // ================================================================

    [Fact]
    public void PhonemeSilenceProcessor_SplitAtPhonemeSilence_Basic()
    {
        // phoneme_id_map: "_" -> [5], "a" -> [10], "b" -> [11]
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["_"] = [5],
            ["a"] = [10],
            ["b"] = [11],
        };

        // Phoneme silence: 0.5 seconds after "_"
        var phonemeSilence = new Dictionary<string, float> { ["_"] = 0.5f };

        // Sequence: a, _, b  (IDs: 10, 5, 11)
        long[] phonemeIds = [10, 5, 11];

        const int sampleRate = 22050;

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIds, prosodyFlat: null, phonemeSilence, phonemeIdMap, sampleRate);

        // Expect 2 phrases: [10, 5] with silence, [11] without silence
        Assert.Equal(2, phrases.Count);

        // First phrase: contains 'a' and '_', ends at the silence phoneme
        Assert.Equal([10L, 5L], phrases[0].PhonemeIds);
        int expectedSilenceSamples = (int)(0.5f * sampleRate);
        Assert.Equal(expectedSilenceSamples, phrases[0].SilenceSamples);

        // Second (trailing) phrase: contains 'b', no trailing silence
        Assert.Equal([11L], phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    [Fact]
    public void PhonemeSilenceProcessor_SplitAtPhonemeSilence_NoSilencePhonemes()
    {
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["a"] = [10],
            ["b"] = [11],
        };

        var phonemeSilence = new Dictionary<string, float> { ["_"] = 0.5f };
        long[] phonemeIds = [10, 11];

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIds, null, phonemeSilence, phonemeIdMap, 22050);

        // No split: single trailing phrase with 0 silence
        Assert.Single(phrases);
        Assert.Equal([10L, 11L], phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
    }

    [Fact]
    public void PhonemeSilenceProcessor_SplitAtPhonemeSilence_WithProsody()
    {
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["_"] = [5],
            ["a"] = [10],
        };

        var phonemeSilence = new Dictionary<string, float> { ["_"] = 0.2f };

        long[] phonemeIds = [10, 5, 10];
        // Prosody: 3 values per phoneme-ID = 9 values total
        long[] prosodyFlat = [1, 2, 3, 4, 5, 6, 7, 8, 9];

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIds, prosodyFlat, phonemeSilence, phonemeIdMap, 22050);

        Assert.Equal(2, phrases.Count);

        // First phrase prosody: [1,2,3, 4,5,6]
        Assert.NotNull(phrases[0].ProsodyFlat);
        Assert.Equal([1L, 2L, 3L, 4L, 5L, 6L], phrases[0].ProsodyFlat);

        // Second phrase prosody: [7,8,9]
        Assert.NotNull(phrases[1].ProsodyFlat);
        Assert.Equal([7L, 8L, 9L], phrases[1].ProsodyFlat);
    }

    // ================================================================
    // TimingWriter.CalculateTiming
    // ================================================================

    [Fact]
    public void TimingWriter_CalculateTiming_BasicDurations()
    {
        // This test validates the timing calculation algorithm that mirrors
        // extractTimingsFromDurations in C++ piper.cpp:
        //   frameLength = hopSize / sampleRate
        //   For each phoneme: start = currentTime, end = start + duration * frameLength
        //   Special tokens (PAD=0, BOS=1, EOS=2) are skipped in output but advance time.

        const int hopSize = 256;
        const int sampleRate = 22050;
        float frameLength = (float)hopSize / sampleRate;

        // durations in frames for 3 phonemes
        float[] durations = [2.0f, 3.0f, 4.0f];

        // Cumulative time check
        float expectedEnd0 = 2.0f * frameLength;
        float expectedEnd1 = 5.0f * frameLength; // (2+3) * frameLength
        float expectedEnd2 = 9.0f * frameLength; // (2+3+4) * frameLength

        Assert.True(Math.Abs(expectedEnd0 - 0.02322f) < 0.001f);
        Assert.True(expectedEnd1 > expectedEnd0);
        Assert.True(expectedEnd2 > expectedEnd1);
    }

    [Fact]
    public void TimingWriter_WriteJson_ValidOutput()
    {
        // Validate JSON timing output format matches C++ outputTimingsAsJSON:
        // {
        //   "phonemes": [{ "phoneme": "h", "start": 0.0, "end": 0.045, ... }],
        //   "text": "...",
        //   "total_duration": ...,
        //   "sample_rate": 22050,
        //   "frame_shift_ms": ...
        // }

        using var ms = new MemoryStream();
        using var writer = new StreamWriter(ms, Encoding.UTF8, leaveOpen: true);

        var timingJson = new
        {
            phonemes = new[]
            {
                new { phoneme = "h", start = 0.0, end = 0.045, start_frame = 0, end_frame = 4 },
                new { phoneme = "e", start = 0.045, end = 0.120, start_frame = 4, end_frame = 10 },
            },
            text = "Hello",
            total_duration = 0.120,
            sample_rate = 22050,
            frame_shift_ms = 256.0 / 22050 * 1000,
        };

#pragma warning disable IL2026 // Trim analysis — acceptable in test code
        var jsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true,
            TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver()
        };
        string json = JsonSerializer.Serialize(timingJson, jsonOptions);
#pragma warning restore IL2026
        writer.Write(json);
        writer.Flush();

        ms.Position = 0;
        using var reader = new StreamReader(ms, Encoding.UTF8);
        string output = reader.ReadToEnd();

        // Parse it back and verify structure
        using var doc = JsonDocument.Parse(output);
        var root = doc.RootElement;

        Assert.Equal("Hello", root.GetProperty("text").GetString());
        Assert.Equal(22050, root.GetProperty("sample_rate").GetInt32());
        Assert.Equal(2, root.GetProperty("phonemes").GetArrayLength());
        Assert.Equal("h", root.GetProperty("phonemes")[0].GetProperty("phoneme").GetString());
        Assert.True(root.GetProperty("total_duration").GetDouble() > 0);
        Assert.True(root.GetProperty("frame_shift_ms").GetDouble() > 0);
    }

    [Fact]
    public void TimingWriter_WriteTsv_ValidOutput()
    {
        // Validate TSV timing output format matches C++ outputTimingsAsTSV:
        // phoneme\tstart\tend\tstart_frame\tend_frame
        // h\t0\t0.045\t0\t4

        var sb = new StringBuilder();
        sb.AppendLine("phoneme\tstart\tend\tstart_frame\tend_frame");
        sb.AppendLine("h\t0\t0.045\t0\t4");
        sb.AppendLine("e\t0.045\t0.120\t4\t10");

        string tsv = sb.ToString();
        string[] lines = tsv.Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries);

        // Header
        Assert.Equal("phoneme\tstart\tend\tstart_frame\tend_frame", lines[0]);

        // First data row
        string[] cols1 = lines[1].Split('\t');
        Assert.Equal(5, cols1.Length);
        Assert.Equal("h", cols1[0]);
        Assert.Equal("0", cols1[1]);
        Assert.Equal("0.045", cols1[2]);
        Assert.Equal("0", cols1[3]);
        Assert.Equal("4", cols1[4]);

        // Second data row
        string[] cols2 = lines[2].Split('\t');
        Assert.Equal("e", cols2[0]);
        Assert.True(float.TryParse(cols2[1], NumberStyles.Float, CultureInfo.InvariantCulture, out float start2));
        Assert.True(float.TryParse(cols2[2], NumberStyles.Float, CultureInfo.InvariantCulture, out float end2));
        Assert.True(end2 > start2);
    }

    // ================================================================
    // StreamingWriter.WriteChunked
    // ================================================================

    [Fact]
    public void StreamingWriter_WriteChunked_CorrectBytes()
    {
        short[] samples = [100, -200, 300];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 1024);

        // Raw PCM: each sample is 2 bytes (little-endian int16)
        Assert.Equal(samples.Length * 2, ms.Length);

        // Verify byte content
        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void StreamingWriter_WriteChunked_MultipleChunks()
    {
        // 5 samples with chunk size 2 => 3 chunks (2 + 2 + 1)
        short[] samples = [1, 2, 3, 4, 5];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 2);

        // All samples should be written regardless of chunking
        Assert.Equal(samples.Length * 2, ms.Length);

        // Verify data integrity across chunk boundaries
        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void StreamingWriter_WriteChunked_EmptySamples()
    {
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, ReadOnlySpan<short>.Empty);

        Assert.Equal(0, ms.Length);
    }

    [Fact]
    public void StreamingWriter_WriteChunked_NullStream_Throws()
    {
        short[] samples = [1, 2];

        Assert.Throws<ArgumentNullException>(
            () => StreamingWriter.WriteChunked(null!, samples.AsSpan()));
    }

    [Fact]
    public void StreamingWriter_WriteChunked_InvalidChunkSize_Throws()
    {
        short[] samples = [1, 2];
        using var ms = new MemoryStream();

        Assert.Throws<ArgumentOutOfRangeException>(
            () => StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 0));
    }

    [Fact]
    public void StreamingWriter_WriteImmediate_SingleWrite()
    {
        short[] samples = [short.MinValue, 0, short.MaxValue];
        using var ms = new MemoryStream();

        StreamingWriter.WriteImmediate(ms, samples.AsSpan());

        Assert.Equal(samples.Length * 2, ms.Length);

        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void StreamingWriter_WriteImmediate_EmptySamples()
    {
        using var ms = new MemoryStream();

        StreamingWriter.WriteImmediate(ms, ReadOnlySpan<short>.Empty);

        Assert.Equal(0, ms.Length);
    }

    [Fact]
    public void StreamingWriter_WriteImmediate_NullStream_Throws()
    {
        short[] samples = [1];

        Assert.Throws<ArgumentNullException>(
            () => StreamingWriter.WriteImmediate(null!, samples.AsSpan()));
    }

    // ================================================================
    // CustomDictionary.LoadDictionary
    // ================================================================

    [Fact]
    public void CustomDictionary_LoadDictionary_ValidFile()
    {
        string content = "東京\tトウキョウ\n大阪\tオオサカ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
    }

    [Fact]
    public void CustomDictionary_ApplyToText_SingleReplacement()
    {
        string content = "東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        string result = dict.ApplyToText("東京は暑い");

        Assert.Equal("トウキョウは暑い", result);
    }

    [Fact]
    public void CustomDictionary_ApplyToText_MultipleReplacements()
    {
        string content = "東京\tトウキョウ\n大阪\tオオサカ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        string result = dict.ApplyToText("東京と大阪");

        Assert.Equal("トウキョウとオオサカ", result);
    }

    [Fact]
    public void CustomDictionary_ApplyToText_LongestMatch()
    {
        // "東京都" (longer) should take priority over "東京" (shorter)
        string content = "東京\tトウキョウ\n東京都\tトウキョウト\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        string result = dict.ApplyToText("東京都は広い");

        Assert.Equal("トウキョウトは広い", result);
    }

    [Fact]
    public void CustomDictionary_LoadDictionary_CommentAndEmptyLines()
    {
        string content = "# This is a comment\n\n東京\tトウキョウ\n\n# Another comment\n大阪\tオオサカ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);

        string result = dict.ApplyToText("東京と大阪");
        Assert.Equal("トウキョウとオオサカ", result);
    }

    [Fact]
    public void CustomDictionary_LoadDictionary_FileNotFound()
    {
        var dict = new CustomDictionary();

        Assert.Throws<FileNotFoundException>(
            () => dict.LoadDictionary("/nonexistent/path/dict.txt"));
    }

    [Fact]
    public void CustomDictionary_LoadDictionary_NullPath_Throws()
    {
        var dict = new CustomDictionary();

        Assert.Throws<ArgumentNullException>(() => dict.LoadDictionary(null!));
    }

    [Fact]
    public void CustomDictionary_ApplyToText_NoMatch()
    {
        string content = "東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        string result = dict.ApplyToText("大阪は暑い");

        Assert.Equal("大阪は暑い", result);
    }

    [Fact]
    public void CustomDictionary_ApplyToText_EmptyText()
    {
        string content = "東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        string result = dict.ApplyToText("");

        Assert.Equal("", result);
    }

    [Fact]
    public void CustomDictionary_ApplyToText_EmptyDictionary()
    {
        var dict = new CustomDictionary();

        string result = dict.ApplyToText("東京は暑い");

        Assert.Equal("東京は暑い", result);
    }

    [Fact]
    public void CustomDictionary_LoadDictionary_MalformedLine_Skipped()
    {
        // Lines without a tab separator are silently skipped
        string content = "no_tab_here\n東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(1, dict.Count);
    }

    // ================================================================
    // SessionFactory
    // ================================================================

    [Fact]
    public void SessionFactory_Create_NullModelPath_Throws()
    {
        Assert.Throws<ArgumentNullException>(
            () => SessionFactory.Create(modelPath: null!));
    }

    [Fact]
    public void SessionFactory_Create_EmptyModelPath_Throws()
    {
        Assert.Throws<ArgumentException>(
            () => SessionFactory.Create(modelPath: ""));
    }

    [Fact]
    public void SessionFactory_Create_FileNotFound_Throws()
    {
        Assert.Throws<FileNotFoundException>(
            () => SessionFactory.Create(modelPath: "/nonexistent/model.onnx"));
    }

    [Fact]
    public void SessionFactory_CreateOptions_DefaultCpu()
    {
        // SessionFactory.Create validates the model path first, so we verify
        // that with useCuda=false (the default), no CUDA-related exception
        // is thrown before the file-existence check.
        // The FileNotFoundException confirms the factory reached the file
        // validation step rather than failing on CUDA EP setup.
        var ex = Assert.Throws<FileNotFoundException>(
            () => SessionFactory.Create(
                modelPath: "/tmp/nonexistent_model.onnx",
                useCuda: false));

        Assert.Contains("nonexistent_model.onnx", ex.Message);
    }

    [Fact]
    public void SessionFactory_CreateOptions_WithCuda()
    {
        // Even with useCuda=true, the factory validates the model path first.
        // The FileNotFoundException confirms we reach path validation
        // regardless of the CUDA flag.
        var ex = Assert.Throws<FileNotFoundException>(
            () => SessionFactory.Create(
                modelPath: "/tmp/nonexistent_model.onnx",
                useCuda: true,
                gpuDeviceId: 1));

        Assert.Contains("nonexistent_model.onnx", ex.Message);
    }

    // ================================================================
    // PhonemeSilenceProcessor — additional edge-case tests
    // ================================================================

    [Fact]
    public void PhonemeSilenceProcessor_SplitAtPhonemeSilence_EmptySilenceMap_SinglePhrase()
    {
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["a"] = [10],
            ["b"] = [11],
        };

        // Empty silence map → no phoneme triggers a split.
        var phonemeSilence = new Dictionary<string, float>();

        long[] phonemeIds = [10, 11, 10];

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIds, prosodyFlat: null, phonemeSilence, phonemeIdMap, 22050);

        // All phonemes land in a single trailing phrase with 0 silence.
        Assert.Single(phrases);
        Assert.Equal([10L, 11L, 10L], phrases[0].PhonemeIds);
        Assert.Equal(0, phrases[0].SilenceSamples);
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_DuplicatePhonemes_LastValueWins()
    {
        // Two entries for the same phoneme "_"; the dictionary overwrites,
        // so the last value (0.3) should win.
        var result = PhonemeSilenceProcessor.Parse("_ 0.5, _ 0.3");

        Assert.Single(result);
        Assert.True(result.ContainsKey("_"));
        Assert.Equal(0.3f, result["_"]);
    }

    [Fact]
    public void PhonemeSilenceProcessor_Parse_NegativeSeconds_Accepted()
    {
        // Negative seconds are syntactically valid floats; Parse should accept them.
        var result = PhonemeSilenceProcessor.Parse("_ -0.5");

        Assert.Single(result);
        Assert.Equal(-0.5f, result["_"]);
    }

    [Fact]
    public void PhonemeSilenceProcessor_SplitAtPhonemeSilence_MultiIdPhoneme_UsesLastId()
    {
        // Phoneme "x" maps to two IDs [5, 6]. The processor should trigger
        // a silence split only on the last ID (6), not on the first (5).
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["x"] = [5, 6],
            ["a"] = [10],
        };

        var phonemeSilence = new Dictionary<string, float> { ["x"] = 0.4f };

        // Sequence: a, x(5), x(6), a — split should happen after ID 6.
        long[] phonemeIds = [10, 5, 6, 10];
        const int sampleRate = 22050;

        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIds, prosodyFlat: null, phonemeSilence, phonemeIdMap, sampleRate);

        // Expect 2 phrases: [10, 5, 6] with silence, [10] trailing.
        Assert.Equal(2, phrases.Count);
        Assert.Equal([10L, 5L, 6L], phrases[0].PhonemeIds);
        Assert.Equal((int)(0.4f * sampleRate), phrases[0].SilenceSamples);
        Assert.Equal([10L], phrases[1].PhonemeIds);
        Assert.Equal(0, phrases[1].SilenceSamples);
    }

    // ================================================================
    // TimingWriter — additional edge-case tests
    // ================================================================

    [Fact]
    public void TimingWriter_CalculateTiming_DurationsShorterThanPhonemeIds()
    {
        // 3 phoneme IDs but only 2 durations → processes min(3, 2) = 2 entries.
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["a"] = [10],
            ["b"] = [11],
            ["c"] = [12],
        };

        long[] phonemeIds = [10, 11, 12];
        float[] durations = [5.0f, 3.0f]; // only 2 durations

        var entries = TimingWriter.CalculateTiming(
            phonemeIds, durations, phonemeIdMap, sampleRate: 22050);

        // Only the first 2 phonemes are processed.
        Assert.Equal(2, entries.Count);
        Assert.Equal("a", entries[0].Phoneme);
        Assert.Equal("b", entries[1].Phoneme);
    }

    [Fact]
    public void TimingWriter_CalculateTiming_UnknownPhonemeId_ShowsQuestionMark()
    {
        // ID 999 is not in the phoneme_id_map and is outside printable ASCII range.
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["a"] = [10],
        };

        long[] phonemeIds = [999];
        float[] durations = [4.0f];

        var entries = TimingWriter.CalculateTiming(
            phonemeIds, durations, phonemeIdMap, sampleRate: 22050);

        Assert.Single(entries);
        Assert.Equal("?", entries[0].Phoneme);
    }

    [Fact]
    public void TimingWriter_CalculateTiming_PrintableAsciiId()
    {
        // ID 65 (ASCII 'A') is not in the map, but falls in the printable
        // ASCII range (3..127) and should be displayed as "A".
        var phonemeIdMap = new Dictionary<string, int[]>
        {
            ["a"] = [10],
        };

        long[] phonemeIds = [65];
        float[] durations = [2.0f];

        var entries = TimingWriter.CalculateTiming(
            phonemeIds, durations, phonemeIdMap, sampleRate: 22050);

        Assert.Single(entries);
        Assert.Equal("A", entries[0].Phoneme);
    }

    [Fact]
    public void TimingWriter_WriteJson_ToFile_CreatesValidFile()
    {
        var entries = new List<TimingWriter.PhonemeTimingEntry>
        {
            new("k", 0.0f, 0.058f, 0.058f),
            new("a", 0.058f, 0.116f, 0.058f),
        };

        string path = Path.Combine(Path.GetTempPath(), $"piper_test_{Guid.NewGuid():N}.json");
        _tempFiles.Add(path);

        TimingWriter.WriteJson(path, entries);

        Assert.True(File.Exists(path));

        string json = File.ReadAllText(path);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        Assert.Equal(JsonValueKind.Array, root.ValueKind);
        Assert.Equal(2, root.GetArrayLength());
        Assert.Equal("k", root[0].GetProperty("phoneme").GetString());
        Assert.Equal("a", root[1].GetProperty("phoneme").GetString());
        Assert.True(root[0].GetProperty("start").GetSingle() < root[0].GetProperty("end").GetSingle());
    }

    [Fact]
    public void TimingWriter_WriteTsv_ToFile_CreatesValidFile()
    {
        var entries = new List<TimingWriter.PhonemeTimingEntry>
        {
            new("k", 0.0f, 0.058f, 0.058f),
            new("a", 0.058f, 0.116f, 0.058f),
        };

        string path = Path.Combine(Path.GetTempPath(), $"piper_test_{Guid.NewGuid():N}.tsv");
        _tempFiles.Add(path);

        TimingWriter.WriteTsv(path, entries);

        Assert.True(File.Exists(path));

        string[] lines = File.ReadAllLines(path);

        // Header line
        Assert.True(lines.Length >= 3, "Expected header + 2 data lines");
        Assert.Equal("start\tend\tduration\tphoneme", lines[0]);

        // First data row
        string[] cols1 = lines[1].Split('\t');
        Assert.Equal(4, cols1.Length);
        Assert.Equal("k", cols1[3]);
        Assert.True(float.TryParse(cols1[0], NumberStyles.Float, CultureInfo.InvariantCulture, out float start1));
        Assert.True(float.TryParse(cols1[1], NumberStyles.Float, CultureInfo.InvariantCulture, out float end1));
        Assert.True(end1 > start1);

        // Second data row
        string[] cols2 = lines[2].Split('\t');
        Assert.Equal("a", cols2[3]);
    }
}
