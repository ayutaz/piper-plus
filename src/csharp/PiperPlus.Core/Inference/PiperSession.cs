using System;
using Microsoft.ML.OnnxRuntime;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Input parameters for a single TTS synthesis call.
/// Mirrors the VITS inference signature used by the C++ and Python runtimes.
/// </summary>
/// <param name="PhonemeIds">Phoneme ID sequence produced by the phonemizer.</param>
/// <param name="SpeakerId">Speaker index for multi-speaker models (ignored when the model has no <c>sid</c> input).</param>
/// <param name="ProsodyFeatures">
/// Flat array of A1/A2/A3 values, length = <c>PhonemeIds.Length * 3</c>.
/// Layout: <c>[a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...]</c>.
/// Pass <c>null</c> to use zeros (the model default).
/// </param>
/// <param name="NoiseScale">Noise scale for the stochastic duration predictor (higher = more variation).</param>
/// <param name="LengthScale">Length / speed scale (higher = slower speech).</param>
/// <param name="NoiseW">Noise scale W for the stochastic duration predictor.</param>
public record SynthesisInput(
    long[] PhonemeIds,
    int SpeakerId = 0,
    long[]? ProsodyFeatures = null,
    float NoiseScale = 0.667f,
    float LengthScale = 1.0f,
    float NoiseW = 0.8f
);

/// <summary>
/// Runs ONNX inference against a loaded <see cref="PiperModel"/> and converts
/// the float32 audio output to int16 PCM samples.
/// </summary>
/// <remarks>
/// <para>
/// This class does <b>not</b> own the <see cref="PiperModel"/> and therefore does not
/// implement <see cref="IDisposable"/>. The caller (or the model itself) is responsible
/// for disposing the underlying <see cref="InferenceSession"/>.
/// </para>
/// <para>
/// The inference flow mirrors the C++ implementation in <c>piper.cpp:synthesize</c> and
/// the Python implementation in <c>infer_onnx.py</c>:
/// <list type="number">
///   <item>Build input tensors (<c>input</c>, <c>input_lengths</c>, <c>scales</c>,
///         optional <c>sid</c>, optional <c>prosody_features</c>).</item>
///   <item>Run <c>session.Run()</c>.</item>
///   <item>Squeeze the output float32 audio from shape <c>[1, 1, samples]</c>.</item>
///   <item>Peak-normalize and convert to int16 PCM.</item>
/// </list>
/// </para>
/// </remarks>
public sealed class PiperSession
{
    private readonly PiperModel _model;

    /// <summary>
    /// Initializes a new <see cref="PiperSession"/> bound to the given model.
    /// </summary>
    /// <param name="model">
    /// A loaded <see cref="PiperModel"/>. Must remain alive (undisposed) for
    /// the lifetime of this session.
    /// </param>
    public PiperSession(PiperModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        _model = model;
    }

    /// <summary>
    /// Seconds of silence (zero samples) appended after the synthesized audio.
    /// Mirrors <c>SynthesisConfig.sentenceSilenceSeconds</c> in the C++ implementation.
    /// Set to <c>0</c> to disable.
    /// </summary>
    public float SentenceSilenceSeconds { get; set; } = 0.2f;

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    /// <summary>
    /// Synthesize audio from phoneme IDs and return peak-normalized 16-bit PCM samples.
    /// </summary>
    /// <param name="input">Synthesis parameters including phoneme IDs and optional speaker/prosody data.</param>
    /// <returns>Mono int16 PCM audio at the model's sample rate.</returns>
    public short[] Synthesize(SynthesisInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        float[] raw = SynthesizeToFloat(input);
        short[] pcm = ConvertToInt16(raw);

        if (SentenceSilenceSeconds > 0)
        {
            int silenceSamples = (int)(_model.SampleRate * SentenceSilenceSeconds);
            var result = new short[pcm.Length + silenceSamples];
            pcm.CopyTo(result.AsSpan());
            // Remaining elements are already zero-initialized.
            return result;
        }

        return pcm;
    }

