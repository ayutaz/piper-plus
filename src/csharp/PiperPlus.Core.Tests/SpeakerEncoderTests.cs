using System;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Cross-runtime golden tests for Speaker Encoder mel spectrogram computation.
/// Reads test/fixtures/speaker_encoder_golden.json and verifies that the C#
/// implementation matches the reference output (Python manual DFT) for
/// deterministic inputs (sine waves).
/// </summary>
public class SpeakerEncoderTests
{
    // Mel parameters — must match all runtimes
    private const int SR = 16000;
    private const int NFFT = 512;
    private const int HopLength = 160;
    private const int NMels = 80;
    private const float Fmin = 20f;
    private const float Fmax = 7600f;

    // ------------------------------------------------------------------
    // Internal reimplementation for unit testing (mirrors SpeakerEncoder
    // private methods; identical algorithm)
    // ------------------------------------------------------------------

    private static float HzToMel(float hz) => 2595f * MathF.Log10(1f + hz / 700f);
    private static float MelToHz(float mel) => 700f * (MathF.Pow(10f, mel / 2595f) - 1f);

    private static float[] HannWindow(int length)
    {
        float[] w = new float[length];
        for (int n = 0; n < length; n++)
            w[n] = 0.5f * (1f - MathF.Cos(2f * MathF.PI * n / length));
        return w;
    }

    private static float[] CreateMelFilterbank()
    {
        int fftBins = NFFT / 2 + 1;
        float[] filterbank = new float[NMels * fftBins];

        float melFmin = HzToMel(Fmin);
        float melFmax = HzToMel(Fmax);

        float[] melPoints = new float[NMels + 2];
        for (int i = 0; i < melPoints.Length; i++)
            melPoints[i] = melFmin + (melFmax - melFmin) * i / (NMels + 1);

        float[] binPoints = new float[melPoints.Length];
        for (int i = 0; i < melPoints.Length; i++)
            binPoints[i] = MelToHz(melPoints[i]) * NFFT / SR;

        for (int m = 0; m < NMels; m++)
        {
            int left = (int)MathF.Floor(binPoints[m]);
            int center = (int)MathF.Floor(binPoints[m + 1]);
            int right = (int)MathF.Floor(binPoints[m + 2]);

            if (left == center && center == right)
            {
                center = Math.Min(center + 1, fftBins - 1);
                right = Math.Min(right + 2, fftBins - 1);
            }
            else if (left == center)
            {
                center = Math.Min(center + 1, fftBins - 1);
            }
            if (center == right)
            {
                right = Math.Min(right + 1, fftBins - 1);
            }

            for (int k = left; k < center; k++)
            {
                if (center > left)
                    filterbank[m * fftBins + k] = (float)(k - left) / (center - left);
            }
            for (int k = center; k < right; k++)
            {
                if (right > center)
                    filterbank[m * fftBins + k] = (float)(right - k) / (right - center);
            }
            if (center < fftBins)
                filterbank[m * fftBins + center] = MathF.Max(filterbank[m * fftBins + center], 1.0f);
        }

        return filterbank;
    }

    private static float[] ComputeMelSpectrogram(float[] samples)
    {
        float[] melFilters = CreateMelFilterbank();
        float[] window = HannWindow(NFFT);

        int nFrames = samples.Length >= NFFT
            ? (samples.Length - NFFT) / HopLength + 1
            : 0;

        int fftBins = NFFT / 2 + 1;
        float[] melSpec = new float[NMels * nFrames];

        for (int frameIdx = 0; frameIdx < nFrames; frameIdx++)
        {
            int start = frameIdx * HopLength;

            float[] powerSpec = new float[fftBins];
            for (int k = 0; k < fftBins; k++)
            {
                float real = 0, imag = 0;
                float freq = -2f * MathF.PI * k / NFFT;
                for (int n = 0; n < NFFT; n++)
                {
                    float sample = (start + n < samples.Length)
                        ? samples[start + n] * window[n]
                        : 0f;
                    float angle = freq * n;
                    real += sample * MathF.Cos(angle);
                    imag += sample * MathF.Sin(angle);
                }
                powerSpec[k] = real * real + imag * imag;
            }

            for (int melIdx = 0; melIdx < NMels; melIdx++)
            {
                float energy = 0;
                for (int k = 0; k < fftBins; k++)
                    energy += melFilters[melIdx * fftBins + k] * powerSpec[k];

                melSpec[melIdx * nFrames + frameIdx] = MathF.Log(MathF.Max(energy, 1e-10f));
            }
        }

        return melSpec;
    }

