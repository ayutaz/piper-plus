using System.Text.Json;
using System.Text.Json.Serialization;

namespace PiperPlus.Core.Config;

/// <summary>
/// Represents the deserialized config.json used by Piper TTS models.
/// All JSON keys use snake_case and are mapped via <see cref="JsonPropertyNameAttribute"/>.
/// </summary>
public sealed class PiperConfig
{
    // ----------------------------------------------------------------
    // Required fields
    // ----------------------------------------------------------------

    [JsonPropertyName("num_speakers")]
    public int NumSpeakers { get; set; }

    /// <summary>
    /// Maps each phoneme (single codepoint, including PUA U+E000-U+E01C) to an array of
    /// integer IDs.  Keys: "_"=PAD, "^"=BOS, "$"=EOS, plus language-specific phonemes.
    /// </summary>
    [JsonPropertyName("phoneme_id_map")]
    public Dictionary<string, int[]> PhonemeIdMap { get; set; } = null!;

    [JsonPropertyName("audio")]
    public AudioConfig Audio { get; set; } = null!;

    [JsonPropertyName("inference")]
    public InferenceConfig Inference { get; set; } = null!;

    // ----------------------------------------------------------------
    // Optional fields
    // ----------------------------------------------------------------

    /// <summary>
    /// Phoneme type: "openjtalk", "text", or null (espeak default).
    /// </summary>
    [JsonPropertyName("phoneme_type")]
    public string? PhonemeType { get; set; }

    /// <summary>
    /// Legacy espeak-ng phonemizer config. piper-plus does NOT depend on
    /// espeak-ng (GPL-free design — see CONTRIBUTING.md "espeak-ng Policy");
    /// this property exists only for backward-compatible deserialization of
    /// older config.json files. New models should leave this <c>null</c>.
    /// </summary>
    [JsonPropertyName("espeak")]
    public EspeakConfig? Espeak { get; set; }

    /// <summary>
    /// Maps speaker names to integer IDs, e.g. {"speaker_1": 0}.
    /// </summary>
    [JsonPropertyName("speaker_id_map")]
    public Dictionary<string, int>? SpeakerIdMap { get; set; }

    /// <summary>
    /// Maps phoneme codepoints to replacement phoneme codepoint arrays.
    /// </summary>
    [JsonPropertyName("phoneme_map")]
    public Dictionary<string, string[]>? PhonemeMap { get; set; }

    /// <summary>
    /// Number of languages for multilingual models.
    /// </summary>
    [JsonPropertyName("num_languages")]
    public int? NumLanguages { get; set; }

    /// <summary>
    /// Maps language codes (e.g. "ja", "en") to integer IDs for the <c>lid</c> ONNX input.
    /// </summary>
    [JsonPropertyName("language_id_map")]
    public Dictionary<string, int>? LanguageIdMap { get; set; }

    /// <summary>
    /// Number of prosody symbols (prosody models only).
    /// </summary>
    [JsonPropertyName("prosody_num_symbols")]
    public int? ProsodyNumSymbols { get; set; }

    /// <summary>
    /// Maps prosody symbol strings to ID arrays (prosody models only).
    /// </summary>
    [JsonPropertyName("prosody_id_map")]
    public Dictionary<string, int[]>? ProsodyIdMap { get; set; }

    // ----------------------------------------------------------------
    // Static factory / search methods
    // ----------------------------------------------------------------

