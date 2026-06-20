using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// End-to-end tests that exercise the full zero-shot TTS inference pipeline
/// using real ONNX model files from <c>test/models/</c>.
/// </summary>
/// <remarks>
/// <para>
/// All tests call <see cref="Assert.Skip"/> when the model file is absent so
/// that the suite stays green in environments (CI, developer machines) where
/// the test artefacts have not been provisioned.
/// </para>
/// <para>
/// Path resolution: the test model directory is located by walking up from the
/// test assembly location until the repository root is found, then descending
/// into <c>test/models/</c>. This mirrors the approach used in
/// <see cref="CliIntegrationTests"/>.
/// </para>
/// </remarks>
public sealed class ZeroShotE2ETests : IDisposable
{
    // ------------------------------------------------------------------
    // Constants
    // ------------------------------------------------------------------

    private const string ModelFileName = "zero-shot-test.onnx";
    private const string SpeakerEmbeddingFileName = "test_speaker.npy";
    private const int EmbeddingDim = 192;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------

    private readonly string? _modelDir;

    // ------------------------------------------------------------------
    // Constructor
    // ------------------------------------------------------------------

    public ZeroShotE2ETests()
    {
        _modelDir = ResolveTestModelsDir();
    }

    // ------------------------------------------------------------------
    // IDisposable
    // ------------------------------------------------------------------

    public void Dispose() { /* nothing to dispose */ }

    // ------------------------------------------------------------------
    // Helper: locate test/models directory
    // ------------------------------------------------------------------

    /// <summary>
    /// Walks up from the test assembly directory until it finds a directory
    /// that contains a <c>test/models</c> subdirectory (the repository root).
    /// Returns <c>null</c> when not found so that tests can skip gracefully.
    /// </summary>
    private static string? ResolveTestModelsDir()
    {
        string assemblyDir = Path.GetDirectoryName(
            typeof(ZeroShotE2ETests).Assembly.Location)!;

        var dir = new DirectoryInfo(assemblyDir);

        while (dir is not null)
        {
            string candidate = Path.Combine(dir.FullName, "test", "models");
            if (Directory.Exists(candidate))
            {
                return candidate;
            }

            dir = dir.Parent;
        }

        return null;
    }

    // ------------------------------------------------------------------
    // Helper: skip if the model file is not available
    // ------------------------------------------------------------------

    private string RequireModelPath()
    {
        if (_modelDir is null)
        {
            Assert.Skip(
                "Could not locate test/models directory. " +
                "Run tests from within the repository.");
        }

        var modelPath = Path.Combine(_modelDir!, ModelFileName);

        if (!File.Exists(modelPath))
        {
            Assert.Skip(
                $"Test model not found: {modelPath}. " +
                "Place zero-shot-test.onnx in test/models/ to enable these tests.");
        }

        return modelPath;
    }

    // ------------------------------------------------------------------
    // Helper: build a minimal PiperConfig for the test model
    // ------------------------------------------------------------------

    /// <summary>
    /// Builds a <see cref="PiperConfig"/> suitable for the test model.
    /// The config file on disk has an empty <c>phoneme_id_map</c>, so we
    /// construct the config programmatically rather than calling
    /// <see cref="PiperConfig.LoadFromFile"/> (which would fail validation).
    /// </summary>
    private static PiperConfig BuildTestConfig() =>
        new()
        {
            NumSpeakers = 2,
            PhonemeIdMap = new Dictionary<string, int[]>
            {
                ["_"] = [0],
                ["^"] = [1],
                ["$"] = [2],
            },
            Audio = new AudioConfig { SampleRate = 22050 },
            Inference = new InferenceConfig
            {
                NoiseScale = 0.4f,
                LengthScale = 1.0f,
                NoiseW = 0.5f,
            },
        };

    // ------------------------------------------------------------------
    // Helper: load a speaker embedding from an .npy file
    // ------------------------------------------------------------------

    /// <summary>
    /// Loads a NumPy v1.0 .npy or raw-binary speaker embedding.
    /// Returns a zero vector when the file is absent (caller handles skip).
    /// </summary>
    private static float[] LoadNpyEmbedding(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);

        float[] embedding;

        // Detect NumPy .npy magic: \x93NUMPY
        if (bytes.Length >= 10
            && bytes[0] == 0x93 && bytes[1] == (byte)'N'
            && bytes[2] == (byte)'U' && bytes[3] == (byte)'M'
            && bytes[4] == (byte)'P' && bytes[5] == (byte)'Y')
        {
            // v1.0: header_len is uint16 at offset 8
            int headerLen = BitConverter.ToUInt16(bytes, 8);
            int dataOffset = 6 + 2 + 2 + headerLen; // magic(6) + ver(2) + headerLen(2) + header
            int numFloats = (bytes.Length - dataOffset) / sizeof(float);
            embedding = new float[numFloats];
            Buffer.BlockCopy(bytes, dataOffset, embedding, 0, numFloats * sizeof(float));
        }
        else
        {
            int numFloats = bytes.Length / sizeof(float);
            embedding = new float[numFloats];
            Buffer.BlockCopy(bytes, 0, embedding, 0, numFloats * sizeof(float));
        }