    private static float[] ResampleLinear(float[] samples, int fromRate, int toRate)
    {
        double ratio = (double)fromRate / toRate;
        int outputLen = (int)Math.Ceiling(samples.Length / ratio);
        float[] output = new float[outputLen];

        for (int i = 0; i < outputLen; i++)
        {
            double srcPos = i * ratio;
            int idx = (int)srcPos;
            float frac = (float)(srcPos - idx);

            if (idx + 1 < samples.Length)
                output[i] = samples[idx] * (1f - frac) + samples[idx + 1] * frac;
            else if (idx < samples.Length)
                output[i] = samples[idx];
        }

        return output;
    }

    // ------------------------------------------------------------------
    // Signal generators
    // ------------------------------------------------------------------

    private static float[] GenerateSine(float freqHz, float durationS, int sr)
    {
        int n = (int)(durationS * sr);
        float[] samples = new float[n];
        for (int i = 0; i < n; i++)
            samples[i] = MathF.Sin(2f * MathF.PI * freqHz * i / sr);
        return samples;
    }

    private static float[] GenerateMultitone(float[] freqs, float durationS, int sr)
    {
        int n = (int)(durationS * sr);
        float[] samples = new float[n];
        foreach (float f in freqs)
        {
            for (int i = 0; i < n; i++)
                samples[i] += MathF.Sin(2f * MathF.PI * f * i / sr);
        }
        float peak = samples.Max(MathF.Abs);
        if (peak > 0f)
        {
            for (int i = 0; i < n; i++)
                samples[i] /= peak;
        }
        return samples;
    }

    // ------------------------------------------------------------------
    // Golden file loading
    // ------------------------------------------------------------------

    private static string FindGoldenPath()
    {
        // Walk up from the test binary directory to find the project root
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        for (int i = 0; i < 10; i++)
        {
            string candidate = Path.Combine(dir, "test", "fixtures", "speaker_encoder_golden.json");
            if (File.Exists(candidate)) return candidate;
            dir = Path.GetDirectoryName(dir) ?? dir;
        }

        // Also try relative to the solution location
        string? solutionDir = Directory.GetCurrentDirectory();
        for (int i = 0; i < 10; i++)
        {
            string candidate = Path.Combine(solutionDir, "test", "fixtures", "speaker_encoder_golden.json");
            if (File.Exists(candidate)) return candidate;
            solutionDir = Path.GetDirectoryName(solutionDir) ?? solutionDir;
        }

        throw new FileNotFoundException("Cannot find test/fixtures/speaker_encoder_golden.json");
    }

    private static JsonElement LoadGolden()
    {
        string path = FindGoldenPath();
        string json = File.ReadAllText(path);
        return JsonDocument.Parse(json).RootElement;
    }

    private static JsonElement FindTestCase(JsonElement golden, string id)
    {
        foreach (JsonElement tc in golden.GetProperty("test_cases").EnumerateArray())
        {
            if (tc.GetProperty("id").GetString() == id) return tc;
        }
        throw new KeyNotFoundException($"Test case '{id}' not found in golden data");
    }

    private static double RelativeL2(float[] actual, double[] expected)
    {
        if (actual.Length != expected.Length)
            throw new ArgumentException($"Length mismatch: {actual.Length} vs {expected.Length}");

        double diffSq = 0, refSq = 0;
        for (int i = 0; i < actual.Length; i++)
        {
            double d = actual[i] - expected[i];
            diffSq += d * d;
            refSq += expected[i] * expected[i];
        }
        return refSq < 1e-20 ? Math.Sqrt(diffSq) : Math.Sqrt(diffSq / refSq);
    }

    // ------------------------------------------------------------------
    // Tests: Parameter validation
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenMelParams_Match()
    {
        JsonElement g = LoadGolden();
        JsonElement p = g.GetProperty("mel_params");

        Assert.Equal(SR, p.GetProperty("sr").GetInt32());
        Assert.Equal(NFFT, p.GetProperty("n_fft").GetInt32());
        Assert.Equal(HopLength, p.GetProperty("hop_length").GetInt32());
        Assert.Equal(NMels, p.GetProperty("n_mels").GetInt32());
        Assert.Equal(Fmin, (float)p.GetProperty("fmin").GetDouble(), 0.01f);
        Assert.Equal(Fmax, (float)p.GetProperty("fmax").GetDouble(), 0.01f);
    }

