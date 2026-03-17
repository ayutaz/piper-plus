using System.CommandLine;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

using Microsoft.ML.OnnxRuntime;

using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// JSONL input line deserialized from stdin.
/// </summary>
internal sealed class JsonlUtterance
{
    [JsonPropertyName("phoneme_ids")]
    public int[]? PhonemeIds { get; set; }

    [JsonPropertyName("speaker_id")]
    public int? SpeakerId { get; set; }

    [JsonPropertyName("output_file")]
    public string? OutputFile { get; set; }

    /// <summary>
    /// Prosody features as array-of-arrays: [[a1, a2, a3], [a1, a2, a3], ...].
    /// Note: Python uses dict format [{"a1":1,"a2":2,"a3":3},...] which differs.
    /// </summary>
    [JsonPropertyName("prosody_features")]
    public int[][]? ProsodyFeatures { get; set; }

    /// <summary>
    /// Text field for JSONL lines — when present, the CLI phonemizes this text
    /// instead of requiring pre-computed <see cref="PhonemeIds"/>.
    /// </summary>
    [JsonPropertyName("text")]
    public string? Text { get; set; }

    /// <summary>
    /// Speaker name resolved via <see cref="PiperConfig.SpeakerIdMap"/>.
    /// Used only when <see cref="SpeakerId"/> is absent (speaker_id takes precedence).
    /// </summary>
    [JsonPropertyName("speaker")]
    public string? Speaker { get; set; }
}

/// <summary>
/// Source-generated JSON context for trim/AOT-safe JSONL deserialization.
/// </summary>
[JsonSerializable(typeof(JsonlUtterance))]
[JsonSourceGenerationOptions(
    PropertyNameCaseInsensitive = false,
    ReadCommentHandling = JsonCommentHandling.Skip,
    AllowTrailingCommas = true)]
