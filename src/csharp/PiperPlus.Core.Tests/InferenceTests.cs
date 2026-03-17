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
    // SynthesisInput record tests
    // ----------------------------------------------------------------

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
