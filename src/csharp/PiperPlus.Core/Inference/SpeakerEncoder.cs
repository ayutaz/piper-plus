using System;
using System.IO;
using System.Numerics;
using Microsoft.ML.OnnxRuntime;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Speaker encoder for voice cloning — loads an ECAPA-TDNN ONNX model
/// and extracts speaker embedding vectors from reference audio.
/// </summary>
/// <remarks>
/// <para>
/// Mel spectrogram parameters are unified across all runtimes:
/// sr=16000, n_fft=512, hop=160, n_mels=80, fmin=20, fmax=7600.
/// </para>
/// <para>
/// The extracted embedding (typically 256-d float32) can be passed to
/// <see cref="SynthesisInput.SpeakerEmbedding"/> for voice cloning synthesis.
/// </para>
/// </remarks>
public sealed class SpeakerEncoder : IDisposable
{
    private const int MelSampleRate = 16000;
    private const int MelNFft = 512;
    private const int MelHopLength = 160;
    private const int MelNMels = 80;
    private const float MelFmin = 20f;
    private const float MelFmax = 7600f;

    private readonly InferenceSession _session;
    private bool _disposed;

    /// <summary>
    /// Load a speaker encoder model from an ONNX file.
    /// </summary>
    /// <param name="modelPath">Path to the speaker encoder ONNX model.</param>
    public SpeakerEncoder(string modelPath)
    {
        ArgumentException.ThrowIfNullOrEmpty(modelPath);
        if (!File.Exists(modelPath))
            throw new FileNotFoundException($"Speaker encoder model not found: {modelPath}", modelPath);

        var options = new SessionOptions
        {
            GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL,
            IntraOpNumThreads = 2,
            InterOpNumThreads = 1,
        };

        _session = new InferenceSession(modelPath, options);
    }

    /// <summary>
    /// Encode audio samples into a speaker embedding vector.
    /// </summary>
    /// <param name="audioSamples">Mono float32 PCM samples.</param>
    /// <param name="sampleRate">Sample rate of the input audio.</param>
    /// <returns>Speaker embedding vector (typically 256-d float32).</returns>
    public float[] Encode(float[] audioSamples, int sampleRate)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ArgumentNullException.ThrowIfNull(audioSamples);

        if (audioSamples.Length == 0)
            throw new ArgumentException("Audio samples cannot be empty.", nameof(audioSamples));

        // Resample to 16kHz if needed
        float[] resampled = sampleRate != MelSampleRate
            ? ResampleLinear(audioSamples, sampleRate, MelSampleRate)
            : audioSamples;

        // Compute mel spectrogram
        float[] mel = ComputeMelSpectrogram(resampled);
        int nFrames = mel.Length / MelNMels;

        if (nFrames == 0)
            throw new ArgumentException("Audio is too short for mel spectrogram computation.", nameof(audioSamples));

        // Create input tensor: [1, n_mels, n_frames]
        using var melTensor = OrtValue.CreateTensorValueFromMemory(
            mel, [1, MelNMels, nFrames]);

        var inputNames = new List<string> { "input" };
        var inputValues = new List<OrtValue> { melTensor };

        string[] outputNames = _session.OutputMetadata.Keys.ToArray();
        if (outputNames.Length == 0) outputNames = ["output"];

        using var runOptions = new RunOptions();
        using var results = _session.Run(runOptions, inputNames, inputValues, outputNames);