internal partial class CliJsonContext : JsonSerializerContext;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            var rootCommand = BuildRootCommand();
            return rootCommand.Parse(args).Invoke();
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[ERR] Fatal error: {ex.Message}");
            return 1;
        }
    }

    private static RootCommand BuildRootCommand()
    {
        // --model / -m
        var modelOption = new Option<FileInfo?>("--model", "-m")
        { Description = "Path to .onnx model file" };

        // --config / -c
        var configOption = new Option<FileInfo?>("--config", "-c")
        { Description = "Path to config.json (auto-detected if omitted)" };

        // --output_file / --output-file / -f
        var outputFileOption = new Option<string?>("--output_file", "--output-file", "-f")
        { Description = "Output WAV file path ('-' for stdout)" };

        // --output_dir / --output-dir / -d
        var outputDirOption = new Option<DirectoryInfo>("--output_dir", "--output-dir", "-d")
        {
            Description = "Output directory (default: current directory)",
            DefaultValueFactory = _ => new DirectoryInfo(Directory.GetCurrentDirectory()),
        };

        // --output_raw / --output-raw
        var outputRawOption = new Option<bool>("--output_raw", "--output-raw")
        { Description = "Output raw PCM int16 to stdout (no WAV header)" };

        // --speaker / -s
        var speakerOption = new Option<int>("--speaker", "-s")
        {
            Description = "Speaker ID (default: 0)",
            DefaultValueFactory = _ => 0,
        };

        // --noise_scale / --noise-scale
        var noiseScaleOption = new Option<float>("--noise_scale", "--noise-scale")
        {
            Description = "Generator noise scale (default: 0.667)",
            DefaultValueFactory = _ => 0.667f,
        };

        // --length_scale / --length-scale
        var lengthScaleOption = new Option<float>("--length_scale", "--length-scale")
        {
            Description = "Phoneme length scale (default: 1.0)",
            DefaultValueFactory = _ => 1.0f,
        };

        // --noise_w / --noise-w
        var noiseWOption = new Option<float>("--noise_w", "--noise-w")
        {
            Description = "Duration predictor noise (default: 0.8)",
            DefaultValueFactory = _ => 0.8f,
        };

        // --sentence_silence / --sentence-silence
        var sentenceSilenceOption = new Option<float>("--sentence_silence", "--sentence-silence")
        {
            Description = "Seconds of silence after each sentence (default: 0.2)",
            DefaultValueFactory = _ => 0.2f,
        };

        // --text / -t
        var textOption = new Option<string?>("--text", "-t")
        { Description = "Text to synthesize (alternative to JSONL stdin input)" };

        // --language
        var languageOption = new Option<string>("--language")
        {
            Description = "Language for --text mode: ja or en (default: ja)",
            DefaultValueFactory = _ => "ja",
        };

        // --json-input
        var jsonInputOption = new Option<bool>("--json-input")
        { Description = "Interpret stdin as JSONL" };

        // --debug
        var debugOption = new Option<bool>("--debug")
        { Description = "Enable DEBUG logging to stderr" };

        // --quiet / -q
        var quietOption = new Option<bool>("--quiet", "-q")
        { Description = "Disable all logging" };

        // --version
        var versionOption = new Option<bool>("--version")
        { Description = "Show version and exit" };

        // ================================================================
        // Phase 3 — new CLI options (14)
        // ================================================================

        // --use-cuda
        var useCudaOption = new Option<bool>("--use-cuda")
        { Description = "Use CUDA execution provider" };

        // --gpu-device-id
        var gpuDeviceIdOption = new Option<int>("--gpu-device-id")
        {
            Description = "CUDA GPU device ID",
            DefaultValueFactory = _ => 0,
        };

        // --phoneme_silence
        var phonemeSilenceOption = new Option<string?>("--phoneme_silence")
        { Description = "Phoneme silence: '<phoneme> <seconds>'" };

        // --raw-phonemes
        var rawPhonemesOption = new Option<bool>("--raw-phonemes")
        { Description = "Treat input as phonemes (not text)" };

        // --streaming
        var streamingOption = new Option<bool>("--streaming")
        { Description = "Stream raw PCM int16 to stdout" };

        // --output-timing
        var outputTimingOption = new Option<string?>("--output-timing")
        { Description = "Output phoneme timing to file" };

        // --timing-format
        var timingFormatOption = new Option<string>("--timing-format")
        {
            Description = "Timing format: json or tsv",
            DefaultValueFactory = _ => "json",
        };

        // --custom-dict
        var customDictOption = new Option<string?>("--custom-dict")
        { Description = "Custom dictionary files (comma-separated)" };

        // --espeak_data (no-op, for C++ CLI compatibility)
        var espeakDataOption = new Option<string?>("--espeak_data")
        { Description = "espeak-ng data path (ignored in C# CLI)" };

        // --tashkeel_model (no-op, for C++ CLI compatibility)
        var tashkeelModelOption = new Option<string?>("--tashkeel_model")
        { Description = "libtashkeel model (ignored in C# CLI)" };

        // --test-mode
        var testModeOption = new Option<bool>("--test-mode")
        { Description = "Skip ONNX inference (CI testing)" };

        // --list-models [LANG]
        var listModelsOption = new Option<string?>("--list-models")
        {
            Description = "List available models (optionally filter by language code)",
            Arity = ArgumentArity.ZeroOrOne,
        };

        // --download-model NAME
        var downloadModelOption = new Option<string?>("--download-model")
        { Description = "Download a model by name" };

        // --model-dir DIR
        var modelDirOption = new Option<DirectoryInfo?>("--model-dir")
        { Description = "Model download directory" };

        var rootCommand = new RootCommand("Piper Plus TTS — C# CLI")
        {
            modelOption,
            configOption,
            outputFileOption,
            outputDirOption,
            outputRawOption,
            speakerOption,
            noiseScaleOption,
            lengthScaleOption,
            noiseWOption,
            sentenceSilenceOption,
            textOption,
            languageOption,
            jsonInputOption,
            debugOption,
            quietOption,
            versionOption,
            // Phase 3 options
            useCudaOption,
            gpuDeviceIdOption,
            phonemeSilenceOption,
            rawPhonemesOption,
            streamingOption,
            outputTimingOption,
            timingFormatOption,
            customDictOption,
            espeakDataOption,
            tashkeelModelOption,
            testModeOption,
            listModelsOption,
            downloadModelOption,
            modelDirOption,
        };

        rootCommand.SetAction((parseResult) =>
            {
                // --version: early exit
                if (parseResult.GetValue(versionOption))
                {
                    var version = Assembly.GetExecutingAssembly()
                        .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                        ?.InformationalVersion
                        ?? Assembly.GetExecutingAssembly().GetName().Version?.ToString()
                        ?? "unknown";
                    Console.WriteLine(version);
                    return;
                }

                bool debug = parseResult.GetValue(debugOption);
                bool quiet = parseResult.GetValue(quietOption);

                // ============================================================
                // --list-models / --download-model (early return, no model needed)
                // ============================================================
                if (parseResult.GetResult(listModelsOption) is not null)
                {
                    string? listModelsLang = parseResult.GetValue(listModelsOption);
                    ModelManager.ListModels(string.IsNullOrEmpty(listModelsLang) ? null : listModelsLang);
                    return;
                }

                string? downloadModelName = parseResult.GetValue(downloadModelOption);
                if (!string.IsNullOrEmpty(downloadModelName))
                {
                    var dlModelDir = parseResult.GetValue(modelDirOption);
                    string targetDir = dlModelDir?.FullName
                        ?? Environment.GetEnvironmentVariable("PIPER_MODEL_DIR")
                        ?? ModelManager.GetDefaultModelDir();

                    LogInfo(quiet, $"Downloading model '{downloadModelName}' to {targetDir}...");

                    bool success = ModelManager.DownloadModelAsync(
                        downloadModelName, targetDir, CancellationToken.None).GetAwaiter().GetResult();

                    if (!success)
                    {
                        Environment.ExitCode = 1;
                    }
                    return;
                }

                // ============================================================
                // No-op options (C++ CLI compatibility)
                // ============================================================
                string? espeakData = parseResult.GetValue(espeakDataOption);
                if (!string.IsNullOrEmpty(espeakData))
                {
                    LogDebug(debug, quiet, $"--espeak_data ignored in C# CLI: {espeakData}");
                }

                string? tashkeelModel = parseResult.GetValue(tashkeelModelOption);
                if (!string.IsNullOrEmpty(tashkeelModel))
                {
                    LogDebug(debug, quiet, $"--tashkeel_model ignored in C# CLI: {tashkeelModel}");
                }

                // ============================================================
                // Phase 3 option values
                // ============================================================
                bool useCuda = parseResult.GetValue(useCudaOption);
                int gpuDeviceId = parseResult.GetValue(gpuDeviceIdOption);
                string? phonemeSilenceSpec = parseResult.GetValue(phonemeSilenceOption);
                bool rawPhonemes = parseResult.GetValue(rawPhonemesOption);
                bool streaming = parseResult.GetValue(streamingOption);
                string? outputTimingPath = parseResult.GetValue(outputTimingOption);
                string timingFormat = parseResult.GetValue(timingFormatOption)!;
                string? customDictPaths = parseResult.GetValue(customDictOption);
                bool testMode = parseResult.GetValue(testModeOption);

                // --model-dir: resolve from CLI > PIPER_MODEL_DIR env
                var modelDirInfo = parseResult.GetValue(modelDirOption);
                if (modelDirInfo is null)
                {
                    var envModelDir = Environment.GetEnvironmentVariable("PIPER_MODEL_DIR");
                    if (!string.IsNullOrEmpty(envModelDir))
                    {
                        modelDirInfo = new DirectoryInfo(envModelDir);
                        LogDebug(debug, quiet, $"PIPER_MODEL_DIR: {envModelDir}");
                    }
                }

                // --gpu-device-id: resolve from CLI > PIPER_GPU_DEVICE_ID env
                // (SessionFactory also handles this, but we resolve here for logging)
                if (gpuDeviceId == 0)
                {
                    var envGpu = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
                    if (!string.IsNullOrEmpty(envGpu) && int.TryParse(envGpu, out int envGpuId))
                    {
                        gpuDeviceId = envGpuId;
                        LogDebug(debug, quiet, $"PIPER_GPU_DEVICE_ID: {envGpuId}");
                    }
                }

                // Resolve model path: CLI > env > error
                var modelFileInfo = parseResult.GetValue(modelOption);
                string? modelPath = modelFileInfo?.FullName;

                if (string.IsNullOrEmpty(modelPath))
                {
                    var envModel = Environment.GetEnvironmentVariable("PIPER_DEFAULT_MODEL");
                    if (!string.IsNullOrEmpty(envModel))
                    {
                        modelPath = envModel;
                    }
                }

                // --test-mode does not require a real model when --text is used
                if (string.IsNullOrEmpty(modelPath) && !testMode)
                {
                    LogError("--model is required (or set PIPER_DEFAULT_MODEL).");
                    Environment.ExitCode = 1;
                    return;
                }

                if (!testMode && !string.IsNullOrEmpty(modelPath) && !File.Exists(modelPath))
                {
                    LogError($"Model file not found: {modelPath}");
                    Environment.ExitCode = 1;
                    return;
                }

                // Resolve config path
                var configFileInfo = parseResult.GetValue(configOption);
                string? explicitConfig = configFileInfo?.FullName;
                string? configPath = PiperConfig.FindConfigPath(
                    explicitConfig, modelPath);

                if (string.IsNullOrEmpty(configPath) && !testMode)
                {
                    LogError(
                        $"config.json not found. Searched: {modelPath}.json, " +
                        $"{Path.GetDirectoryName(modelPath)}/config.json. " +
                        "Use --config to specify.");
                    Environment.ExitCode = 1;
                    return;
                }

                LogDebug(debug, quiet, $"Config path: {configPath}");

                PiperConfig? config = null;
                if (!string.IsNullOrEmpty(configPath))
                {
                    try
                    {
                        config = PiperConfig.LoadFromFile(configPath);
                    }
                    catch (Exception ex)
                    {
                        LogError($"Failed to load config: {ex.Message}");
                        Environment.ExitCode = 1;
                        return;
                    }
                }

                // ============================================================
                // Parse --phoneme_silence
                // ============================================================
                Dictionary<string, float>? phonemeSilenceMap = null;
                if (!string.IsNullOrEmpty(phonemeSilenceSpec))
                {
                    try
                    {
                        phonemeSilenceMap = PhonemeSilenceProcessor.Parse(phonemeSilenceSpec);
                        LogDebug(debug, quiet,
                            $"Phoneme silence: {phonemeSilenceMap.Count} entries");
                    }
                    catch (ArgumentException ex)
                    {
                        LogError($"Invalid --phoneme_silence: {ex.Message}");
                        Environment.ExitCode = 1;
                        return;
                    }
                }

                // ============================================================
                // Load --custom-dict
                // ============================================================
                CustomDictionary? customDict = null;
                if (!string.IsNullOrEmpty(customDictPaths))
                {
                    customDict = new CustomDictionary();
                    var paths = customDictPaths.Split(',',
                        StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
                    customDict.LoadDictionaries(paths);
                    LogDebug(debug, quiet,
                        $"Custom dictionary: {customDict.Count} entries from {paths.Length} file(s)");
                }

                // Gather synthesis parameters
                float noiseScale = parseResult.GetValue(noiseScaleOption);
                float lengthScale = parseResult.GetValue(lengthScaleOption);
                float noiseW = parseResult.GetValue(noiseWOption);
                int speaker = parseResult.GetValue(speakerOption);
                float sentenceSilence = parseResult.GetValue(sentenceSilenceOption);
                bool outputRaw = parseResult.GetValue(outputRawOption);
                bool jsonInput = parseResult.GetValue(jsonInputOption);
                string? textInput = parseResult.GetValue(textOption);
                string language = parseResult.GetValue(languageOption)!;

                string? outputFile = parseResult.GetValue(outputFileOption);
                var outputDir = parseResult.GetValue(outputDirOption)!;

                // Validate --text and --json-input are mutually exclusive
                if (!string.IsNullOrEmpty(textInput) && jsonInput)
                {
                    LogError("--text and --json-input are mutually exclusive.");
                    Environment.ExitCode = 1;
                    return;
                }

                // ============================================================
                // --test-mode + --text: output phoneme IDs and exit
                // ============================================================
                if (testMode && !string.IsNullOrEmpty(textInput))
                {
                    LogDebug(debug, quiet, "[test-mode] Phonemizing text without inference.");

                    IPhonemizer phonemizer;
                    try
                    {
#pragma warning disable IL2026 // RequiresUnreferencedCode -- G2P engines resolved via reflection
                        phonemizer = ResolveTextModePhonemizer(language);
#pragma warning restore IL2026
                    }
                    catch (NotSupportedException ex)
                    {
                        LogError(ex.Message);
                        Environment.ExitCode = 1;
                        return;
                    }

                    // Apply custom dict before phonemization
                    if (customDict is not null)
                    {
                        textInput = customDict.ApplyToText(textInput);
                    }

                    var phonemeIdMap = phonemizer.GetPhonemeIdMap()
                                      ?? config?.PhonemeIdMap
                                      ?? new Dictionary<string, int[]>();
                    var (phonemeIdsLong, _) = PhonemeEncoder.EncodeDirect(
                        phonemizer, textInput, phonemeIdMap);

                    Console.Error.WriteLine(
                        $"[test-mode] phoneme_ids({phonemeIdsLong.Length}): " +
                        $"[{string.Join(", ", phonemeIdsLong)}]");

                    return;
                }

                // ============================================================
                // --test-mode + JSONL/raw-phonemes: parse and output IDs
                // ============================================================
                if (testMode)
                {
                    LogDebug(debug, quiet, "[test-mode] Processing stdin without inference.");

                    using var stdinReader = new StreamReader(
                        Console.OpenStandardInput(), Console.InputEncoding);

                    int lineNum = 0;
                    string? line;
                    while ((line = stdinReader.ReadLine()) is not null)
                    {
                        if (string.IsNullOrWhiteSpace(line))
                            continue;

                        lineNum++;

                        if (rawPhonemes)
                        {
                            Console.Error.WriteLine(
                                $"[test-mode] raw-phonemes line {lineNum}: {line.Trim()}");
                            continue;
                        }

                        // JSONL mode
                        try
                        {
                            var utterance = JsonSerializer.Deserialize(
                                line, CliJsonContext.Default.JsonlUtterance);

                            if (utterance?.PhonemeIds is not null)
                            {
                                Console.Error.WriteLine(
                                    $"[test-mode] line {lineNum}: phoneme_ids({utterance.PhonemeIds.Length}): " +
                                    $"[{string.Join(", ", utterance.PhonemeIds)}]");
                            }
                            else if (utterance?.Text is not null)
                            {
                                Console.Error.WriteLine(
                                    $"[test-mode] line {lineNum}: text=\"{utterance.Text}\"");
                            }
                        }
                        catch (JsonException ex)
                        {
                            LogError($"Invalid JSON on line {lineNum}: {ex.Message}");
                        }
                    }

                    return;
                }

                // ============================================================
                // Model/config must be available for inference modes
                // ============================================================
                if (string.IsNullOrEmpty(modelPath))
                {
                    LogError("--model is required (or set PIPER_DEFAULT_MODEL).");
                    Environment.ExitCode = 1;
                    return;
                }

                if (config is null)
                {
                    LogError(
                        $"config.json not found. Searched: {modelPath}.json, " +
                        $"{Path.GetDirectoryName(modelPath)}/config.json. " +
                        "Use --config to specify.");
                    Environment.ExitCode = 1;
                    return;
                }

                LogDebug(debug, quiet, $"Model path: {modelPath}");
                LogDebug(debug, quiet, $"Sample rate: {config.Audio.SampleRate}");
                LogInfo(quiet, $"Loading model: {modelPath}");

                // Create ONNX InferenceSession via SessionFactory (CUDA-aware)
                InferenceSession session;
                try
                {
                    session = SessionFactory.Create(
                        modelPath,
                        useCuda: useCuda,
                        gpuDeviceId: gpuDeviceId);
                }
                catch (Exception ex)
                {
                    LogError($"Failed to load ONNX model: {ex.Message}");
                    Environment.ExitCode = 1;
                    return;
                }

                using var model = new PiperModel(session, config);
                LogInfo(quiet, $"Model loaded (speakers={config.NumSpeakers}, " +
                               $"hasSid={model.HasSpeakerId}, " +
                               $"hasProsody={model.HasProsody})");

                if (useCuda)
                {
                    LogDebug(debug, quiet, $"CUDA enabled (device_id={gpuDeviceId})");
                }

                // Create PiperSession for inference
                var piperSession = new PiperSession(model);

                int sampleRate = model.SampleRate;
                piperSession.SentenceSilenceSeconds = sentenceSilence;

                // Determine output mode
                OutputMode outputMode;
                if (streaming)
                {
                    // --streaming forces raw stdout mode
                    outputMode = OutputMode.RawStdout;
                    LogDebug(debug, quiet, "Streaming mode: forcing raw PCM stdout output");
                }
                else if (outputRaw)
                {
                    outputMode = OutputMode.RawStdout;
                }
                else if (outputFile == "-")
                {
                    outputMode = OutputMode.WavStdout;
                }
                else if (!string.IsNullOrEmpty(outputFile))
                {
                    outputMode = OutputMode.SingleFile;
                }
                else
                {
                    outputMode = OutputMode.Directory;
                }

                // Ensure output directory exists for directory mode
                if (outputMode == OutputMode.Directory && !outputDir.Exists)
                {
                    outputDir.Create();
                    outputDir.Refresh();
                }

                LogDebug(debug, quiet, $"Output mode: {outputMode}");
                LogDebug(debug, quiet,
                    $"Params: noise_scale={noiseScale}, length_scale={lengthScale}, " +
                    $"noise_w={noiseW}, speaker={speaker}");

                // ================================================================
                // --text mode: phonemize text directly
                // ================================================================
                if (!string.IsNullOrEmpty(textInput))
                {
                    // Apply custom dictionary before phonemization
                    if (customDict is not null)
                    {
                        string original = textInput;
                        textInput = customDict.ApplyToText(textInput);
                        if (textInput != original)
                        {
                            LogDebug(debug, quiet,
                                $"Custom dict: \"{original}\" -> \"{textInput}\"");
                        }
                    }

                    LogDebug(debug, quiet, $"Text mode: language={language}, text=\"{textInput}\"");

                    // Resolve phonemizer for the requested language
                    IPhonemizer phonemizer;
                    try
                    {
#pragma warning disable IL2026 // RequiresUnreferencedCode -- G2P engines resolved via reflection
                        phonemizer = ResolveTextModePhonemizer(language);
#pragma warning restore IL2026
                    }
                    catch (NotSupportedException ex)
                    {
                        LogError(ex.Message);
                        Environment.ExitCode = 1;
                        return;
                    }

                    // Use the phonemizer's own ID map if available, else fall back to config
                    var phonemeIdMap = phonemizer.GetPhonemeIdMap() ?? config.PhonemeIdMap;

                    // Phonemize + encode in one step via PhonemeEncoder
                    var (phonemeIdsLong, prosodyFlat) = PhonemeEncoder.EncodeDirect(
                        phonemizer, textInput, phonemeIdMap);

                    LogDebug(debug, quiet,
                        $"Encoded: {phonemeIdsLong.Length} phoneme IDs" +
                        (prosodyFlat is not null ? $", prosody={prosodyFlat.Length / 3} entries" : ""));

                    // If model doesn't support prosody, discard the prosody data
                    if (!model.HasProsody)
                    {
                        prosodyFlat = null;
                    }

                    // Synthesize (with optional --phoneme_silence splitting)
                    short[] audio;
                    try
                    {
                        audio = SynthesizeWithPhonemeSilence(
                            piperSession, phonemeIdsLong, prosodyFlat,
                            speaker, noiseScale, lengthScale, noiseW,
                            phonemeSilenceMap, config.PhonemeIdMap, sampleRate);
                    }
                    catch (Exception ex)
                    {
                        LogError($"Synthesis failed: {ex.Message}");
                        Environment.ExitCode = 1;
                        return;
                    }

                    // --output-timing: warn that timing data is not available
                    // (VITS model does not expose per-phoneme durations in standard output)
                    if (!string.IsNullOrEmpty(outputTimingPath))
                    {
                        LogInfo(quiet,
                            $"Warning: --output-timing specified but phoneme timing data " +
                            $"is not available from this model. Skipping timing output.");
                    }

                    // Write output (streaming vs normal)
                    if (streaming)
                    {
                        using var stdout = Console.OpenStandardOutput();
                        StreamingWriter.WriteImmediate(stdout, audio);
                    }
                    else
                    {
                        WriteTextModeOutput(
                            outputMode, outputRaw, outputFile, outputDir,
                            audio, sampleRate, quiet);
                    }

                    LogInfo(quiet, "Synthesized 1 utterance(s).");
                    return;
                }

                // ================================================================
                // --raw-phonemes mode: stdin lines are space-separated phonemes
                // ================================================================
                if (rawPhonemes)
                {
                    LogDebug(debug, quiet, "Raw phonemes mode: interpreting stdin as phoneme strings");

                    using var stdinReader = new StreamReader(
                        Console.OpenStandardInput(), Console.InputEncoding);

                    Stream? stdoutStream = (outputMode is OutputMode.RawStdout or OutputMode.WavStdout)
                        ? Console.OpenStandardOutput()
                        : null;

                    try
                    {
                        int utteranceIndex = 0;
                        string? line;

                        while ((line = stdinReader.ReadLine()) is not null)
                        {
                            if (string.IsNullOrWhiteSpace(line))
                                continue;

                            // Parse space-separated phonemes via RawPhonemeParser
                            // (handles PUA resolution for multi-char tokens like "a:", "N_m")
                            long[] phonemeIdsLong = RawPhonemeParser.Parse(line.Trim(), config.PhonemeIdMap);

                            if (phonemeIdsLong.Length == 0)
                            {
                                LogDebug(debug, quiet,
                                    $"Line {utteranceIndex + 1}: no valid phoneme IDs; skipping.");
                                utteranceIndex++;
                                continue;
                            }

                            LogDebug(debug, quiet,
                                $"Raw phonemes line {utteranceIndex}: " +
                                $"{phonemeIdsLong.Length} IDs, speaker={speaker}");

                            short[] audio;
                            try
                            {
                                audio = SynthesizeWithPhonemeSilence(
                                    piperSession, phonemeIdsLong, null,
                                    speaker, noiseScale, lengthScale, noiseW,
                                    phonemeSilenceMap, config.PhonemeIdMap, sampleRate);
                            }
                            catch (Exception ex)
                            {
                                LogError($"Synthesis failed on line {utteranceIndex + 1}: {ex.Message}");
                                Environment.ExitCode = 1;
                                return;
                            }

                            WriteUtteranceOutput(
                                outputMode, stdoutStream, streaming,
                                outputFile, outputDir, null,
                                audio, sampleRate, utteranceIndex, quiet);

                            utteranceIndex++;
                        }

                        LogInfo(quiet, $"Synthesized {utteranceIndex} utterance(s).");
                    }
                    finally
                    {
                        stdoutStream?.Dispose();
                    }

                    return;
                }

                // ================================================================
                // JSONL stdin mode (existing behavior, extended)
                // ================================================================

                // Hint when stdin appears to be a terminal
                if (!jsonInput && Console.IsInputRedirected == false)
                {
                    LogInfo(quiet, "Reading from stdin. Use --text for direct text input, " +
                                   "or pipe JSONL input. Press Ctrl+D (Unix) / Ctrl+Z (Windows) to end.");
                }

                // Lazily resolved phonemizer for JSONL "text" field processing
                IPhonemizer? jsonlPhonemizer = null;

                // Open stdout stream once for raw/wav stdout modes (avoid re-opening per utterance)
                {
                    Stream? stdoutStream = (outputMode is OutputMode.RawStdout or OutputMode.WavStdout)
                        ? Console.OpenStandardOutput()
                        : null;
                    try
                    {
                        // Read stdin line by line
                        int utteranceIndex = 0;
                        string? line;

                        using var stdinReader = new StreamReader(
                            Console.OpenStandardInput(), Console.InputEncoding);

                        while ((line = stdinReader.ReadLine()) is not null)
                        {
                            if (string.IsNullOrWhiteSpace(line))
                            {
                                continue;
                            }

                            // Parse JSONL input
                            JsonlUtterance? utterance;
                            try
                            {
                                utterance = JsonSerializer.Deserialize(
                                    line, CliJsonContext.Default.JsonlUtterance);
                            }
                            catch (JsonException ex)
                            {
                                LogError($"Invalid JSON on line {utteranceIndex + 1}: {ex.Message}");
                                Environment.ExitCode = 1;
                                return;
                            }

                            // ---------------------------------------------------
                            // Resolve speaker: speaker_id > "speaker" name > CLI default
                            // (C++ compatible: speaker_id takes precedence)
                            // ---------------------------------------------------
                            int uttSpeaker;
                            if (utterance?.SpeakerId.HasValue == true)
                            {
                                uttSpeaker = utterance.SpeakerId.Value;
                            }
                            else if (!string.IsNullOrEmpty(utterance?.Speaker)
                                && config.SpeakerIdMap is not null)
                            {
                                if (config.SpeakerIdMap.TryGetValue(
                                        utterance.Speaker, out int resolvedId))
                                {
                                    uttSpeaker = resolvedId;
                                    LogDebug(debug, quiet,
                                        $"Speaker name '{utterance.Speaker}' -> ID {resolvedId}");
                                }
                                else
                                {
                                    // C++ compatible: warn and continue (don't exit)
                                    LogInfo(quiet,
                                        $"Warning: Unknown speaker name '{utterance.Speaker}', using default speaker {speaker}");
                                    uttSpeaker = speaker;
                                }
                            }
                            else
                            {
                                uttSpeaker = speaker;
                            }

                            // ---------------------------------------------------
                            // JSONL "text" field: phonemize inline
                            // ---------------------------------------------------
                            long[] phonemeIdsLong;
                            long[]? prosodyFlat = null;

                            if (!string.IsNullOrEmpty(utterance?.Text))
                            {
                                // Lazily create phonemizer
                                if (jsonlPhonemizer is null)
                                {
                                    try
                                    {
#pragma warning disable IL2026 // RequiresUnreferencedCode -- G2P engines resolved via reflection
                                        jsonlPhonemizer = ResolveTextModePhonemizer(language);
#pragma warning restore IL2026
                                    }
                                    catch (NotSupportedException ex)
                                    {
                                        LogError(ex.Message);
                                        Environment.ExitCode = 1;
                                        return;
                                    }
                                }

                                string textToPhon = utterance!.Text;

                                // Apply custom dict
                                if (customDict is not null)
                                {
                                    textToPhon = customDict.ApplyToText(textToPhon);
                                }

                                var phonemeIdMap = jsonlPhonemizer.GetPhonemeIdMap()
                                                  ?? config.PhonemeIdMap;
                                var encoded = PhonemeEncoder.EncodeDirect(
                                    jsonlPhonemizer, textToPhon, phonemeIdMap);
                                phonemeIdsLong = encoded.PhonemeIds;
                                prosodyFlat = model.HasProsody ? encoded.ProsodyFlat : null;

                                LogDebug(debug, quiet,
                                    $"JSONL text line {utteranceIndex}: \"{textToPhon}\" -> " +
                                    $"{phonemeIdsLong.Length} IDs");
                            }
                            else
                            {
                                // Standard phoneme_ids mode
                                if (utterance?.PhonemeIds is null || utterance.PhonemeIds.Length == 0)
                                {
                                    LogError($"Missing or empty phoneme_ids (and no text) on line {utteranceIndex + 1}.");
                                    Environment.ExitCode = 1;
                                    return;
                                }

                                // Convert int[] -> long[] for ONNX tensor (int64)
                                phonemeIdsLong = Array.ConvertAll(
                                    utterance.PhonemeIds, id => (long)id);

                                // Convert int[][] -> flat long[] for prosody features
                                if (utterance.ProsodyFeatures is { Length: > 0 })
                                {
                                    prosodyFlat = new long[utterance.ProsodyFeatures.Length * 3];
                                    for (int pi = 0; pi < utterance.ProsodyFeatures.Length; pi++)
                                    {
                                        var pf = utterance.ProsodyFeatures[pi];
                                        if (pf is { Length: >= 3 })
                                        {
                                            prosodyFlat[pi * 3] = pf[0];
                                            prosodyFlat[pi * 3 + 1] = pf[1];
                                            prosodyFlat[pi * 3 + 2] = pf[2];
                                        }
                                    }
                                }
                            }

                            LogDebug(debug, quiet,
                                $"Utterance {utteranceIndex}: phonemes={phonemeIdsLong.Length}, " +
                                $"speaker={uttSpeaker}");

                            // Run inference (with optional --phoneme_silence splitting)
                            short[] audio;
                            try
                            {
                                audio = SynthesizeWithPhonemeSilence(
                                    piperSession, phonemeIdsLong, prosodyFlat,
                                    uttSpeaker, noiseScale, lengthScale, noiseW,
                                    phonemeSilenceMap, config.PhonemeIdMap, sampleRate);
                            }
                            catch (Exception ex)
                            {
                                LogError($"Synthesis failed on line {utteranceIndex + 1}: {ex.Message}");
                                Environment.ExitCode = 1;
                                return;
                            }

                            // Determine output target for this utterance
                            string? uttOutputFile = utterance?.OutputFile;

                            WriteUtteranceOutput(
                                outputMode, stdoutStream, streaming,
                                outputFile, outputDir, uttOutputFile,
                                audio, sampleRate, utteranceIndex, quiet);

                            utteranceIndex++;
                        }

                        if (utteranceIndex == 0 && jsonInput)
                        {
                            LogError("No input received on stdin.");
                            Environment.ExitCode = 1;
                            return;
                        }

                        // --output-timing: warn once at end if no timing data
                        if (!string.IsNullOrEmpty(outputTimingPath))
                        {
                            LogInfo(quiet,
                                $"Warning: --output-timing specified but phoneme timing data " +
                                $"is not available from this model. Skipping timing output.");
                        }

                        LogInfo(quiet, $"Synthesized {utteranceIndex} utterance(s).");
                    }
                    finally
                    {
                        stdoutStream?.Dispose();
                    }
                }
            });

        return rootCommand;
    }

    // ----------------------------------------------------------------
    // Synthesis helpers
    // ----------------------------------------------------------------

    /// <summary>
    /// Synthesize audio, optionally splitting at phoneme silence boundaries.
    /// When <paramref name="phonemeSilenceMap"/> is <c>null</c>, performs a
    /// single inference call (normal path). Otherwise, splits the phoneme
    /// sequence via <see cref="PhonemeSilenceProcessor"/> and concatenates
    /// per-phrase audio with inserted silence gaps.
    /// </summary>
    private static short[] SynthesizeWithPhonemeSilence(
        PiperSession piperSession,
        long[] phonemeIdsLong,
        long[]? prosodyFlat,
        int speaker,
        float noiseScale,
        float lengthScale,
        float noiseW,
        Dictionary<string, float>? phonemeSilenceMap,
        Dictionary<string, int[]> phonemeIdMap,
        int sampleRate)
    {
        // Normal (non-split) path
        if (phonemeSilenceMap is null || phonemeSilenceMap.Count == 0)
        {
            var input = new SynthesisInput(
                PhonemeIds: phonemeIdsLong,
                SpeakerId: speaker,
                ProsodyFeatures: prosodyFlat,
                NoiseScale: noiseScale,
                LengthScale: lengthScale,
                NoiseW: noiseW);
            return piperSession.Synthesize(input);
        }

        // Split at phoneme silence boundaries
        var phrases = PhonemeSilenceProcessor.SplitAtPhonemeSilence(
            phonemeIdsLong, prosodyFlat,
            phonemeSilenceMap, phonemeIdMap, sampleRate);

        var segments = new List<(short[] Audio, int SilenceSamples)>();
        int totalLength = 0;

        foreach (var phrase in phrases)
        {
            if (phrase.PhonemeIds.Count == 0)
                continue;

            long[] phraseIds = phrase.PhonemeIds.ToArray();
            long[]? phraseProsody = phrase.ProsodyFlat?.ToArray();

            var input = new SynthesisInput(
                PhonemeIds: phraseIds,
                SpeakerId: speaker,
                ProsodyFeatures: phraseProsody,
                NoiseScale: noiseScale,
                LengthScale: lengthScale,
                NoiseW: noiseW);

            short[] phraseAudio = piperSession.Synthesize(input);
            segments.Add((phraseAudio, phrase.SilenceSamples));
            totalLength += phraseAudio.Length + phrase.SilenceSamples;
        }

        // Concatenate segments with silence gaps
        var result = new short[totalLength];
        int offset = 0;
        foreach (var (audio, silenceSamples) in segments)
        {
            audio.CopyTo(result.AsSpan(offset));
            offset += audio.Length;
            offset += silenceSamples; // zeros already initialized
        }

        return result;
    }

    // ----------------------------------------------------------------
    // Text mode helpers
    // ----------------------------------------------------------------

    /// <summary>
    /// Resolve an <see cref="IPhonemizer"/> for the given language in --text mode.
    /// <para>
    /// Currently supported languages:
    /// <list type="bullet">
    ///   <item><c>ja</c> — Japanese (requires <c>JapanesePhonemizer</c> + <c>IJapaneseG2PEngine</c>)</item>
    ///   <item><c>en</c> — English (requires <c>EnglishPhonemizer</c>)</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="language">Language code.</param>
    /// <returns>An <see cref="IPhonemizer"/> instance.</returns>
    /// <exception cref="NotSupportedException">When the language or its dependencies are unavailable.</exception>
    [RequiresUnreferencedCode(
        "G2P engine types are resolved via reflection. When publishing trimmed, " +
        "ensure DotNetG2PEngine/DotNetEnglishG2PEngine are preserved.")]
    private static IPhonemizer ResolveTextModePhonemizer(string language)
    {
        switch (language)
        {
            case "ja":
            {
                // DotNetG2PEngine は NuGet 未公開の可能性があるためリフレクションで解決
                var g2pType = Type.GetType(
                    "PiperPlus.Core.Phonemize.DotNetG2PEngine, PiperPlus.Core");
                if (g2pType is null)
                {
                    throw new NotSupportedException(
                        "--text mode for Japanese requires DotNetG2P, which is not yet available. " +
                        "Use JSONL stdin input instead.");
                }

                var g2pEngine = Activator.CreateInstance(g2pType) as IJapaneseG2PEngine
                    ?? throw new NotSupportedException(
                        "Failed to create DotNetG2PEngine instance.");

                // JapanesePhonemizer は直接参照可能
                return new JapanesePhonemizer(g2pEngine);
            }

            case "en":
            {
                // DotNetG2P.English のラッパーをリフレクションで解決
                var g2pType = Type.GetType(
                    "PiperPlus.Core.Phonemize.DotNetEnglishG2PEngine, PiperPlus.Core");
                if (g2pType is null)
                {
                    throw new NotSupportedException(
                        "--text mode for English requires DotNetG2P.English, which is not yet available. " +
                        "Use JSONL stdin input instead.");
                }

                var g2pEngine = Activator.CreateInstance(g2pType) as IEnglishG2PEngine
                    ?? throw new NotSupportedException(
                        "Failed to create DotNetEnglishG2PEngine instance.");

                return new EnglishPhonemizer(g2pEngine);
            }

            default:
                throw new NotSupportedException(
                    $"Unsupported language for --text mode: {language}. " +
                    "Supported languages: ja, en.");
        }
    }

    /// <summary>
    /// Write synthesized audio to the appropriate output target for --text mode.
    /// Produces a single file named <c>0.wav</c> in directory mode.
    /// </summary>
    private static void WriteTextModeOutput(
        OutputMode outputMode,
        bool outputRaw,
        string? outputFile,
        DirectoryInfo outputDir,
        short[] audio,
        int sampleRate,
        bool quiet)
    {
        switch (outputMode)
        {
            case OutputMode.RawStdout:
            {
                using var stdout = Console.OpenStandardOutput();
                WriteRawPcm(stdout, audio);
                break;
            }

            case OutputMode.WavStdout:
            {
                using var stdout = Console.OpenStandardOutput();
                WavWriter.Write(stdout, audio, sampleRate);
                break;
            }

            case OutputMode.SingleFile:
            {
                WavWriter.Write(outputFile!, audio, sampleRate);
                LogInfo(quiet, outputFile!);
                break;
            }

            case OutputMode.Directory:
            {
                var wavPath = Path.Combine(outputDir.FullName, "0.wav");

                var parentDir = Path.GetDirectoryName(wavPath);
                if (!string.IsNullOrEmpty(parentDir) && !Directory.Exists(parentDir))
                {
                    Directory.CreateDirectory(parentDir);
                }

                WavWriter.Write(wavPath, audio, sampleRate);
                LogInfo(quiet, wavPath);
                break;
            }
        }
    }

    /// <summary>
    /// Write a single utterance's audio to the appropriate output target
    /// in JSONL/raw-phonemes mode. Handles streaming vs non-streaming output.
    /// </summary>
    private static void WriteUtteranceOutput(
        OutputMode outputMode,
        Stream? stdoutStream,
        bool streaming,
        string? outputFile,
        DirectoryInfo outputDir,
        string? uttOutputFile,
        short[] audio,
        int sampleRate,
        int utteranceIndex,
        bool quiet)
    {
        // --streaming: always use StreamingWriter
        if (streaming && stdoutStream is not null)
        {
            StreamingWriter.WriteImmediate(stdoutStream, audio);
            return;
        }

        switch (outputMode)
        {
            case OutputMode.RawStdout:
                WriteRawPcm(stdoutStream!, audio);
                break;

            case OutputMode.WavStdout:
                WavWriter.Write(stdoutStream!, audio, sampleRate);
                break;

            case OutputMode.SingleFile:
            {
                if (utteranceIndex > 0)
                {
                    LogInfo(quiet, $"Warning: --output_file overwrites previous utterance ({outputFile})");
                }
                var path = outputFile!;
                WavWriter.Write(path, audio, sampleRate);
                LogInfo(quiet, path);
                break;
            }

            case OutputMode.Directory:
            {
                string wavPath;
                if (!string.IsNullOrEmpty(uttOutputFile))
                {
                    // Security: prevent path traversal from JSONL output_file
                    if (uttOutputFile.Contains("..") || Path.IsPathRooted(uttOutputFile))
                    {
                        LogError($"Rejected output_file with path traversal or absolute path: {uttOutputFile}");
                        Environment.ExitCode = 1;
                        return;
                    }
                    wavPath = Path.GetFullPath(Path.Combine(outputDir.FullName, uttOutputFile));
                    if (!wavPath.StartsWith(outputDir.FullName))
                    {
                        LogError($"Rejected output_file outside output directory: {uttOutputFile}");
                        Environment.ExitCode = 1;
                        return;
                    }
                }
                else
                {
                    wavPath = Path.Combine(
                        outputDir.FullName, $"{utteranceIndex}.wav");
                }

                // Ensure parent directory exists
                var parentDir = Path.GetDirectoryName(wavPath);
                if (!string.IsNullOrEmpty(parentDir)
                    && !Directory.Exists(parentDir))
                {
                    Directory.CreateDirectory(parentDir);
                }

                WavWriter.Write(wavPath, audio, sampleRate);
                LogInfo(quiet, wavPath);
                break;
            }
        }
    }

    // ----------------------------------------------------------------
    // Output helpers
    // ----------------------------------------------------------------

    /// <summary>
    /// Writes raw PCM int16 samples to the given stream (no WAV header).
    /// </summary>
    private static void WriteRawPcm(Stream stream, ReadOnlySpan<short> samples)
    {
        Span<byte> buffer = stackalloc byte[4096];
        int offset = 0;

        for (int i = 0; i < samples.Length; i++)
        {
            short sample = samples[i];
            buffer[offset++] = (byte)(sample & 0xFF);
            buffer[offset++] = (byte)((sample >> 8) & 0xFF);

            if (offset >= buffer.Length)
            {
                stream.Write(buffer[..offset]);
                offset = 0;
            }
        }

        if (offset > 0)
        {
            stream.Write(buffer[..offset]);
        }

        stream.Flush();
    }

    // ----------------------------------------------------------------
    // Logging helpers — all output goes to stderr
    // ----------------------------------------------------------------

    private static void LogError(string message)
    {
        Console.Error.WriteLine($"[ERR] {message}");
    }

    private static void LogInfo(bool quiet, string message)
    {
        if (!quiet)
        {
            Console.Error.WriteLine($"[INF] {message}");
        }
    }

    private static void LogDebug(bool debug, bool quiet, string message)
    {
        if (debug && !quiet)
        {
            Console.Error.WriteLine($"[DBG] {message}");
        }
    }
}

internal enum OutputMode
{
    /// <summary>Write individual WAV files to output directory.</summary>
    Directory,
    /// <summary>Write a single WAV file to the specified path.</summary>
    SingleFile,
    /// <summary>Write WAV binary (with header) to stdout.</summary>
    WavStdout,
    /// <summary>Write raw PCM int16 (no header) to stdout.</summary>
    RawStdout,
}