    /// <summary>
    /// Synthesize audio from phoneme IDs and return raw float32 samples
    /// before peak normalization. Useful when the caller wants to apply
    /// custom post-processing (denoising, gain, concatenation, etc.).
    /// </summary>
    /// <param name="input">Synthesis parameters including phoneme IDs and optional speaker/prosody data.</param>
    /// <returns>Raw float32 audio as produced by the ONNX model.</returns>
    public float[] SynthesizeToFloat(SynthesisInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        long[] phonemeIds = input.PhonemeIds;
        int phonemeLength = phonemeIds.Length;

        // ----- Build input tensors -----
        // All OrtValues pin managed arrays; dispose them after Run().

        // input: [1, phoneme_length]
        using var inputTensor = OrtValue.CreateTensorValueFromMemory(
            phonemeIds, new long[] { 1, phonemeLength });

        // input_lengths: [1]
        long[] lengths = new long[] { phonemeLength };
        using var inputLengths = OrtValue.CreateTensorValueFromMemory(
            lengths, new long[] { 1 });

        // scales: [3] -- noise_scale, length_scale, noise_w
        float[] scales = new float[] { input.NoiseScale, input.LengthScale, input.NoiseW };
        using var scalesTensor = OrtValue.CreateTensorValueFromMemory(
            scales, new long[] { 3 });

        // Collect names and values in order.
        var inputNames = new List<string>(5) { "input", "input_lengths", "scales" };
        var inputValues = new List<OrtValue>(5) { inputTensor, inputLengths, scalesTensor };

        // sid (optional): [1]
        OrtValue? sidTensor = null;
        if (_model.HasSpeakerId)
        {
            long[] sidArray = new long[] { input.SpeakerId };
            sidTensor = OrtValue.CreateTensorValueFromMemory(sidArray, new long[] { 1 });
            inputNames.Add("sid");
            inputValues.Add(sidTensor);
        }

        // prosody_features (optional): [1, phoneme_length, 3]
        OrtValue? prosodyTensor = null;
        if (_model.HasProsody)
        {
            long[] prosodyArray;
            if (input.ProsodyFeatures is not null
                && input.ProsodyFeatures.Length == phonemeLength * 3)
            {
                prosodyArray = input.ProsodyFeatures;
            }
            else
            {
                // Use zeros when no prosody data is provided (matches C++ behaviour).
                prosodyArray = new long[phonemeLength * 3];
            }

            prosodyTensor = OrtValue.CreateTensorValueFromMemory(
                prosodyArray, new long[] { 1, phonemeLength, 3 });
            inputNames.Add("prosody_features");
            inputValues.Add(prosodyTensor);
        }

        try
        {
            // ----- Run inference -----
            string[] outputNames = new string[] { "output" };

            using var results = _model.Session.Run(
                new RunOptions(),
                inputNames,
                inputValues,
                outputNames);

            // Output shape: [1, 1, audio_samples] -- squeeze to 1-D.
            ReadOnlySpan<float> outputSpan = results[0].GetTensorDataAsSpan<float>();
            return outputSpan.ToArray();
        }
        finally
        {
            // Dispose optional tensors that were created outside the using declarations.
            sidTensor?.Dispose();
            prosodyTensor?.Dispose();
        }
    }

    // ------------------------------------------------------------------
    // Static helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Peak-normalize float32 audio and convert to 16-bit signed PCM.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The algorithm finds the absolute peak of the input and scales the entire
    /// signal so that the peak maps to <see cref="short.MaxValue"/> (32767).
    /// A minimum peak of 0.01 is enforced to avoid division-by-zero on near-silent
    /// audio.
    /// </para>
    /// <para>
    /// This matches the C++ implementation in <c>piper.cpp</c> and the Python
    /// <c>audio_float_to_int16</c> in <c>vits/utils.py</c>:
    /// <code>
    /// scale = 32767 / max(0.01, max(|sample|))
    /// sample_i16 = clamp(sample * scale, -32768, 32767)
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="audio">Raw float32 samples from the model.</param>
    /// <returns>Peak-normalized int16 PCM samples.</returns>
    public static short[] ConvertToInt16(ReadOnlySpan<float> audio)
    {
        if (audio.IsEmpty)
        {
            return [];
        }

        // Find absolute peak value.
        float maxVal = 0f;
        for (int i = 0; i < audio.Length; i++)
        {
            float abs = Math.Abs(audio[i]);
            if (abs > maxVal)
            {
                maxVal = abs;
            }
        }

        // Scale so that the peak maps to 32767; clamp minimum peak to avoid
        // amplifying near-silence to full scale.
        float scale = 32767.0f / Math.Max(0.01f, maxVal);

        var result = new short[audio.Length];
        for (int i = 0; i < audio.Length; i++)
        {
            result[i] = (short)Math.Clamp(audio[i] * scale, short.MinValue, short.MaxValue);
        }

        return result;
    }
}
