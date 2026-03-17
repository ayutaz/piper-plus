using System.CommandLine;
using System.CommandLine.Invocation;
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
    /// Takes precedence over <see cref="SpeakerId"/> when both are present.
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
        var rootCommand = BuildRootCommand();
        return rootCommand.Invoke(args);
    }

    private static RootCommand BuildRootCommand()
    {
        // --model / -m
        var modelOption = new Option<FileInfo?>(
            aliases: ["--model", "-m"],
            description: "Path to .onnx model file");

        // --config / -c
        var configOption = new Option<FileInfo?>(
            aliases: ["--config", "-c"],
            description: "Path to config.json (auto-detected if omitted)");

        // --output_file / -f
        var outputFileOption = new Option<string?>(
            aliases: ["--output_file", "-f"],
            description: "Output WAV file path ('-' for stdout)");

        // --output_dir / -d
        var outputDirOption = new Option<DirectoryInfo>(
            aliases: ["--output_dir", "-d"],
            getDefaultValue: () => new DirectoryInfo(Directory.GetCurrentDirectory()),
            description: "Output directory (default: current directory)");

        // --output_raw
        var outputRawOption = new Option<bool>(
            name: "--output_raw",
            description: "Output raw PCM int16 to stdout (no WAV header)");

        // --speaker / -s
        var speakerOption = new Option<int>(
            aliases: ["--speaker", "-s"],
            getDefaultValue: () => 0,
            description: "Speaker ID (default: 0)");

        // --noise_scale
        var noiseScaleOption = new Option<float>(
            name: "--noise_scale",
            getDefaultValue: () => 0.667f,
            description: "Generator noise scale (default: 0.667)");

        // --length_scale
        var lengthScaleOption = new Option<float>(
            name: "--length_scale",
            getDefaultValue: () => 1.0f,
            description: "Phoneme length scale (default: 1.0)");

        // --noise_w
        var noiseWOption = new Option<float>(
            name: "--noise_w",
            getDefaultValue: () => 0.8f,
            description: "Duration predictor noise (default: 0.8)");

        // --sentence_silence
        var sentenceSilenceOption = new Option<float>(
            name: "--sentence_silence",
            getDefaultValue: () => 0.2f,
            description: "Seconds of silence after each sentence (default: 0.2)");

        // --text / -t
        var textOption = new Option<string?>(
            aliases: ["--text", "-t"],
            description: "Text to synthesize (alternative to JSONL stdin input)");

        // --language
        var languageOption = new Option<string>(
            name: "--language",
            getDefaultValue: () => "ja",
            description: "Language for --text mode: ja or en (default: ja)");

        // --json-input
        var jsonInputOption = new Option<bool>(
            name: "--json-input",
            description: "Interpret stdin as JSONL");

        // --debug
        var debugOption = new Option<bool>(
            name: "--debug",
            description: "Enable DEBUG logging to stderr");

        // --quiet / -q
        var quietOption = new Option<bool>(
            aliases: ["--quiet", "-q"],
            description: "Disable all logging");

        // --version
        var versionOption = new Option<bool>(
            name: "--version",
            description: "Show version and exit");

        // ================================================================
        // Phase 3 — new CLI options (14)
        // ================================================================

        // --use-cuda
        var useCudaOption = new Option<bool>(
            name: "--use-cuda",
            description: "Use CUDA execution provider");

        // --gpu-device-id
        var gpuDeviceIdOption = new Option<int>(
            name: "--gpu-device-id",
            getDefaultValue: () => 0,
            description: "CUDA GPU device ID");

        // --phoneme_silence
        var phonemeSilenceOption = new Option<string?>(
            name: "--phoneme_silence",
            description: "Phoneme silence: '<phoneme> <seconds>'");

        // --raw-phonemes
        var rawPhonemesOption = new Option<bool>(
            name: "--raw-phonemes",
            description: "Treat input as phonemes (not text)");

        // --streaming
        var streamingOption = new Option<bool>(
            name: "--streaming",
            description: "Stream raw PCM int16 to stdout");

        // --output-timing
        var outputTimingOption = new Option<string?>(
            name: "--output-timing",
            description: "Output phoneme timing to file");

        // --timing-format
        var timingFormatOption = new Option<string>(
            name: "--timing-format",
            getDefaultValue: () => "json",
            description: "Timing format: json or tsv");

        // --custom-dict
        var customDictOption = new Option<string?>(
            name: "--custom-dict",
            description: "Custom dictionary files (comma-separated)");

        // --espeak_data (no-op, for C++ CLI compatibility)
        var espeakDataOption = new Option<string?>(
            name: "--espeak_data",
            description: "espeak-ng data path (ignored in C# CLI)");

        // --tashkeel_model (no-op, for C++ CLI compatibility)
        var tashkeelModelOption = new Option<string?>(
            name: "--tashkeel_model",
            description: "libtashkeel model (ignored in C# CLI)");

        // --test-mode
        var testModeOption = new Option<bool>(
            name: "--test-mode",
            description: "Skip ONNX inference (CI testing)");

        // --list-models (Phase 4 placeholder)
        var listModelsOption = new Option<string?>(
            name: "--list-models",
            description: "List available models (not yet implemented)");

        // --download-model (Phase 4 placeholder)
        var downloadModelOption = new Option<string?>(
            name: "--download-model",
            description: "Download a model (not yet implemented)");

        // --model-dir (Phase 4 placeholder)
        var modelDirOption = new Option<DirectoryInfo?>(
            name: "--model-dir",
            description: "Model directory");

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

        rootCommand.SetHandler(
            (InvocationContext ctx) =>
            {
                var result = ctx.ParseResult;

                // --version: early exit
                if (result.GetValueForOption(versionOption))
                {
                    var version = Assembly.GetExecutingAssembly()
                        .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                        ?.InformationalVersion
                        ?? Assembly.GetExecutingAssembly().GetName().Version?.ToString()
                        ?? "unknown";
                    Console.WriteLine(version);
                    ctx.ExitCode = 0;
                    return;
                }

                bool debug = result.GetValueForOption(debugOption);
                bool quiet = result.GetValueForOption(quietOption);

                // ============================================================
                // Phase 4 placeholders: --list-models / --download-model
                // ============================================================
                string? listModels = result.GetValueForOption(listModelsOption);
                if (listModels is not null)
                {
                    LogError("--list-models is not yet implemented. Coming in Phase 4.");
                    ctx.ExitCode = 1;
                    return;
                }

                string? downloadModel = result.GetValueForOption(downloadModelOption);
                if (downloadModel is not null)
                {
                    LogError("--download-model is not yet implemented. Coming in Phase 4.");
                    ctx.ExitCode = 1;
                    return;
                }

                // ============================================================
                // No-op options (C++ CLI compatibility)
                // ============================================================
                string? espeakData = result.GetValueForOption(espeakDataOption);
                if (!string.IsNullOrEmpty(espeakData))
                {
                    LogDebug(debug, quiet, $"--espeak_data ignored in C# CLI: {espeakData}");
                }

                string? tashkeelModel = result.GetValueForOption(tashkeelModelOption);
                if (!string.IsNullOrEmpty(tashkeelModel))
                {
                    LogDebug(debug, quiet, $"--tashkeel_model ignored in C# CLI: {tashkeelModel}");
                }

                // ============================================================
                // Phase 3 option values
                // ============================================================
                bool useCuda = result.GetValueForOption(useCudaOption);
                int gpuDeviceId = result.GetValueForOption(gpuDeviceIdOption);
                string? phonemeSilenceSpec = result.GetValueForOption(phonemeSilenceOption);
                bool rawPhonemes = result.GetValueForOption(rawPhonemesOption);
                bool streaming = result.GetValueForOption(streamingOption);
                string? outputTimingPath = result.GetValueForOption(outputTimingOption);
                string timingFormat = result.GetValueForOption(timingFormatOption)!;
                string? customDictPaths = result.GetValueForOption(customDictOption);
                bool testMode = result.GetValueForOption(testModeOption);

                // --model-dir: resolve from CLI > PIPER_MODEL_DIR env
                var modelDirInfo = result.GetValueForOption(modelDirOption);
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
                var modelFileInfo = result.GetValueForOption(modelOption);
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
                    ctx.ExitCode = 1;
                    return;
                }

                if (!testMode && !string.IsNullOrEmpty(modelPath) && !File.Exists(modelPath))
                {
                    LogError($"Model file not found: {modelPath}");
                    ctx.ExitCode = 1;
                    return;
                }

                // Resolve config path
                var configFileInfo = result.GetValueForOption(configOption);
                string? explicitConfig = configFileInfo?.FullName;
                string? configPath = PiperConfig.FindConfigPath(
                    explicitConfig, modelPath);

                if (string.IsNullOrEmpty(configPath) && !testMode)
                {
                    LogError(
                        $"config.json not found. Searched: {modelPath}.json, " +
                        $"{Path.GetDirectoryName(modelPath)}/config.json. " +
                        "Use --config to specify.");
                    ctx.ExitCode = 1;
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
                        ctx.ExitCode = 1;
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
                        ctx.ExitCode = 1;
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
                float noiseScale = result.GetValueForOption(noiseScaleOption);
                float lengthScale = result.GetValueForOption(lengthScaleOption);
                float noiseW = result.GetValueForOption(noiseWOption);
                int speaker = result.GetValueForOption(speakerOption);
                float sentenceSilence = result.GetValueForOption(sentenceSilenceOption);
                bool outputRaw = result.GetValueForOption(outputRawOption);
                bool jsonInput = result.GetValueForOption(jsonInputOption);
                string? textInput = result.GetValueForOption(textOption);
                string language = result.GetValueForOption(languageOption)!;

                string? outputFile = result.GetValueForOption(outputFileOption);
                var outputDir = result.GetValueForOption(outputDirOption)!;

                // Validate --text and --json-input are mutually exclusive
                if (!string.IsNullOrEmpty(textInput) && jsonInput)
                {
                    LogError("--text and --json-input are mutually exclusive.");
                    ctx.ExitCode = 1;
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
                        phonemizer = ResolveTextModePhonemizer(language);
                    }
                    catch (NotSupportedException ex)
                    {
                        LogError(ex.Message);
                        ctx.ExitCode = 1;
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

                    ctx.ExitCode = 0;
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

                    ctx.ExitCode = 0;
                    return;
                }

                // ============================================================
                // Model/config must be available for inference modes
                // ============================================================
                if (string.IsNullOrEmpty(modelPath))
                {
                    LogError("--model is required (or set PIPER_DEFAULT_MODEL).");
                    ctx.ExitCode = 1;
                    return;
                }

                if (config is null)
                {
                    LogError(
                        $"config.json not found. Searched: {modelPath}.json, " +
                        $"{Path.GetDirectoryName(modelPath)}/config.json. " +
                        "Use --config to specify.");
                    ctx.ExitCode = 1;
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
                    ctx.ExitCode = 1;
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
                        phonemizer = ResolveTextModePhonemizer(language);
                    }
                    catch (NotSupportedException ex)
                    {
                        LogError(ex.Message);
                        ctx.ExitCode = 1;
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
                        ctx.ExitCode = 1;
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
                    ctx.ExitCode = 0;
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

                            // Parse space-separated phonemes and look up IDs
                            string[] phonemeTokens = line.Trim().Split(' ',
                                StringSplitOptions.RemoveEmptyEntries);

                            var idList = new List<long>();
                            foreach (string token in phonemeTokens)
                            {
                                if (config.PhonemeIdMap.TryGetValue(token, out int[]? ids))
                                {
                                    foreach (int id in ids)
                                    {
                                        idList.Add(id);
                                    }
                                }
                                else
                                {
                                    LogDebug(debug, quiet,
                                        $"Unknown phoneme '{token}' — skipped");
                                }
                            }

                            if (idList.Count == 0)
                            {
                                LogDebug(debug, quiet,
                                    $"Line {utteranceIndex + 1}: no valid phoneme IDs; skipping.");
                                utteranceIndex++;
                                continue;
                            }

                            long[] phonemeIdsLong = idList.ToArray();

                            LogDebug(debug, quiet,
                                $"Raw phonemes line {utteranceIndex}: {phonemeTokens.Length} tokens -> " +
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
                                ctx.ExitCode = 1;
                                return;
                            }

                            WriteUtteranceOutput(
                                outputMode, stdoutStream, streaming,
                                outputFile, outputDir, null,
                                audio, sampleRate, utteranceIndex, quiet);

                            utteranceIndex++;
                        }

                        LogInfo(quiet, $"Synthesized {utteranceIndex} utterance(s).");
                        ctx.ExitCode = 0;
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
                                ctx.ExitCode = 1;
                                return;
                            }

                            // ---------------------------------------------------
                            // Resolve speaker: "speaker" name > speaker_id > CLI default
                            // ---------------------------------------------------
                            int uttSpeaker = utterance?.SpeakerId ?? speaker;

                            if (!string.IsNullOrEmpty(utterance?.Speaker)
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
                                    LogError(
                                        $"Unknown speaker name '{utterance.Speaker}' " +
                                        $"on line {utteranceIndex + 1}. " +
                                        "Available: " +
                                        string.Join(", ", config.SpeakerIdMap.Keys));
                                    ctx.ExitCode = 1;
                                    return;
                                }
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
                                        jsonlPhonemizer = ResolveTextModePhonemizer(language);
                                    }
                                    catch (NotSupportedException ex)
                                    {
                                        LogError(ex.Message);
                                        ctx.ExitCode = 1;
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
                                    ctx.ExitCode = 1;
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
                                ctx.ExitCode = 1;
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
                            ctx.ExitCode = 1;
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
                        ctx.ExitCode = 0;
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
                var phonemizerType = Type.GetType(
                    "PiperPlus.Core.Phonemize.EnglishPhonemizer, PiperPlus.Core");
                if (phonemizerType is null)
                {
                    throw new NotSupportedException(
                        "--text mode for English requires EnglishPhonemizer, " +
                        "which is not yet available.");
                }

                var phonemizer = Activator.CreateInstance(phonemizerType) as IPhonemizer
                    ?? throw new NotSupportedException(
                        "Failed to create EnglishPhonemizer instance.");

                return phonemizer;
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
                    // Per-utterance output_file from JSONL
                    wavPath = Path.IsPathRooted(uttOutputFile)
                        ? uttOutputFile
                        : Path.Combine(outputDir.FullName, uttOutputFile);
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
