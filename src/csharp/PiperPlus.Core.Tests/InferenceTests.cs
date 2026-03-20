using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Tests for <see cref="PiperSession.ConvertToInt16"/> peak-normalisation logic
/// and <see cref="SynthesisInput"/> default values.
/// </summary>
public class InferenceTests
{
    // ----------------------------------------------------------------
    // ConvertToInt16 tests
    // ----------------------------------------------------------------

    [Fact]
    public void ConvertToInt16_ZeroArray_ReturnsAllZeros()
    {
        // All-zero input: peak is 0.0, which falls below the minimum 0.01,
        // so scale = 32767 / 0.01 = 3276700. 0 * anything = 0.
        float[] audio = [0.0f, 0.0f, 0.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(3, result.Length);
        Assert.All(result, sample => Assert.Equal(0, sample));
    }

    [Fact]
    public void ConvertToInt16_NormalizedArray_ScalesCorrectly()
    {
        // Peak = 1.0, scale = 32767 / 1.0 = 32767.
        // -1.0 * 32767 = -32767, 0 * 32767 = 0, 1.0 * 32767 = 32767.
        float[] audio = [-1.0f, 0.0f, 1.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(3, result.Length);
        Assert.Equal(-32767, result[0]);
        Assert.Equal(0, result[1]);
        Assert.Equal(32767, result[2]);
    }

    [Fact]
    public void ConvertToInt16_SmallValues_NormalizedToFullRange()
    {
        // Peak = 0.001, scale = 32767 / 0.01 = 3276700 (minimum peak 0.01 applies).
        // 0.001 * 3276700 = 3276.7 -> (short)3276 after Clamp truncation.
        // -0.001 * 3276700 = -3276.7 -> (short)-3276.
        float[] audio = [0.001f, -0.001f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(2, result.Length);
        // Math.Clamp returns float, cast to short truncates toward zero.
        Assert.Equal((short)(0.001f * (32767.0f / 0.01f)), result[0]);
        Assert.Equal((short)(-0.001f * (32767.0f / 0.01f)), result[1]);
    }

    [Fact]
    public void ConvertToInt16_LargeValues_ClampedCorrectly()
    {
        // Peak = 100.0, scale = 32767 / 100.0 = 327.67.
        // 100 * 327.67 = 32767, -100 * 327.67 = -32767.
        float[] audio = [100.0f, -100.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(2, result.Length);
        Assert.Equal(32767, result[0]);
        Assert.Equal(-32767, result[1]);
    }

    [Fact]
    public void ConvertToInt16_SingleSample_Works()
    {
        // Peak = 0.5, scale = 32767 / 0.5 = 65534.
        // 0.5 * 65534 = 32767.
        float[] audio = [0.5f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        Assert.Equal(32767, result[0]);
    }

    [Fact]
    public void ConvertToInt16_EmptyArray_ReturnsEmpty()
    {
        float[] audio = [];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Empty(result);
    }

    [Fact]
    public void ConvertToInt16_AsymmetricValues_NormalizesToPeak()
    {
        // Peak = max(|0.1|, |-0.5|) = 0.5, scale = 32767 / 0.5 = 65534.
        // 0.1 * 65534 = 6553.4 -> (short)6553.
        // -0.5 * 65534 = -32767.
        float[] audio = [0.1f, -0.5f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(2, result.Length);
        float scale = 32767.0f / 0.5f;
        Assert.Equal((short)(0.1f * scale), result[0]);
        Assert.Equal(-32767, result[1]);
    }

    [Fact]
    public void ConvertToInt16_VerySmallPeak_UsesMinimumScale()
    {
        // All values are extremely small (1e-8). Peak < 0.01, so
        // minimum peak 0.01 is used. scale = 32767 / 0.01 = 3276700.
        // 1e-8 * 3276700 ~= 0.032767 -> (short)0.
        float[] audio = [1e-8f, -1e-8f, 5e-9f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(3, result.Length);
        // Values are so small that even with the minimum-peak scale they round to 0.
        Assert.All(result, sample => Assert.Equal(0, sample));
    }

    // ----------------------------------------------------------------
    // ConvertToInt16 boundary value tests
    // ----------------------------------------------------------------

    [Fact]
    public void ConvertToInt16_PeakExactlyAtMinimum_0_01()
    {
        // Peak = 0.01, which equals the minimum threshold exactly.
        // scale = 32767 / max(0.01, 0.01) = 32767 / 0.01 = 3276700.
        // 0.01 * 3276700 = 32767.
        float[] audio = [0.01f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        float scale = 32767.0f / 0.01f;
        Assert.Equal((short)Math.Clamp(0.01f * scale, -32767f, 32767f), result[0]);
    }

    [Fact]
    public void ConvertToInt16_PeakJustBelow_Minimum_UsesMinimumPeak()
    {
        // Peak = 0.005 < 0.01, so the minimum peak 0.01 is used.
        // scale = 32767 / 0.01 = 3276700.
        // 0.005 * 3276700 = 16383.5 -> (short)16383.
        float[] audio = [0.005f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        float scale = 32767.0f / 0.01f; // minimum peak applies
        Assert.Equal((short)Math.Clamp(0.005f * scale, -32767f, 32767f), result[0]);
    }

    [Fact]
    public void ConvertToInt16_PeakJustAbove_Minimum_UsesActualPeak()
    {
        // Peak = 0.02 > 0.01, so the actual peak is used.
        // scale = 32767 / 0.02 = 1638350.
        // 0.02 * 1638350 = 32767.
        float[] audio = [0.02f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        float scale = 32767.0f / 0.02f; // actual peak used
        Assert.Equal((short)Math.Clamp(0.02f * scale, -32767f, 32767f), result[0]);
    }

    [Fact]
    public void ConvertToInt16_AllNegativeValues_NormalizesCorrectly()
    {
        // Peak = max(|-0.5|, |-1.0|, |-0.3|) = 1.0.
        // scale = 32767 / 1.0 = 32767.
        float[] audio = [-0.5f, -1.0f, -0.3f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(3, result.Length);
        float scale = 32767.0f / 1.0f;
        Assert.Equal((short)Math.Clamp(-0.5f * scale, -32767f, 32767f), result[0]);
        Assert.Equal((short)Math.Clamp(-1.0f * scale, -32767f, 32767f), result[1]);
        Assert.Equal((short)Math.Clamp(-0.3f * scale, -32767f, 32767f), result[2]);
    }

    [Fact]
    public void ConvertToInt16_MixedTinyAndLarge_PeakDeterminesScale()
    {
        // Peak = max(|0.001|, |1.0|, |0.001|) = 1.0.
        // scale = 32767 / 1.0 = 32767.
        // 0.001 * 32767 = 32.767 -> (short)32.
        // 1.0 * 32767 = 32767.
        float[] audio = [0.001f, 1.0f, 0.001f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(3, result.Length);
        float scale = 32767.0f / 1.0f;
        Assert.Equal((short)(0.001f * scale), result[0]);
        Assert.Equal(32767, result[1]);
        Assert.Equal((short)(0.001f * scale), result[2]);
    }

    [Fact]
    public void ConvertToInt16_SymmetricClipping_Negative32767()
    {
        // Verify the negative clamp is -32767 (not -32768).
        // With peak = 1.0, scale = 32767. -1.0 * 32767 = -32767, which
        // equals the clamp boundary exactly.
        // Use a value slightly beyond -1.0 to force clamping.
        float[] audio = [1.0f, -1.5f];

        short[] result = PiperSession.ConvertToInt16(audio);

        // Peak = 1.5, scale = 32767 / 1.5 = 21844.666...
        // -1.5 * 21844.666 = -32767 (exactly at clamp boundary).
        // Verify clamped to -32767, not -32768.
        Assert.True(result[1] >= -32767,
            $"Expected >= -32767 but got {result[1]}; symmetric clamp must not produce -32768");
    }

    [Fact]
    public void ConvertToInt16_SymmetricClipping_Positive32767()
    {
        // Verify the positive clamp is +32767.
        // Peak = 1.5, scale = 32767 / 1.5 = 21844.666...
        // 1.5 * 21844.666 = 32767 (exactly at clamp boundary).
        float[] audio = [1.5f, -1.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.True(result[0] <= 32767,
            $"Expected <= 32767 but got {result[0]}; positive clamp must be 32767");
        Assert.Equal(32767, result[0]);
    }

    [Fact]
    public void ConvertToInt16_SingleSampleMaxPositive()
    {
        // [1.0f]: peak = 1.0, scale = 32767. 1.0 * 32767 = 32767.
        float[] audio = [1.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        Assert.Equal(32767, result[0]);
    }

    [Fact]
    public void ConvertToInt16_SingleSampleMaxNegative()
    {
        // [-1.0f]: peak = 1.0, scale = 32767. -1.0 * 32767 = -32767.
        float[] audio = [-1.0f];

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Single(result);
        Assert.Equal(-32767, result[0]);
    }

    [Fact]
    public void ConvertToInt16_LargeArray_Performance()
    {
        // 100,000 samples: verify correct output length and no exceptions.
        const int count = 100_000;
        float[] audio = new float[count];
        var rng = new Random(42);
        for (int i = 0; i < count; i++)
        {
            audio[i] = (float)(rng.NextDouble() * 2.0 - 1.0); // range [-1, 1]
        }

        short[] result = PiperSession.ConvertToInt16(audio);

        Assert.Equal(count, result.Length);
        // All values must be within the symmetric int16 range.
        Assert.All(result, s => Assert.InRange(s, (short)-32767, (short)32767));
    }

    // ----------------------------------------------------------------
    // SynthesisInput record tests
    // ----------------------------------------------------------------

    [Fact]
    public void SynthesisInput_WithCustomScales_ValuesPreserved()
    {
        var input = new SynthesisInput(
            PhonemeIds: [10, 20, 30],
            SpeakerId: 5,
            NoiseScale: 0.33f,
            LengthScale: 1.5f,
            NoiseW: 0.4f
        );

        Assert.Equal(0.33f, input.NoiseScale);
        Assert.Equal(1.5f, input.LengthScale);
        Assert.Equal(0.4f, input.NoiseW);
        Assert.Equal(5, input.SpeakerId);
    }

    [Fact]
    public void SynthesisInput_WithProsodyFeatures_Preserved()
    {
        long[] phonemes = [1, 2, 3];
        // 3 phonemes * 3 features = 9 values: [a1_0, a2_0, a3_0, a1_1, ...]
        long[] prosody = [1, 2, 5, -1, 3, 4, 0, 1, 3];

        var input = new SynthesisInput(
            PhonemeIds: phonemes,
            ProsodyFeatures: prosody
        );

        Assert.NotNull(input.ProsodyFeatures);
        Assert.Equal(9, input.ProsodyFeatures.Length);
        Assert.Equal(prosody, input.ProsodyFeatures);
    }

    [Fact]
    public void SynthesisInput_DefaultValues_AreCorrect()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);

        Assert.Equal(0.667f, input.NoiseScale);
        Assert.Equal(1.0f, input.LengthScale);
        Assert.Equal(0.8f, input.NoiseW);
    }

    [Fact]
    public void SynthesisInput_SpeakerId_DefaultsToZero()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);

        Assert.Equal(0, input.SpeakerId);
        Assert.Null(input.ProsodyFeatures);
    }
}