        if (embedding.Length != EmbeddingDim)
        {
            var padded = new float[EmbeddingDim];
            Array.Copy(embedding, padded, Math.Min(embedding.Length, EmbeddingDim));
            return padded;
        }

        return embedding;
    }

    // ------------------------------------------------------------------
    // Helper: minimal phoneme ID sequence (BOS + silence + EOS)
    // ------------------------------------------------------------------

    /// <summary>
    /// Returns a minimal but well-formed phoneme ID sequence:
    /// BOS(1), eight silence/dummy phonemes(0), EOS(2).
    /// Sufficient to produce a short audio burst from the model.
    /// </summary>
    private static long[] MinimalPhonemeIds() =>
        [1L, 0L, 0L, 0L, 0L, 0L, 0L, 0L, 0L, 2L];

    // ------------------------------------------------------------------
    // Test 1: inference produces non-empty audio with finite values
    // ------------------------------------------------------------------

    [Fact]
    public void ZeroShot_Inference_ProducesAudio()
    {
        string modelPath = RequireModelPath();
        string speakerPath = Path.Combine(_modelDir!, SpeakerEmbeddingFileName);

        if (!File.Exists(speakerPath))
        {
            Assert.Skip(
                $"Speaker embedding not found: {speakerPath}. " +
                "Place test_speaker.npy in test/models/ to enable this test.");
        }

        float[] embedding = LoadNpyEmbedding(speakerPath);

        using var session = SessionFactory.Create(modelPath);
        var config = BuildTestConfig();
        using var model = new PiperModel(session, config);
        var piperSession = new PiperSession(model) { SentenceSilenceSeconds = 0f };

        var input = new SynthesisInput(
            PhonemeIds: MinimalPhonemeIds(),
            SpeakerEmbedding: embedding);

        float[] audio = piperSession.SynthesizeToFloat(input);

        // Must produce at least some output samples.
        Assert.NotEmpty(audio);

        // All samples must be finite (no NaN or Inf).
        Assert.All(audio, sample =>
            Assert.True(float.IsFinite(sample),
                $"Audio sample is not finite: {sample}"));
    }

    // ------------------------------------------------------------------
    // Test 2: different embeddings produce different audio
    // ------------------------------------------------------------------

    [Fact]
    public void ZeroShot_DifferentEmbeddings_ProduceDifferentAudio()
    {
        string modelPath = RequireModelPath();

        using var session = SessionFactory.Create(modelPath);
        var config = BuildTestConfig();
        using var model = new PiperModel(session, config);
        var piperSession = new PiperSession(model) { SentenceSilenceSeconds = 0f };

        // Embedding A: all 0.5
        float[] embeddingA = new float[EmbeddingDim];
        Array.Fill(embeddingA, 0.5f);

        // Embedding B: all -0.5 (maximally different direction)
        float[] embeddingB = new float[EmbeddingDim];
        Array.Fill(embeddingB, -0.5f);

        var inputA = new SynthesisInput(
            PhonemeIds: MinimalPhonemeIds(),
            SpeakerEmbedding: embeddingA);

        var inputB = new SynthesisInput(
            PhonemeIds: MinimalPhonemeIds(),
            SpeakerEmbedding: embeddingB);

        float[] audioA = piperSession.SynthesizeToFloat(inputA);
        float[] audioB = piperSession.SynthesizeToFloat(inputB);

        // Both must produce output.
        Assert.NotEmpty(audioA);
        Assert.NotEmpty(audioB);

        // The outputs must differ (stochastic model with different speaker
        // conditioning should not produce identical waveforms).
        bool anyDifference = false;
        int len = Math.Min(audioA.Length, audioB.Length);
        for (int i = 0; i < len; i++)
        {
            if (Math.Abs(audioA[i] - audioB[i]) > 1e-6f)
            {
                anyDifference = true;
                break;
            }
        }

        Assert.True(anyDifference,
            "Audio produced from different speaker embeddings must differ.");
    }

    // ------------------------------------------------------------------
    // Test 3: zero embedding does not throw
    // ------------------------------------------------------------------

    [Fact]
    public void ZeroShot_ZeroEmbedding_DoesNotThrow()
    {
        string modelPath = RequireModelPath();

        using var session = SessionFactory.Create(modelPath);
        var config = BuildTestConfig();
        using var model = new PiperModel(session, config);
        var piperSession = new PiperSession(model) { SentenceSilenceSeconds = 0f };

        // All-zeros embedding: the model should accept it gracefully.
        float[] zeroEmbedding = new float[EmbeddingDim]; // zero-initialized by default

        var input = new SynthesisInput(
            PhonemeIds: MinimalPhonemeIds(),
            SpeakerEmbedding: zeroEmbedding);

        // Must not throw; audio quality is not checked here.
        float[] audio = piperSession.SynthesizeToFloat(input);

        Assert.NotNull(audio);
    }
}