    // ------------------------------------------------------------------
    // Tests: Hann window
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenHannWindow_First5()
    {
        JsonElement g = LoadGolden();
        JsonElement hw = g.GetProperty("hann_window");
        int length = hw.GetProperty("length").GetInt32();

        float[] window = HannWindow(length);
        double[] expected = hw.GetProperty("first_5").EnumerateArray()
            .Select(e => e.GetDouble()).ToArray();

        for (int i = 0; i < expected.Length; i++)
            Assert.True(Math.Abs(window[i] - expected[i]) < 1e-5,
                $"hann_window[{i}]: expected {expected[i]}, got {window[i]}");
    }

    [Fact]
    public void GoldenHannWindow_Last5()
    {
        JsonElement g = LoadGolden();
        JsonElement hw = g.GetProperty("hann_window");
        int length = hw.GetProperty("length").GetInt32();

        float[] window = HannWindow(length);
        double[] expected = hw.GetProperty("last_5").EnumerateArray()
            .Select(e => e.GetDouble()).ToArray();

        for (int i = 0; i < expected.Length; i++)
        {
            int idx = length - 5 + i;
            Assert.True(Math.Abs(window[idx] - expected[i]) < 1e-5,
                $"hann_window[{idx}]: expected {expected[i]}, got {window[idx]}");
        }
    }

    [Fact]
    public void GoldenHannWindow_MidValue()
    {
        JsonElement g = LoadGolden();
        JsonElement hw = g.GetProperty("hann_window");
        int length = hw.GetProperty("length").GetInt32();
        double expectedMid = hw.GetProperty("mid_value").GetDouble();

        float[] window = HannWindow(length);
        Assert.True(Math.Abs(window[length / 2] - expectedMid) < 1e-5,
            $"hann_window mid: expected {expectedMid}, got {window[length / 2]}");
    }

    // ------------------------------------------------------------------
    // Tests: Mel filterbank
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenFilterbank_Shape()
    {
        JsonElement g = LoadGolden();
        int fftBins = NFFT / 2 + 1;
        int[] expectedShape = g.GetProperty("mel_filterbank").GetProperty("shape")
            .EnumerateArray().Select(e => e.GetInt32()).ToArray();

        float[] fb = CreateMelFilterbank();

        Assert.Equal(NMels, expectedShape[0]);
        Assert.Equal(fftBins, expectedShape[1]);
        Assert.Equal(NMels * fftBins, fb.Length);
    }

    [Fact]
    public void GoldenFilterbank_BandSums()
    {
        JsonElement g = LoadGolden();
        double[] expectedSums = g.GetProperty("mel_filterbank").GetProperty("band_sums")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();

        float[] fb = CreateMelFilterbank();
        int fftBins = NFFT / 2 + 1;

        for (int m = 0; m < NMels; m++)
        {
            float bandSum = 0;
            for (int k = 0; k < fftBins; k++)
                bandSum += fb[m * fftBins + k];

            double relErr = Math.Abs(expectedSums[m]) > 1e-10
                ? Math.Abs((bandSum - expectedSums[m]) / expectedSums[m])
                : Math.Abs(bandSum - expectedSums[m]);

            Assert.True(relErr < 0.02,
                $"filterbank band[{m}] sum: expected {expectedSums[m]}, got {bandSum} (rel err {relErr:F6})");
        }
    }

    [Fact]
    public void GoldenFilterbank_TotalSum()
    {
        JsonElement g = LoadGolden();
        double expectedTotal = g.GetProperty("mel_filterbank").GetProperty("total_sum").GetDouble();

        float[] fb = CreateMelFilterbank();
        double total = fb.Sum(x => (double)x);

        double relErr = Math.Abs((total - expectedTotal) / expectedTotal);
        Assert.True(relErr < 0.02,
            $"filterbank total: expected {expectedTotal}, got {total} (rel err {relErr:F6})");
    }

