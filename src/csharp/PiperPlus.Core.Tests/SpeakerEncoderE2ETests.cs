using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Serialization;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// E2E cosine gate for the speaker encoder. Mirrors
/// <c>test/test_speaker_encoder_e2e.py</c>,
/// <c>src/rust/piper-core/tests/test_speaker_encoder_e2e.rs</c>, and
/// <c>src/go/piperplus/speaker_encoder_e2e_test.go</c>.
///
/// See <c>docs/spec/speaker-encoder-contract.md</c>.
///
/// This test is opt-in: it skips by default unless both
/// <list type="number">
///   <item>The fixture has an <c>e2e_cosine_gate</c> block, AND</item>
///   <item><c>PIPER_SPEAKER_ENCODER_ONNX_PATH</c> points at a local encoder ONNX.</item>
/// </list>
/// </summary>
public class SpeakerEncoderE2ETests
{
    private sealed record E2EEncoderRef(
        [property: JsonPropertyName("hf_repo")] string HfRepo,
        [property: JsonPropertyName("hf_filename")] string HfFilename,
        [property: JsonPropertyName("hf_revision")] string HfRevision,
        [property: JsonPropertyName("sha256")] string? Sha256
    );

    private sealed record E2EReferenceWav(
        [property: JsonPropertyName("path")] string Path,
        [property: JsonPropertyName("sha256")] string? Sha256
    );

    private sealed record E2EExpectedEmbedding(
        [property: JsonPropertyName("dim")] int Dim,
        [property: JsonPropertyName("values")] float[] Values,
        [property: JsonPropertyName("checksum")] string? Checksum
    );

    private sealed record E2EGate(
        [property: JsonPropertyName("version")] int Version,
        [property: JsonPropertyName("encoder_onnx")] E2EEncoderRef EncoderOnnx,
        [property: JsonPropertyName("reference_wav")] E2EReferenceWav ReferenceWav,
        [property: JsonPropertyName("expected_embedding")] E2EExpectedEmbedding ExpectedEmbedding,
        [property: JsonPropertyName("cosine_threshold")] float CosineThreshold
    );

    private sealed record E2EFixture(
        [property: JsonPropertyName("e2e_cosine_gate")] E2EGate? E2ECosineGate
    );

    private static string RepoRoot()
    {
        // bin/Debug/net10.0/ -> 4 levels up to PiperPlus.Core.Tests/, then 4 more to repo root
        string here = AppContext.BaseDirectory;
        DirectoryInfo? d = new(here);
        for (int i = 0; i < 8 && d is not null; i++)
        {
            if (Directory.Exists(System.IO.Path.Combine(d.FullName, "test", "fixtures")))
            {
                return d.FullName;
            }
            d = d.Parent;
        }
        // Fallback: use a path relative to the test source file (Roslyn-resolved at build).
        throw new DirectoryNotFoundException(
            "Could not locate repo root from " + here);
    }

    private static string FixturePath() =>
        System.IO.Path.Combine(RepoRoot(), "test", "fixtures", "speaker_encoder_golden.json");

    private static string Sha256File(string path)
    {
        using var sha = SHA256.Create();
        using var stream = File.OpenRead(path);
        byte[] hash = sha.ComputeHash(stream);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static float Cosine(float[] a, float[] b)
    {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < a.Length; i++)
        {
            dot += (double)a[i] * b[i];
            na += (double)a[i] * a[i];
            nb += (double)b[i] * b[i];
        }
        if (na == 0 || nb == 0) return 0f;
        return (float)(dot / (Math.Sqrt(na) * Math.Sqrt(nb)));
    }

    [Fact]
    public void E2ECosineGate_AgainstPinnedEmbedding()
    {
        string fixturePath;
        try
        {
            fixturePath = FixturePath();
        }
        catch (DirectoryNotFoundException)
        {
            Assert.Skip("repo root not locatable from test bin dir");
            return;
        }

        if (!File.Exists(fixturePath))
        {
            Assert.Skip($"fixture not found: {fixturePath}");
            return;
        }

        string raw = File.ReadAllText(fixturePath);
#pragma warning disable IL2026 // RequiresUnreferencedCode -- E2EFixture POCO members are declared inline and trim-safe in test assembly
        E2EFixture? fixture = System.Text.Json.JsonSerializer.Deserialize<E2EFixture>(raw);
#pragma warning restore IL2026
        if (fixture?.E2ECosineGate is null)
        {
            Assert.Skip("fixture has no e2e_cosine_gate block — generator was run " +
                        "without --encoder-onnx; layer-1 mel parity tests still apply");
            return;
        }
        E2EGate gate = fixture.E2ECosineGate;

        string? encoderPath = Environment.GetEnvironmentVariable("PIPER_SPEAKER_ENCODER_ONNX_PATH");
        if (string.IsNullOrEmpty(encoderPath))
        {
            Assert.Skip("PIPER_SPEAKER_ENCODER_ONNX_PATH not set — opt-in test, " +
                        "skipping by default");
            return;
        }
        if (!File.Exists(encoderPath))
        {
            throw new FileNotFoundException(
                $"PIPER_SPEAKER_ENCODER_ONNX_PATH={encoderPath} does not exist");
        }

        if (!string.IsNullOrEmpty(gate.EncoderOnnx.Sha256))
        {
            string actualSha = Sha256File(encoderPath);
            Assert.True(
                actualSha.Equals(gate.EncoderOnnx.Sha256, StringComparison.OrdinalIgnoreCase),
                $"encoder ONNX sha256 mismatch (silent upstream replacement?):\n" +
                $"  expected: {gate.EncoderOnnx.Sha256}\n  actual:   {actualSha}\n" +
                $"  path:     {encoderPath}");
        }

        string wavPath = gate.ReferenceWav.Path;
        if (!System.IO.Path.IsPathRooted(wavPath))
        {
            wavPath = System.IO.Path.Combine(RepoRoot(), wavPath);
        }
        if (!File.Exists(wavPath))
        {
            Assert.Skip($"reference WAV not found at {wavPath}");
            return;
        }

        using var encoder = new SpeakerEncoder(encoderPath);
        float[] actual = encoder.EncodeFile(wavPath);

        Assert.Equal(gate.ExpectedEmbedding.Values.Length, actual.Length);

        float cos = Cosine(actual, gate.ExpectedEmbedding.Values);
        Assert.True(
            cos >= gate.CosineThreshold,
            $"cosine gate failed: cos={cos:F6} < threshold={gate.CosineThreshold:F6}\n" +
            $"  encoder: {encoderPath}\n  WAV:     {wavPath}");
    }
}