        ReadOnlySpan<float> embedding = results[0].GetTensorDataAsSpan<float>();
        return embedding.ToArray();
    }

    /// <summary>
    /// Encode audio from a WAV file into a speaker embedding.
    /// </summary>
    /// <param name="audioPath">Path to a WAV audio file.</param>
    /// <returns>Speaker embedding vector.</returns>
    public float[] EncodeFile(string audioPath)
    {
        ArgumentException.ThrowIfNullOrEmpty(audioPath);
        if (!File.Exists(audioPath))
            throw new FileNotFoundException($"Audio file not found: {audioPath}", audioPath);

        var (samples, sampleRate) = ReadWavFile(audioPath);
        return Encode(samples, sampleRate);
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed) return;
        _session.Dispose();
        _disposed = true;
    }

    // ------------------------------------------------------------------
    // Internal: WAV reading
    // ------------------------------------------------------------------

    private static (float[] Samples, int SampleRate) ReadWavFile(string path)
    {
        using var stream = File.OpenRead(path);
        using var reader = new BinaryReader(stream);

        // RIFF header
        string riff = new(reader.ReadChars(4));
        if (riff != "RIFF") throw new InvalidDataException($"Not a WAV file: {path}");
        reader.ReadInt32(); // file size
        string wave = new(reader.ReadChars(4));
        if (wave != "WAVE") throw new InvalidDataException($"Not a WAV file: {path}");

        // Find fmt chunk
        int sampleRate = 0;
        short channels = 0;
        short bitsPerSample = 0;
        short audioFormat = 0;

        while (stream.Position < stream.Length)
        {
            string chunkId = new(reader.ReadChars(4));
            int chunkSize = reader.ReadInt32();

            if (chunkId == "fmt ")
            {
                audioFormat = reader.ReadInt16();
                channels = reader.ReadInt16();
                sampleRate = reader.ReadInt32();
                reader.ReadInt32(); // byte rate
                reader.ReadInt16(); // block align
                bitsPerSample = reader.ReadInt16();
                int remaining = chunkSize - 16;
                if (remaining > 0) reader.ReadBytes(remaining);
            }
            else if (chunkId == "data")
            {
                int numSamples = chunkSize / (bitsPerSample / 8);
                float[] samples;

                if (bitsPerSample == 16)
                {
                    samples = new float[numSamples];
                    for (int i = 0; i < numSamples; i++)
                        samples[i] = reader.ReadInt16() / 32768f;
                }
                else if (bitsPerSample == 32 && audioFormat == 3) // IEEE float
                {
                    samples = new float[numSamples];
                    for (int i = 0; i < numSamples; i++)
                        samples[i] = reader.ReadSingle();
                }
                else
                {
                    throw new NotSupportedException($"Unsupported WAV format: {bitsPerSample}-bit, format={audioFormat}");
                }

                // Convert to mono
                if (channels > 1)
                {
                    int monoLen = samples.Length / channels;
                    float[] mono = new float[monoLen];
                    for (int i = 0; i < monoLen; i++)
                    {
                        float sum = 0;
                        for (int ch = 0; ch < channels; ch++)
                            sum += samples[i * channels + ch];
                        mono[i] = sum / channels;
                    }
                    return (mono, sampleRate);
                }

                return (samples, sampleRate);
            }
            else
            {
                reader.ReadBytes(chunkSize);
            }
        }

        throw new InvalidDataException($"No data chunk found in WAV file: {path}");
    }

    // ------------------------------------------------------------------
    // Internal: Audio processing
    // ------------------------------------------------------------------

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

    private static float[] ComputeMelSpectrogram(float[] samples)
    {
        float[] melFilters = CreateMelFilterbank();
        float[] window = HannWindow(MelNFft);

        int nFrames = samples.Length >= MelNFft
            ? (samples.Length - MelNFft) / MelHopLength + 1
            : 0;

        int fftBins = MelNFft / 2 + 1;
        float[] melSpec = new float[MelNMels * nFrames];

        for (int frameIdx = 0; frameIdx < nFrames; frameIdx++)
        {
            int start = frameIdx * MelHopLength;

            // Power spectrum via DFT
            float[] powerSpec = new float[fftBins];
            for (int k = 0; k < fftBins; k++)
            {
                float real = 0, imag = 0;
                float freq = -2f * MathF.PI * k / MelNFft;
                for (int n = 0; n < MelNFft; n++)
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

            // Apply mel filterbank
            for (int melIdx = 0; melIdx < MelNMels; melIdx++)
            {
                float energy = 0;
                for (int k = 0; k < fftBins; k++)
                    energy += melFilters[melIdx * fftBins + k] * powerSpec[k];

                melSpec[melIdx * nFrames + frameIdx] = MathF.Log(MathF.Max(energy, 1e-10f));
            }
        }

        return melSpec;
    }

    private static float[] HannWindow(int length)
    {
        float[] window = new float[length];
        for (int n = 0; n < length; n++)
            window[n] = 0.5f * (1f - MathF.Cos(2f * MathF.PI * n / length));
        return window;
    }

    private static float[] CreateMelFilterbank()
    {
        int fftBins = MelNFft / 2 + 1;
        float[] filterbank = new float[MelNMels * fftBins];

        float melFmin = HzToMel(MelFmin);
        float melFmax = HzToMel(MelFmax);

        float[] melPoints = new float[MelNMels + 2];
        for (int i = 0; i < melPoints.Length; i++)
            melPoints[i] = melFmin + (melFmax - melFmin) * i / (MelNMels + 1);

        float[] binPoints = new float[melPoints.Length];
        for (int i = 0; i < melPoints.Length; i++)
            binPoints[i] = MelToHz(melPoints[i]) * MelNFft / MelSampleRate;

        for (int m = 0; m < MelNMels; m++)
        {
            // Convert to integer bin indices (matching Python's np.floor().astype(int))
            int left = (int)MathF.Floor(binPoints[m]);
            int center = (int)MathF.Floor(binPoints[m + 1]);
            int right = (int)MathF.Floor(binPoints[m + 2]);

            // Edge case: if the triangle collapses to a single bin, widen it to
            // guarantee a non-zero response (matches Python reference).
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

            // Rising slope
            for (int k = left; k < center; k++)
            {
                if (center > left)
                    filterbank[m * fftBins + k] = (float)(k - left) / (center - left);
            }

            // Falling slope
            for (int k = center; k < right; k++)
            {
                if (right > center)
                    filterbank[m * fftBins + k] = (float)(right - k) / (right - center);
            }

            // Ensure center bin always has weight >= 1.0
            if (center < fftBins)
                filterbank[m * fftBins + center] = MathF.Max(filterbank[m * fftBins + center], 1.0f);
        }

        return filterbank;
    }

    private static float HzToMel(float hz) => 2595f * MathF.Log10(1f + hz / 700f);
    private static float MelToHz(float mel) => 700f * (MathF.Pow(10f, mel / 2595f) - 1f);
}