    // ------------------------------------------------------------------
    // Tests: Mel spectrogram — 440Hz sine
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenSine440Hz_MelShape()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "sine_440hz_1s");

        float[] audio = GenerateSine(440f, 1f, SR);
        Assert.Equal(tc.GetProperty("audio_samples_count").GetInt32(), audio.Length);

        float[] mel = ComputeMelSpectrogram(audio);
        int nFrames = mel.Length / NMels;

        int[] expectedShape = tc.GetProperty("expected_mel_shape")
            .EnumerateArray().Select(e => e.GetInt32()).ToArray();
        Assert.Equal(NMels, expectedShape[0]);
        Assert.Equal(nFrames, expectedShape[1]);
    }

    [Fact]
    public void GoldenSine440Hz_MelCorners()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "sine_440hz_1s");
        JsonElement corners = tc.GetProperty("mel_corner_values");

        float[] audio = GenerateSine(440f, 1f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        int nFrames = mel.Length / NMels;

        AssertCornerValue("top_left", mel[0], corners.GetProperty("top_left").GetDouble());
        AssertCornerValue("top_right", mel[nFrames - 1], corners.GetProperty("top_right").GetDouble());
        AssertCornerValue("bottom_left", mel[(NMels - 1) * nFrames], corners.GetProperty("bottom_left").GetDouble());
        AssertCornerValue("bottom_right", mel[NMels * nFrames - 1], corners.GetProperty("bottom_right").GetDouble());
    }

    [Fact]
    public void GoldenSine440Hz_MelSampled()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "sine_440hz_1s");

        float[] audio = GenerateSine(440f, 1f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        float[] sampled = mel.Where((_, i) => i % 10 == 0).ToArray();

        double[] expected = tc.GetProperty("mel_sampled_every_10")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();

        double l2 = RelativeL2(sampled, expected);
        Assert.True(l2 < 0.02, $"sine_440hz sampled L2 distance {l2:F6} exceeds 2% tolerance");
    }

    // ------------------------------------------------------------------
    // Tests: Mel spectrogram — 1000Hz sine
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenSine1000Hz_MelCorners()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "sine_1000hz_0.5s");
        JsonElement corners = tc.GetProperty("mel_corner_values");

        float[] audio = GenerateSine(1000f, 0.5f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        int nFrames = mel.Length / NMels;

        AssertCornerValue("top_left", mel[0], corners.GetProperty("top_left").GetDouble());
        AssertCornerValue("top_right", mel[nFrames - 1], corners.GetProperty("top_right").GetDouble());
        AssertCornerValue("bottom_left", mel[(NMels - 1) * nFrames], corners.GetProperty("bottom_left").GetDouble());
        AssertCornerValue("bottom_right", mel[NMels * nFrames - 1], corners.GetProperty("bottom_right").GetDouble());
    }

    [Fact]
    public void GoldenSine1000Hz_MelSampled()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "sine_1000hz_0.5s");

        float[] audio = GenerateSine(1000f, 0.5f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        float[] sampled = mel.Where((_, i) => i % 10 == 0).ToArray();

        double[] expected = tc.GetProperty("mel_sampled_every_10")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();

        double l2 = RelativeL2(sampled, expected);
        Assert.True(l2 < 0.02, $"sine_1000hz sampled L2 distance {l2:F6} exceeds 2% tolerance");
    }

    // ------------------------------------------------------------------
    // Tests: Mel spectrogram — multitone
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenMultitone_MelCorners()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "multitone_200_600_2000hz_0.5s");
        JsonElement corners = tc.GetProperty("mel_corner_values");

        float[] audio = GenerateMultitone([200f, 600f, 2000f], 0.5f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        int nFrames = mel.Length / NMels;

        AssertCornerValue("top_left", mel[0], corners.GetProperty("top_left").GetDouble());
        AssertCornerValue("top_right", mel[nFrames - 1], corners.GetProperty("top_right").GetDouble());
        AssertCornerValue("bottom_left", mel[(NMels - 1) * nFrames], corners.GetProperty("bottom_left").GetDouble());
        AssertCornerValue("bottom_right", mel[NMels * nFrames - 1], corners.GetProperty("bottom_right").GetDouble());
    }

    [Fact]
    public void GoldenMultitone_MelSampled()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "multitone_200_600_2000hz_0.5s");

        float[] audio = GenerateMultitone([200f, 600f, 2000f], 0.5f, SR);
        float[] mel = ComputeMelSpectrogram(audio);
        float[] sampled = mel.Where((_, i) => i % 10 == 0).ToArray();

        double[] expected = tc.GetProperty("mel_sampled_every_10")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();

        double l2 = RelativeL2(sampled, expected);
        Assert.True(l2 < 0.02, $"multitone sampled L2 distance {l2:F6} exceeds 2% tolerance");
    }

    // ------------------------------------------------------------------
    // Tests: Resampling
    // ------------------------------------------------------------------

    [Fact]
    public void GoldenResample_48kTo16k_OutputLength()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "resample_48k_to_16k");

        float[] audio48k = GenerateSine(440f, 0.1f, 48000);
        Assert.Equal(tc.GetProperty("input_samples_count").GetInt32(), audio48k.Length);

        float[] resampled = ResampleLinear(audio48k, 48000, SR);
        Assert.Equal(tc.GetProperty("expected_output_count").GetInt32(), resampled.Length);
    }

    [Fact]
    public void GoldenResample_48kTo16k_Values()
    {
        JsonElement g = LoadGolden();
        JsonElement tc = FindTestCase(g, "resample_48k_to_16k");

        float[] audio48k = GenerateSine(440f, 0.1f, 48000);
        float[] resampled = ResampleLinear(audio48k, 48000, SR);

        double[] expectedFirst = tc.GetProperty("output_first_10")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();
        for (int i = 0; i < expectedFirst.Length; i++)
            Assert.True(Math.Abs(resampled[i] - expectedFirst[i]) < 1e-4,
                $"resample first[{i}]: expected {expectedFirst[i]}, got {resampled[i]}");

        double[] expectedLast = tc.GetProperty("output_last_10")
            .EnumerateArray().Select(e => e.GetDouble()).ToArray();
        int n = resampled.Length;
        for (int i = 0; i < expectedLast.Length; i++)
        {
            int idx = n - 10 + i;
            Assert.True(Math.Abs(resampled[idx] - expectedLast[i]) < 1e-4,
                $"resample last[{i}]: expected {expectedLast[i]}, got {resampled[idx]}");
        }
    }

    // ------------------------------------------------------------------
    // Tests: Edge cases
    // ------------------------------------------------------------------

    [Fact]
    public void SilentAudio_ProducesFiniteMel()
    {
        float[] silence = new float[16000];
        float[] mel = ComputeMelSpectrogram(silence);
        Assert.True(mel.Length > 0);
        Assert.All(mel, v => Assert.True(float.IsFinite(v), $"Non-finite mel value: {v}"));
    }

    [Fact]
    public void ShortAudio_ProducesEmptyMel()
    {
        float[] shortAudio = new float[100];
        float[] mel = ComputeMelSpectrogram(shortAudio);
        Assert.Empty(mel);
    }

    [Fact]
    public void ResampleSameRate_ReturnsSameArray()
    {
        float[] samples = [1f, 2f, 3f, 4f];
        float[] result = ResampleLinear(samples, 16000, 16000);
        Assert.Equal(samples, result);
    }

    [Fact]
    public void HannWindow_Endpoints_NearZero()
    {
        float[] w = HannWindow(512);
        Assert.Equal(512, w.Length);
        Assert.True(MathF.Abs(w[0]) < 1e-6, $"First window value should be near zero: {w[0]}");
    }

    [Fact]
    public void HzToMel_Roundtrip()
    {
        float hz = 1000f;
        float mel = HzToMel(hz);
        float hzBack = MelToHz(mel);
        Assert.True(MathF.Abs(hz - hzBack) < 0.01f,
            $"Hz roundtrip: {hz} -> {mel} -> {hzBack}");
    }

    [Fact]
    public void FilterbankShape_Correct()
    {
        float[] fb = CreateMelFilterbank();
        int fftBins = NFFT / 2 + 1;
        Assert.Equal(NMels * fftBins, fb.Length);
    }

    [Fact]
    public void FilterbankBands_AllNonZero()
    {
        float[] fb = CreateMelFilterbank();
        int fftBins = NFFT / 2 + 1;
        for (int m = 0; m < NMels; m++)
        {
            float bandSum = 0;
            for (int k = 0; k < fftBins; k++)
                bandSum += fb[m * fftBins + k];
            Assert.True(bandSum > 0, $"Mel band {m} has zero total weight");
        }
    }

    // ------------------------------------------------------------------
    // Helper
    // ------------------------------------------------------------------

    private static void AssertCornerValue(string name, float actual, double expected)
    {
        double relErr = Math.Abs(expected) > 1e-10
            ? Math.Abs((actual - expected) / expected)
            : Math.Abs(actual - expected);
        Assert.True(relErr < 0.02,
            $"{name}: expected {expected}, got {actual} (rel err {relErr:F6})");
    }
}
