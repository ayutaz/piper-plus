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

    [JsonPropertyName("prosody_features")]
    public int[][]? ProsodyFeatures { get; set; }
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

                if (string.IsNullOrEmpty(modelPath))
                {
                    LogError("--model is required (or set PIPER_DEFAULT_MODEL).");
                    ctx.ExitCode = 1;
                    return;
                }

                if (!File.Exists(modelPath))
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

                if (string.IsNullOrEmpty(configPath))
                {
                    LogError(
                        $"config.json not found. Searched: {modelPath}.json, " +
                        $"{Path.GetDirectoryName(modelPath)}/config.json. " +
                        "Use --config to specify.");
                    ctx.ExitCode = 1;
                    return;
                }

                LogDebug(debug, quiet, $"Config path: {configPath}");

                PiperConfig config;
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

                LogDebug(debug, quiet, $"Model path: {modelPath}");
                LogDebug(debug, quiet, $"Sample rate: {config.Audio.SampleRate}");
                LogInfo(quiet, $"Loading model: {modelPath}");

                // Create ONNX InferenceSession
                InferenceSession session;
                try
                {
                    var sessionOptions = new SessionOptions();
                    session = new InferenceSession(modelPath, sessionOptions);
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

                // Create PiperSession for inference
                var piperSession = new PiperSession(model);

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

                int sampleRate = model.SampleRate;
                piperSession.SentenceSilenceSeconds = sentenceSilence;

                // Determine output mode
                OutputMode outputMode;
                if (outputRaw)
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

                    // Synthesize
                    short[] audio;
                    try
                    {
                        var synthesisInput = new SynthesisInput(
                            PhonemeIds: phonemeIdsLong,
                            SpeakerId: speaker,
                            ProsodyFeatures: prosodyFlat,
                            NoiseScale: noiseScale,
                            LengthScale: lengthScale,
                            NoiseW: noiseW);
                        audio = piperSession.Synthesize(synthesisInput);
                    }
                    catch (Exception ex)
                    {
                        LogError($"Synthesis failed: {ex.Message}");
                        ctx.ExitCode = 1;
                        return;
                    }

                    // Write output
                    WriteTextModeOutput(
                        outputMode, outputRaw, outputFile, outputDir,
                        audio, sampleRate, quiet);

                    LogInfo(quiet, "Synthesized 1 utterance(s).");
                    ctx.ExitCode = 0;
                    return;
                }

                // ================================================================
                // JSONL stdin mode (existing behavior)
                // ================================================================

                // Open stdout stream once for raw/wav stdout modes (avoid re-opening per utterance)
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

                        if (utterance?.PhonemeIds is null || utterance.PhonemeIds.Length == 0)
                        {
                            LogError($"Missing or empty phoneme_ids on line {utteranceIndex + 1}.");
                            ctx.ExitCode = 1;
                            return;
                        }

                        // Resolve per-utterance parameters
                        int uttSpeaker = utterance.SpeakerId ?? speaker;

                        // Convert int[] → long[] for ONNX tensor (int64)
                        long[] phonemeIdsLong = Array.ConvertAll(
                            utterance.PhonemeIds, id => (long)id);

                        // Convert int[][] → flat long[] for prosody features
                        long[]? prosodyFlat = null;
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

                        LogDebug(debug, quiet,
                            $"Utterance {utteranceIndex}: phonemes={utterance.PhonemeIds.Length}, " +
                            $"speaker={uttSpeaker}");

                        // Run inference (sentence silence is handled by PiperSession)
                        short[] audio;
                        try
                        {
                            var synthesisInput = new SynthesisInput(
                                PhonemeIds: phonemeIdsLong,
                                SpeakerId: uttSpeaker,
                                ProsodyFeatures: prosodyFlat,
                                NoiseScale: noiseScale,
                                LengthScale: lengthScale,
                                NoiseW: noiseW);
                            audio = piperSession.Synthesize(synthesisInput);
                        }
                        catch (Exception ex)
                        {
                            LogError($"Synthesis failed on line {utteranceIndex + 1}: {ex.Message}");
                            ctx.ExitCode = 1;
                            return;
                        }

                        // Determine output target for this utterance
                        string? uttOutputFile = utterance.OutputFile;

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

                        utteranceIndex++;
                    }

                    if (utteranceIndex == 0 && jsonInput)
                    {
                        LogError("No input received on stdin.");
                        ctx.ExitCode = 1;
                        return;
                    }

                    LogInfo(quiet, $"Synthesized {utteranceIndex} utterance(s).");
                    ctx.ExitCode = 0;
                }
                finally
                {
                    stdoutStream?.Dispose();
                }
            });

        return rootCommand;
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
                // JapanesePhonemizer requires an IJapaneseG2PEngine (DotNetG2P wrapper).
                // The DotNetG2P NuGet package may not yet be available; try to resolve
                // via reflection so the CLI compiles even before the concrete type exists.
                var g2pType = Type.GetType(
                    "PiperPlus.Core.Phonemize.DotNetG2PEngine, PiperPlus.Core");
                if (g2pType is null)
                {
                    throw new NotSupportedException(
                        "--text mode for Japanese requires DotNetG2P, which is not yet available. " +
                        "Use JSONL stdin input instead.");
                }

                var g2pEngine = Activator.CreateInstance(g2pType)
                    ?? throw new NotSupportedException(
                        "Failed to create DotNetG2PEngine instance.");

                var phonemizerType = Type.GetType(
                    "PiperPlus.Core.Phonemize.JapanesePhonemizer, PiperPlus.Core");
                if (phonemizerType is null)
                {
                    throw new NotSupportedException(
                        "--text mode for Japanese requires JapanesePhonemizer, " +
                        "which is not yet available.");
                }

                var phonemizer = Activator.CreateInstance(phonemizerType, g2pEngine) as IPhonemizer
                    ?? throw new NotSupportedException(
                        "Failed to create JapanesePhonemizer instance.");

                return phonemizer;
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
