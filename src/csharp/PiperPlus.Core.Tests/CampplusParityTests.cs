using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// zs-v1 CAM++ embedding parity with the Python recipe, using the real model.
/// </summary>
/// <remarks>
/// <see cref="KaldiFbankTests"/> checks the features; this checks what the runtime
/// feeds the base model: <see cref="SpeakerEncoder"/> on the pinned
/// <c>campplus.onnx</c>, against embeddings that
/// <c>test/generate_zs_campplus_golden.py</c> computed with torchaudio +
/// onnxruntime (the recipe in <c>huggingface-space/zero_shot.py</c>). The browser
/// runs the same fixture in <c>test-zs-campplus-parity.js</c>.
/// Needs the pinned model at <c>PIPER_PLUS_CAMPPLUS_ONNX</c> (CI sets it).
/// </remarks>
public class CampplusParityTests
{
    private const string CampplusSha256 = "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73";

    // Same thresholds as the browser test: measured cosine >= 0.9999999 on these
    // signals. Changing one detail lands below: preemphasis 0.97 -> 0.96 gives
    // 0.99969, resampler rolloff 0.99 gives 0.981, a plain Hann window 0.987.
    private const double MinCosine = 0.9999;
    private const double MaxAbs = 5e-4;

    private readonly ITestOutputHelper _output;

    public CampplusParityTests(ITestOutputHelper output)
    {
        _output = output;
    }

    private static string ModelPath()
    {
        string? path = Environment.GetEnvironmentVariable("PIPER_PLUS_CAMPPLUS_ONNX");
        if (string.IsNullOrEmpty(path))
        {
            Assert.Skip("PIPER_PLUS_CAMPPLUS_ONNX is not set");
        }

        Assert.True(File.Exists(path), $"PIPER_PLUS_CAMPPLUS_ONNX={path} is missing");
        using FileStream stream = File.OpenRead(path);
        Assert.Equal(CampplusSha256, Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant());
        return path;
    }

    // xorshift32 in [-0.5, 0.5), bit-identical to white_noise() in the generator.
    private static double[] WhiteNoise(int n, uint seed)
    {
        double[] output = new double[n];
        uint x = seed;
        for (int i = 0; i < n; i++)
        {
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            output[i] = (x / 4294967296.0) - 0.5;
        }

        return output;
    }

    // Mirrors voiced_signal() in the generator: a harmonic tone with vibrato and
    // a syllable-rate envelope, high partials in the gaps (they exercise the
    // resampler cutoff) and a weak white floor, computed in double and stored as
    // float.
    private static float[] VoicedSignal(JsonElement fx, JsonElement c)
    {
        double rate = c.GetProperty("sample_rate").GetInt32();
        double f0 = c.GetProperty("f0").GetDouble();
        double vibHz = c.GetProperty("vibrato_hz").GetDouble();
        double depth = c.GetProperty("vibrato_depth_hz").GetDouble();
        double syllableHz = fx.GetProperty("syllable_hz").GetDouble();
        double amplitude = fx.GetProperty("amplitude").GetDouble();
        int maxHarmonics = fx.GetProperty("max_harmonics").GetInt32();
        double noiseFloor = fx.GetProperty("noise_floor").GetDouble();
        double[][] partials = fx.GetProperty("noise_partials").EnumerateArray()
            .Select(p => p.EnumerateArray().Select(v => v.GetDouble()).ToArray())
            .ToArray();
        int n = (int)Math.Round(rate * c.GetProperty("seconds").GetDouble());
        double[] floor = WhiteNoise(n, fx.GetProperty("noise_seed").GetUInt32());

        float[] output = new float[n];
        for (int i = 0; i < n; i++)
        {
            double t = i / rate;
            double phase = (2 * Math.PI * f0 * t) - ((depth / vibHz) * Math.Cos(2 * Math.PI * vibHz * t));
            double envelope = 0.5 * (1 - Math.Cos(2 * Math.PI * syllableHz * t));
            double x = 0;
            for (int k = 1; k * (f0 + depth) < rate / 2 && k <= maxHarmonics; k++)
            {
                x += amplitude / k * Math.Sin(k * phase);
            }

            double noise = 0;
            foreach (double[] p in partials.Where(q => q[1] < rate / 2))
            {
                noise += p[0] * Math.Sin(2 * Math.PI * p[1] * t);
            }

            output[i] = (float)((envelope * x) + ((1 - envelope) * noise) + (noiseFloor * floor[i]));
        }

        return output;
    }

    private static double Cosine(float[] a, float[] b)
    {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < a.Length; i++)
        {
            dot += (double)a[i] * b[i];
            na += (double)a[i] * a[i];
            nb += (double)b[i] * b[i];
        }

        return dot / Math.Sqrt(na * nb);
    }

    [Fact]
    public void Embeddings_MatchPythonRecipe()
    {
        string path = ModelPath();
        JsonElement fx = KaldiFbankTests.LoadFixture("zs_campplus_golden.json");
        Assert.Equal(CampplusSha256, fx.GetProperty("campplus_sha256").GetString());

        // The default constructor must pick the zs-v1 front end for CAM++.
        using var encoder = new SpeakerEncoder(path);
        Assert.Equal(SpeakerFrontEnd.KaldiFbank, encoder.FrontEnd);

        var embeddings = new Dictionary<string, float[]>();
        foreach (JsonElement c in fx.GetProperty("cases").EnumerateArray())
        {
            string name = c.GetProperty("name").GetString()!;
            float[] expected = KaldiFbankTests.Floats(c.GetProperty("embedding"));
            float[] embedding = encoder.Encode(VoicedSignal(fx, c), c.GetProperty("sample_rate").GetInt32());
            Assert.Equal(expected.Length, embedding.Length);
            double maxAbs = embedding.Zip(expected, (a, b) => (double)Math.Abs(a - b)).Max();
            double cos = Cosine(embedding, expected);
            _output.WriteLine($"{name}: cosine {cos:F7}, max abs {maxAbs:E2}");
            Assert.True(cos >= MinCosine, $"{name}: cosine {cos} < {MinCosine}");
            Assert.True(maxAbs <= MaxAbs, $"{name}: max abs {maxAbs} > {MaxAbs}");
            embeddings[name] = embedding;
        }

        // Guards against a degenerate encoder that returns the same vector for
        // every voice.
        string[] pair = fx.GetProperty("distinct_pair").EnumerateArray().Select(v => v.GetString()!).ToArray();
        double distinct = Cosine(embeddings[pair[0]], embeddings[pair[1]]);
        Assert.True(distinct < 0.95, $"cosine {distinct} between distinct voices");
    }

    [Fact]
    public void MelFrontEnd_DoesNotMatchPythonRecipe()
    {
        // The legacy front end on the same model drifts well away from the
        // Python embedding; this is what #915 fixed for CAM++.
        string path = ModelPath();
        JsonElement fx = KaldiFbankTests.LoadFixture("zs_campplus_golden.json");
        JsonElement c = fx.GetProperty("cases").EnumerateArray()
            .First(e => e.GetProperty("sample_rate").GetInt32() != 16000);
        using var encoder = new SpeakerEncoder(path, SpeakerFrontEnd.Mel);
        float[] embedding = encoder.Encode(VoicedSignal(fx, c), c.GetProperty("sample_rate").GetInt32());
        double cos = Cosine(embedding, KaldiFbankTests.Floats(c.GetProperty("embedding")));
        _output.WriteLine($"{c.GetProperty("name").GetString()} with the legacy front end: cosine {cos:F4}");
        Assert.True(cos < MinCosine, $"legacy front end unexpectedly matched: cosine {cos}");
    }
}
