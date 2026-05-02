using System;
using System.Buffers;
using Microsoft.ML.OnnxRuntime;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Inference result containing synthesized audio and optional per-phoneme durations.
/// </summary>
/// <param name="Audio">Peak-normalized 16-bit PCM audio samples.</param>
/// <param name="Durations">
/// Per-phoneme durations (in frames) with shape <c>[phoneme_length]</c>, or
/// <c>null</c> when the model does not produce a <c>durations</c> output tensor.
/// </param>
public record SynthesisResult(short[] Audio, float[]? Durations);

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
/// <param name="SpeakerEmbedding">
/// Speaker embedding vector from a speaker encoder model (voice cloning).
/// When provided, this is passed as the <c>speaker_embedding</c> ONNX input
/// together with <c>speaker_embedding_mask=1</c>. Pass <c>null</c> to use
/// the standard <c>sid</c>-based speaker selection.
/// Typical dimension: 256 floats (ECAPA-TDNN output).
/// </param>
public record SynthesisInput(
    long[] PhonemeIds,
    int SpeakerId = 0,
    int LanguageId = 0,
    long[]? ProsodyFeatures = null,
    float NoiseScale = 0.667f,
    float LengthScale = 1.0f,
    float NoiseW = 0.8f,
    float[]? SpeakerEmbedding = null
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

        if (input.PhonemeIds.Length == 0)
            return [];

        return RunInferenceCore(input, includeDurations: false).Audio;
    }

    /// <summary>
    /// Synthesize audio from phoneme IDs and return peak-normalized 16-bit PCM samples
    /// together with optional per-phoneme duration information.
    /// </summary>
    /// <remarks>
    /// When the model exposes a <c>durations</c> output tensor (shape <c>[1, phoneme_length]</c>),
    /// the durations are extracted and returned. Otherwise <see cref="SynthesisResult.Durations"/>
    /// is <c>null</c>. This mirrors the C++ implementation in <c>piper.cpp:synthesize</c>.
    /// </remarks>
    /// <param name="input">Synthesis parameters including phoneme IDs and optional speaker/prosody data.</param>
    /// <returns>A <see cref="SynthesisResult"/> containing PCM audio and optional durations.</returns>
    public SynthesisResult SynthesizeWithDurations(SynthesisInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        if (input.PhonemeIds.Length == 0)
            return new SynthesisResult([], null);

        var (audioFloat, durations) = RunInferenceCore(input, includeDurations: true);
        short[] pcm = ConvertToInt16(audioFloat);

        // Append sentence silence if configured.
        if (SentenceSilenceSeconds > 0)
        {
            int silenceSamples = (int)(_model.SampleRate * SentenceSilenceSeconds);
            var padded = new short[pcm.Length + silenceSamples];
            pcm.CopyTo(padded.AsSpan());
            pcm = padded;
        }

        return new SynthesisResult(pcm, durations);
    }

    // ------------------------------------------------------------------
    // Shared inference helper
    // ------------------------------------------------------------------

    /// <summary>
    /// Build input tensors, run ONNX inference, and return the raw float32 audio
    /// together with optional per-phoneme durations.
    /// <para>
    /// When the phoneme sequence is shorter than <see cref="ShortTextProcessor.MinPhonemeIds"/>,
    /// Strategies A and B are applied automatically:
    /// <list type="bullet">
    ///   <item><b>A</b>: Pad with pause IDs (0) after BOS / before EOS, then
    ///         trim leading/trailing silence from the output.</item>
    ///   <item><b>B</b>: Reduce <c>noiseScale</c> and <c>noiseW</c>
    ///         proportionally to stabilise the duration predictor.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="input">Synthesis parameters.</param>
    /// <param name="includeDurations">
    /// When <c>true</c> and the model exposes a <c>durations</c> output,
    /// the durations tensor is requested and returned.
    /// </param>
    /// <returns>
    /// Raw float32 audio (shape squeezed to 1-D) and optional durations array.
    /// </returns>
    private (float[] Audio, float[]? Durations) RunInferenceCore(
        SynthesisInput input, bool includeDurations)
    {
        long[] phonemeIds = input.PhonemeIds;
        long[]? prosodyFlat = input.ProsodyFeatures;
        float noiseScale = input.NoiseScale;
        float noiseW = input.NoiseW;

        // ----- Strategy A: Silence Padding -----
        bool wasPadded = ShortTextProcessor.NeedsPadding(phonemeIds);
        int frontPad = 0;
        int backPad = 0;
        if (wasPadded)
        {
            (phonemeIds, prosodyFlat, frontPad, backPad) =
                ShortTextProcessor.PadPhonemeIds(phonemeIds, prosodyFlat);
        }

        // ----- Strategy B: Dynamic Scales Adjustment -----
        // Use the *original* length (before padding) for the ratio calculation.
        if (input.PhonemeIds.Length < ShortTextProcessor.MinPhonemeIds)
        {
            (noiseScale, noiseW) = ShortTextProcessor.AdjustScales(
                input.PhonemeIds.Length, noiseScale, noiseW);
        }

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
        float[] scales = new float[] { noiseScale, input.LengthScale, noiseW };
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

        // lid (optional): [1] -- language ID for multilingual models
        OrtValue? lidTensor = null;
        if (_model.HasLanguageId)
        {
            long[] lidArray = new long[] { input.LanguageId };
            lidTensor = OrtValue.CreateTensorValueFromMemory(lidArray, new long[] { 1 });
            inputNames.Add("lid");
            inputValues.Add(lidTensor);
        }

        // prosody_features (optional): [1, phoneme_length, 3]
        // Use ArrayPool for the zero-filled fallback array to avoid per-call allocations
        // when no prosody data is provided. The rented buffer must stay alive through
        // Session.Run() because OrtValue pins the managed array.
        OrtValue? prosodyTensor = null;
        long[]? rentedProsody = null;
        if (_model.HasProsody)
        {
            long[] prosodyArray;
            int prosodySize = phonemeLength * 3;
            if (prosodyFlat is not null
                && prosodyFlat.Length == prosodySize)
            {
                prosodyArray = prosodyFlat;
            }
            else if (prosodySize > 64)
            {
                // Pool the zero-fill buffer for non-trivial sizes.
                rentedProsody = ArrayPool<long>.Shared.Rent(prosodySize);
                Array.Clear(rentedProsody, 0, prosodySize);
                prosodyArray = rentedProsody;
            }
            else
            {
                // Small arrays: plain allocation is cheaper than pool overhead.
                prosodyArray = new long[prosodySize];
            }

            prosodyTensor = OrtValue.CreateTensorValueFromMemory(
                prosodyArray, new long[] { 1, phonemeLength, 3 });
            inputNames.Add("prosody_features");
            inputValues.Add(prosodyTensor);
        }

        // speaker_embedding (optional): [1, embedding_dim]
        // speaker_embedding_mask (optional): [1, 1] — 1 if embedding active, 0 otherwise
        // ONNX Runtime requires ALL declared inputs, so both tensors must always
        // be provided when the model supports speaker_embedding.
        OrtValue? speakerEmbTensor = null;
        OrtValue? speakerEmbMaskTensor = null;
        if (_model.HasSpeakerEmbedding)
        {
            if (input.SpeakerEmbedding is not null && input.SpeakerEmbedding.Length > 0)
            {
                int embDim = input.SpeakerEmbedding.Length;
                speakerEmbTensor = OrtValue.CreateTensorValueFromMemory(
                    input.SpeakerEmbedding, [1, embDim]);
                inputNames.Add("speaker_embedding");
                inputValues.Add(speakerEmbTensor);

                long[] mask = [1];
                speakerEmbMaskTensor = OrtValue.CreateTensorValueFromMemory(mask, [1, 1]);
                inputNames.Add("speaker_embedding_mask");
                inputValues.Add(speakerEmbMaskTensor);
            }
            else
            {
                // Model supports it but no embedding provided — send zeros + mask=0.
                // Read embedding dimension from model input metadata; default 256 (ECAPA-TDNN).
                int embDim = 256;
                var meta = _model.Session.InputMetadata;
                if (meta.TryGetValue("speaker_embedding", out var embMeta)
                    && embMeta.Dimensions.Length >= 2 && embMeta.Dimensions[1] > 0)
                {
                    embDim = embMeta.Dimensions[1];
                }

                float[] zeroEmb = new float[embDim];
                speakerEmbTensor = OrtValue.CreateTensorValueFromMemory(zeroEmb, [1, embDim]);
                inputNames.Add("speaker_embedding");
                inputValues.Add(speakerEmbTensor);

                long[] mask = [0];
                speakerEmbMaskTensor = OrtValue.CreateTensorValueFromMemory(mask, [1, 1]);
                inputNames.Add("speaker_embedding_mask");
                inputValues.Add(speakerEmbMaskTensor);
            }
        }

        try
        {
            // ----- Build output names -----
            bool requestDurations = includeDurations && _model.HasDurationOutput;
            string[] outputNames = requestDurations
                ? ["output", "durations"]
                : ["output"];

            // ----- Run inference -----
            using var runOptions = new RunOptions();
            using var results = _model.Session.Run(
                runOptions,
                inputNames,
                inputValues,
                outputNames);

            // Output shape: [1, 1, audio_samples] -- squeeze to 1-D.
            ReadOnlySpan<float> outputSpan = results[0].GetTensorDataAsSpan<float>();
            float[] audio = outputSpan.ToArray();

            // Extract durations BEFORE post-trim so the precise trimmer can
            // use them. Always copy out the full padded-sequence durations
            // first; the value returned to callers is truncated below to the
            // original phoneme length so timing alignment is preserved.
            float[]? paddedDurations = null;
            if (requestDurations && results.Count >= 2)
            {
                ReadOnlySpan<float> durSpan = results[1].GetTensorDataAsSpan<float>();
                paddedDurations = durSpan.ToArray();
            }

            // ----- Strategy A: Post-inference padding-induced trim -----
            // Prefer durations-based precise trim (issue #356); fall back to
            // legacy RMS trim only when durations are unavailable.
            if (wasPadded)
            {
                if (paddedDurations is not null)
                {
                    audio = ShortTextProcessor.TrimPaddingByDurations(
                        audio, paddedDurations, frontPad, backPad, _model.HopSize);
                }
                else
                {
                    audio = ShortTextProcessor.TrimSilence(audio);
                }
            }

            // Truncate durations back to the original phoneme length for
            // timing consumers (they treat the padded extras as out-of-band).
            float[]? durations = paddedDurations;
            if (durations is not null && wasPadded && durations.Length > input.PhonemeIds.Length)
            {
                var trimmed = new float[input.PhonemeIds.Length];
                Array.Copy(durations, trimmed, input.PhonemeIds.Length);
                durations = trimmed;
            }

            return (audio, durations);
        }
        finally
        {
            // Dispose optional tensors that were created outside the using declarations.
            sidTensor?.Dispose();
            lidTensor?.Dispose();
            prosodyTensor?.Dispose();
            speakerEmbTensor?.Dispose();
            speakerEmbMaskTensor?.Dispose();

            // Return the pooled prosody buffer after the tensor is disposed.
            if (rentedProsody is not null)
                ArrayPool<long>.Shared.Return(rentedProsody);
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
            result[i] = (short)Math.Clamp(audio[i] * scale, -32767f, 32767f);
        }

        return result;
    }
}