    /// <summary>
    /// Locate config.json using the standard search order:
    /// <list type="number">
    ///   <item><description><paramref name="explicitPath"/> if provided</description></item>
    ///   <item><description><c>PIPER_DEFAULT_CONFIG</c> environment variable</description></item>
    ///   <item><description><c>{modelPath}.json</c> (e.g. model.onnx.json)</description></item>
    ///   <item><description><c>{modelDir}/config.json</c></description></item>
    /// </list>
    /// </summary>
    /// <returns>Resolved path, or <c>null</c> if none found.</returns>
    public static string? FindConfigPath(string? explicitPath, string? modelPath)
    {
        // 1. Explicit --config path
        if (!string.IsNullOrEmpty(explicitPath))
        {
            return File.Exists(explicitPath) ? explicitPath : null;
        }

        // 2. PIPER_DEFAULT_CONFIG environment variable
        var envPath = Environment.GetEnvironmentVariable("PIPER_DEFAULT_CONFIG");
        if (!string.IsNullOrEmpty(envPath) && File.Exists(envPath))
        {
            return envPath;
        }

        if (string.IsNullOrEmpty(modelPath))
        {
            return null;
        }

        // 3. {model_path}.json  (e.g. model.onnx.json)
        var modelJsonPath = modelPath + ".json";
        if (File.Exists(modelJsonPath))
        {
            return modelJsonPath;
        }

        // 4. {model_dir}/config.json
        var modelDir = Path.GetDirectoryName(modelPath);
        if (!string.IsNullOrEmpty(modelDir))
        {
            var dirConfigPath = Path.Combine(modelDir, "config.json");
            if (File.Exists(dirConfigPath))
            {
                return dirConfigPath;
            }
        }

        return null;
    }

    /// <summary>
    /// Deserialize a <see cref="PiperConfig"/> from a JSON file on disk.
    /// Throws <see cref="FileNotFoundException"/> if the file does not exist,
    /// <see cref="InvalidOperationException"/> if required fields are missing.
    /// </summary>
    public static PiperConfig LoadFromFile(string configPath)
    {
        if (!File.Exists(configPath))
        {
            throw new FileNotFoundException(
                $"Config file not found: {configPath}", configPath);
        }

        using var stream = File.OpenRead(configPath);
        var config = JsonSerializer.Deserialize(
            stream, PiperConfigJsonContext.Default.PiperConfig);

        if (config is null)
        {
            throw new InvalidOperationException(
                $"Failed to deserialize config from: {configPath}");
        }

        Validate(config, configPath);
        return config;
    }

    // ----------------------------------------------------------------
    // Validation
    // ----------------------------------------------------------------

    private static void Validate(PiperConfig config, string path)
    {
        if (config.PhonemeIdMap is null || config.PhonemeIdMap.Count == 0)
        {
            throw new InvalidOperationException(
                $"phoneme_id_map is missing or empty in: {path}");
        }

        if (config.Audio is null)
        {
            throw new InvalidOperationException(
                $"audio section is missing in: {path}");
        }

        if (config.Inference is null)
        {
            throw new InvalidOperationException(
                $"inference section is missing in: {path}");
        }
    }
}

/// <summary>
/// "audio" section of config.json.
/// </summary>
public sealed class AudioConfig
{
    [JsonPropertyName("sample_rate")]
    public int SampleRate { get; set; } = 22050;

    /// <summary>
    /// Frame shift in samples; used for phoneme timing calculations.
    /// </summary>
    [JsonPropertyName("hop_size")]
    public int? HopSize { get; set; }
}

/// <summary>
/// "inference" section of config.json.
/// </summary>
public sealed class InferenceConfig
{
    [JsonPropertyName("noise_scale")]
    public float NoiseScale { get; set; } = 0.667f;

    [JsonPropertyName("length_scale")]
    public float LengthScale { get; set; } = 1.0f;

    [JsonPropertyName("noise_w")]
    public float NoiseW { get; set; } = 0.8f;
}

/// <summary>
/// "espeak" section of config.json.
/// </summary>
public sealed class EspeakConfig
{
    [JsonPropertyName("voice")]
    public string? Voice { get; set; }
}

/// <summary>
/// Source-generated JSON serializer context for trim-safe / AOT-safe deserialization.
/// <see cref="JsonSerializerIsReflectionEnabledByDefault"/> is disabled in
/// Directory.Build.props, so this context is required.
/// </summary>
[JsonSerializable(typeof(PiperConfig))]
[JsonSourceGenerationOptions(
    PropertyNameCaseInsensitive = false,
    ReadCommentHandling = JsonCommentHandling.Skip,
    AllowTrailingCommas = true)]
internal partial class PiperConfigJsonContext : JsonSerializerContext;
