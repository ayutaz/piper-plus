using System.Text.Json;
using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PiperConfig"/>.
/// Covers deserialization from JSON (including PUA character keys),
/// validation of required fields, and config.json path resolution.
/// </summary>
public sealed class PiperConfigTests : IDisposable
{
    private readonly string _tempDir;

    public PiperConfigTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"piperconfig_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
    }

    // ================================================================
    // Helper
    // ================================================================

    /// <summary>
    /// Writes <paramref name="json"/> to a temp file and returns the path.
    /// </summary>
    private string WriteTempConfig(string json, string fileName = "config.json")
    {
        var path = Path.Combine(_tempDir, fileName);
        File.WriteAllText(path, json);
        return path;
    }

    // ================================================================
    // Deserialization tests
    // ================================================================

    [Fact]
    public void BasicConfig_Deserializes()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": {
            "_": [0], "^": [1], "$": [2],
            "a": [10]
          },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json);
        var config = PiperConfig.LoadFromFile(path);

        Assert.Equal(1, config.NumSpeakers);
        Assert.NotNull(config.PhonemeIdMap);
        Assert.Equal(4, config.PhonemeIdMap.Count);
        Assert.Equal([0], config.PhonemeIdMap["_"]);
        Assert.Equal([1], config.PhonemeIdMap["^"]);
        Assert.Equal([2], config.PhonemeIdMap["$"]);
        Assert.Equal([10], config.PhonemeIdMap["a"]);
        Assert.Equal(22050, config.Audio.SampleRate);
        Assert.Equal(0.667f, config.Inference.NoiseScale);
        Assert.Equal(1.0f, config.Inference.LengthScale);
        Assert.Equal(0.8f, config.Inference.NoiseW);
    }

    [Fact]
    public void PuaCharacterKeys_DeserializeCorrectly()
    {
        // PUA characters U+E000 and U+E005 encoded as JSON \uE000 / \uE005.
        // These are used for extended Japanese phonemes (question markers, N variants, etc.).
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": {
            "_": [0], "^": [1], "$": [2],
            "a": [10],
            "\uE000": [17],
            "\uE005": [22],
            "\uE016": [50],
            "\uE019": [60],
            "\uE01C": [63]
          },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json);
        var config = PiperConfig.LoadFromFile(path);

        // Verify PUA characters survive the JSON round-trip as single-codepoint strings.
        Assert.Equal([17], config.PhonemeIdMap["\uE000"]);
        Assert.Equal([22], config.PhonemeIdMap["\uE005"]);
        Assert.Equal([50], config.PhonemeIdMap["\uE016"]); // ?! question marker
        Assert.Equal([60], config.PhonemeIdMap["\uE019"]); // N_m bilabial
        Assert.Equal([63], config.PhonemeIdMap["\uE01C"]); // N_uvular

        // Ensure the Dictionary key is truly the PUA char, not an escape sequence.
        Assert.True(config.PhonemeIdMap.ContainsKey("\uE000"));
        Assert.Equal(0xE000, (int)config.PhonemeIdMap.Keys.First(k => k.Length == 1 && k[0] == '\uE000')[0]);
    }

    [Fact]
    public void FullConfig_AllFieldsDeserialized()
    {
        const string json = """
        {
          "num_speakers": 20,
          "phoneme_type": "openjtalk",
          "espeak": { "voice": "en-us" },
          "phoneme_id_map": {
            "_": [0], "^": [1], "$": [2],
            "a": [10], "i": [11], "u": [12],
            "\uE000": [17], "\uE005": [22]
          },
          "phoneme_map": {
            "a": ["a"],
            "b": ["b"]
          },
          "audio": { "sample_rate": 22050, "hop_size": 256 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 },
          "speaker_id_map": { "speaker_0": 0, "speaker_1": 1 },
          "prosody_num_symbols": 11,
          "prosody_id_map": {
            "0": [0], "1": [1], "2": [2], "10": [10]
          }
        }
        """;

        var path = WriteTempConfig(json);
        var config = PiperConfig.LoadFromFile(path);

        // Required fields
        Assert.Equal(20, config.NumSpeakers);
        Assert.Equal(8, config.PhonemeIdMap.Count);
        Assert.Equal(22050, config.Audio.SampleRate);
        Assert.Equal(256, config.Audio.HopSize);
        Assert.Equal(0.667f, config.Inference.NoiseScale);
        Assert.Equal(1.0f, config.Inference.LengthScale);
        Assert.Equal(0.8f, config.Inference.NoiseW);

        // Optional fields
        Assert.Equal("openjtalk", config.PhonemeType);
        Assert.NotNull(config.Espeak);
        Assert.Equal("en-us", config.Espeak!.Voice);

        Assert.NotNull(config.PhonemeMap);
        Assert.Equal(2, config.PhonemeMap!.Count);
        Assert.Equal(["a"], config.PhonemeMap["a"]);

        Assert.NotNull(config.SpeakerIdMap);
        Assert.Equal(2, config.SpeakerIdMap!.Count);
        Assert.Equal(0, config.SpeakerIdMap["speaker_0"]);
        Assert.Equal(1, config.SpeakerIdMap["speaker_1"]);

        Assert.Equal(11, config.ProsodyNumSymbols);
        Assert.NotNull(config.ProsodyIdMap);
        Assert.Equal(4, config.ProsodyIdMap!.Count);
        Assert.Equal([0], config.ProsodyIdMap["0"]);
        Assert.Equal([10], config.ProsodyIdMap["10"]);
    }

    [Fact]
    public void MissingAudio_ThrowsException()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "missing_audio.json");
        var ex = Assert.Throws<InvalidOperationException>(() => PiperConfig.LoadFromFile(path));
        Assert.Contains("audio", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void MissingPhonemeIdMap_ThrowsException()
    {
        const string json = """
        {
          "num_speakers": 1,
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "missing_phoneme_id_map.json");
        var ex = Assert.Throws<InvalidOperationException>(() => PiperConfig.LoadFromFile(path));
        Assert.Contains("phoneme_id_map", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SpeakerIdMap_Deserializes()
    {
        const string json = """
        {
          "num_speakers": 3,
          "phoneme_id_map": { "_": [0] },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 },
          "speaker_id_map": {
            "alice": 0,
            "bob": 1,
            "charlie": 2
          }
        }
        """;

        var path = WriteTempConfig(json);
        var config = PiperConfig.LoadFromFile(path);

        Assert.NotNull(config.SpeakerIdMap);
        Assert.Equal(3, config.SpeakerIdMap!.Count);
        Assert.Equal(0, config.SpeakerIdMap["alice"]);
        Assert.Equal(1, config.SpeakerIdMap["bob"]);
        Assert.Equal(2, config.SpeakerIdMap["charlie"]);
    }

    [Fact]
    public void ProsodyFields_Deserialize()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 },
          "prosody_num_symbols": 11,
          "prosody_id_map": {
            "0": [0], "1": [1], "2": [2], "3": [3], "4": [4],
            "5": [5], "6": [6], "7": [7], "8": [8], "9": [9], "10": [10]
          }
        }
        """;

        var path = WriteTempConfig(json);
        var config = PiperConfig.LoadFromFile(path);

        Assert.Equal(11, config.ProsodyNumSymbols);
        Assert.NotNull(config.ProsodyIdMap);
        Assert.Equal(11, config.ProsodyIdMap!.Count);

        // Verify a few entries
        Assert.Equal([0], config.ProsodyIdMap["0"]);
        Assert.Equal([5], config.ProsodyIdMap["5"]);
        Assert.Equal([10], config.ProsodyIdMap["10"]);
    }

    [Fact]
    public void UnknownFields_Ignored()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0], "a": [10] },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 },
          "unknown_field": "should be ignored",
          "another_future_field": { "nested": true },
          "dataset": "some-dataset-name"
        }
        """;

        var path = WriteTempConfig(json, "unknown_fields.json");
        var config = PiperConfig.LoadFromFile(path);

        // The config should load successfully, ignoring unknown fields.
        Assert.Equal(1, config.NumSpeakers);
        Assert.Equal(2, config.PhonemeIdMap.Count);
    }

    // ================================================================
    // FindConfigPath tests
    // ================================================================

    [Fact]
    public void FindConfigPath_ExplicitPath_ReturnsIt()
    {
        var configPath = WriteTempConfig("{}", "explicit.json");

        var result = PiperConfig.FindConfigPath(configPath, modelPath: null);

        Assert.Equal(configPath, result);
    }

    [Fact]
    public void FindConfigPath_ExplicitPath_NonExistent_ReturnsNull()
    {
        var nonExistent = Path.Combine(_tempDir, "does_not_exist.json");

        var result = PiperConfig.FindConfigPath(nonExistent, modelPath: null);

        Assert.Null(result);
    }

    [Fact]
    public void FindConfigPath_ModelPathPlusJson()
    {
        // Create model.onnx.json next to the "model"
        var modelPath = Path.Combine(_tempDir, "model.onnx");
        var configPath = modelPath + ".json";
        File.WriteAllText(configPath, "{}");

        var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath);

        Assert.Equal(configPath, result);
    }

    [Fact]
    public void FindConfigPath_DirConfigJson_Fallback()
    {
        // Create config.json in the model's directory
        var modelPath = Path.Combine(_tempDir, "model.onnx");
        var configPath = Path.Combine(_tempDir, "config.json");
        File.WriteAllText(configPath, "{}");

        var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath);

        Assert.Equal(configPath, result);
    }

    [Fact]
    public void FindConfigPath_NoneFound_ReturnsNull()
    {
        // Point to a model path where no config.json variants exist.
        var modelPath = Path.Combine(_tempDir, "subdir", "model.onnx");

        var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath);

        Assert.Null(result);
    }

    [Fact]
    public void FindConfigPath_BothNull_ReturnsNull()
    {
        var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath: null);

        Assert.Null(result);
    }

    // ================================================================
    // Environment variable tests
    // ================================================================

    [Fact]
    public void FindConfigPath_EnvironmentVariable_ReturnsIt()
    {
        var configPath = WriteTempConfig("{}", "env_config.json");
        var originalValue = Environment.GetEnvironmentVariable("PIPER_DEFAULT_CONFIG");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", configPath);

            var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath: null);

            Assert.Equal(configPath, result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", originalValue);
        }
    }

    [Fact]
    public void FindConfigPath_EnvironmentVariable_NonExistent_SkipsToNext()
    {
        var nonExistent = Path.Combine(_tempDir, "does_not_exist_env.json");
        var modelPath = Path.Combine(_tempDir, "model.onnx");
        var modelJsonPath = modelPath + ".json";
        File.WriteAllText(modelJsonPath, "{}");

        var originalValue = Environment.GetEnvironmentVariable("PIPER_DEFAULT_CONFIG");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", nonExistent);

            var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath);

            // Env var file doesn't exist, so it should fall through to model.onnx.json
            Assert.Equal(modelJsonPath, result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", originalValue);
        }
    }

    [Fact]
    public void FindConfigPath_EnvironmentVariable_Priority()
    {
        // Both env var file and model.onnx.json exist — env var should win
        var envConfigPath = WriteTempConfig("{}", "env_priority.json");
        var modelPath = Path.Combine(_tempDir, "model.onnx");
        var modelJsonPath = modelPath + ".json";
        File.WriteAllText(modelJsonPath, "{}");

        var originalValue = Environment.GetEnvironmentVariable("PIPER_DEFAULT_CONFIG");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", envConfigPath);

            var result = PiperConfig.FindConfigPath(explicitPath: null, modelPath);

            Assert.Equal(envConfigPath, result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_DEFAULT_CONFIG", originalValue);
        }
    }

    // ================================================================
    // Malformed JSON tests
    // ================================================================

    [Fact]
    public void LoadFromFile_MalformedJson_ThrowsException()
    {
        var path = WriteTempConfig("{invalid json}", "malformed.json");

        Assert.ThrowsAny<JsonException>(() => PiperConfig.LoadFromFile(path));
    }

    [Fact]
    public void LoadFromFile_EmptyFile_ThrowsException()
    {
        var path = WriteTempConfig("", "empty.json");

        Assert.ThrowsAny<JsonException>(() => PiperConfig.LoadFromFile(path));
    }

    [Fact]
    public void LoadFromFile_JsonNull_ThrowsException()
    {
        var path = WriteTempConfig("null", "json_null.json");

        Assert.Throws<InvalidOperationException>(() => PiperConfig.LoadFromFile(path));
    }

    // ================================================================
    // Default value tests
    // ================================================================

    [Fact]
    public void Audio_SampleRate_DefaultValue_22050()
    {
        // audio section present but sample_rate omitted — should default to 22050
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "audio": {},
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "default_sample_rate.json");
        var config = PiperConfig.LoadFromFile(path);

        Assert.Equal(22050, config.Audio.SampleRate);
    }

    [Fact]
    public void Inference_DefaultValues_WhenFieldsOmitted()
    {
        // inference section present but all fields omitted — should use defaults
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "audio": { "sample_rate": 22050 },
          "inference": {}
        }
        """;

        var path = WriteTempConfig(json, "default_inference.json");
        var config = PiperConfig.LoadFromFile(path);

        Assert.Equal(0.667f, config.Inference.NoiseScale);
        Assert.Equal(1.0f, config.Inference.LengthScale);
        Assert.Equal(0.8f, config.Inference.NoiseW);
    }

    // ================================================================
    // Edge cases
    // ================================================================

    [Fact]
    public void LoadFromFile_EmptyPhonemeIdMap_ThrowsException()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": {},
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "empty_phoneme_map.json");
        var ex = Assert.Throws<InvalidOperationException>(() => PiperConfig.LoadFromFile(path));
        Assert.Contains("phoneme_id_map", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PhonemeIdMap_MultipleIds_DeserializedCorrectly()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": {
            "_": [0],
            "a": [10, 11, 12]
          },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "multi_ids.json");
        var config = PiperConfig.LoadFromFile(path);

        Assert.Equal(3, config.PhonemeIdMap["a"].Length);
        Assert.Equal([10, 11, 12], config.PhonemeIdMap["a"]);
    }

    [Fact]
    public void LoadFromFile_NonExistentFile_ThrowsFileNotFound()
    {
        var bogusPath = Path.Combine(_tempDir, "no_such_file.json");

        Assert.Throws<FileNotFoundException>(() => PiperConfig.LoadFromFile(bogusPath));
    }

    [Fact]
    public void MissingInference_ThrowsException()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "audio": { "sample_rate": 22050 }
        }
        """;

        var path = WriteTempConfig(json, "missing_inference.json");
        var ex = Assert.Throws<InvalidOperationException>(() => PiperConfig.LoadFromFile(path));
        Assert.Contains("inference", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OptionalFields_DefaultToNull_WhenAbsent()
    {
        const string json = """
        {
          "num_speakers": 1,
          "phoneme_id_map": { "_": [0] },
          "audio": { "sample_rate": 22050 },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        var path = WriteTempConfig(json, "minimal.json");
        var config = PiperConfig.LoadFromFile(path);

        Assert.Null(config.PhonemeType);
        Assert.Null(config.Espeak);
        Assert.Null(config.SpeakerIdMap);
        Assert.Null(config.PhonemeMap);
        Assert.Null(config.ProsodyNumSymbols);
        Assert.Null(config.ProsodyIdMap);
        Assert.Null(config.Audio.HopSize);
    }
}
