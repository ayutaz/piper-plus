using System;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Kaldi-compatible filterbank features and Kaiser-windowed sinc resampling.
/// </summary>
/// <remarks>
/// <para>
/// Ports the speaker front end the public zs-v1 base was verified with
/// (<c>scripts/public_base_runtime.py</c>, the Hugging Face Space's
/// <c>zero_shot.py</c> and the browser's <c>kaldi-fbank.js</c>):
/// </para>
/// <list type="bullet">
///   <item><see cref="ResampleKaiserBest"/>: <c>torchaudio.functional.resample</c>
///   with <c>resampling_method="sinc_interp_kaiser"</c>, <c>lowpass_filter_width=64</c>,
///   <c>rolloff=0.9475937167399596</c>, <c>beta=14.769656459379492</c> ("kaiser_best").</item>
///   <item><see cref="Fbank"/>: <c>torchaudio.compliance.kaldi.fbank</c> with its
///   defaults at 16 kHz, 80 mel bins, 25 ms / 10 ms frames and <c>dither=0</c>
///   (povey window, DC removal, preemphasis 0.97, 512-point power spectrum,
///   mel bins from 20 Hz to Nyquist, log floored at float32 epsilon).</item>
/// </list>
/// <para>
/// Arithmetic is double; <c>KaldiFbankTests</c> checks the result against
/// torchaudio (<c>test/fixtures/kaldi_fbank_golden.json</c>).
/// </para>
/// </remarks>
internal static class KaldiFbank
{
    internal const int SampleRate = 16000;
    internal const int NumMelBins = 80;

    private const int FrameLength = 400; // 25 ms at 16 kHz
    private const int FrameShift = 160; // 10 ms at 16 kHz
    private const int PaddedLength = 512;
    private const int NumFftBins = PaddedLength / 2;
    private const double Preemphasis = 0.97;
    private const double LowFreq = 20.0;
    private const double Float32Epsilon = 1.1920928955078125e-7;

    private const double KaiserLowpassFilterWidth = 64.0;
    private const double KaiserRolloff = 0.9475937167399596;
    private const double KaiserBeta = 14.769656459379492;

    // ------------------------------------------------------------------
    // Resampling
    // ------------------------------------------------------------------

    /// <summary>
    /// Resample mono PCM with torchaudio's "kaiser_best" sinc interpolation.
    /// Returns the input itself when the rates are equal.
    /// </summary>
    internal static float[] ResampleKaiserBest(float[] samples, int fromRate, int toRate)
    {
        ArgumentNullException.ThrowIfNull(samples);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(fromRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(toRate);
        if (fromRate == toRate)
        {
            return samples;
        }

        int g = Gcd(fromRate, toRate);
        int orig = fromRate / g;
        int target = toRate / g;
        double[] kernel = SincResampleKernel(orig, target, out int width, out int taps);

        // Input is zero-padded by `width` on the left (F.pad in torchaudio);
        // reads outside the signal contribute nothing.
        int length = samples.Length;
        int outLength = (int)((((long)target * length) + orig - 1) / orig);
        float[] output = new float[outLength];
        for (int i = 0; i < outLength; i++)
        {
            int frame = i / target;
            int phase = i - (frame * target);
            int start = (frame * orig) - width;
            int row = phase * taps;
            int kFrom = Math.Max(0, -start);
            int kTo = Math.Min(taps, length - start);
            double acc = 0;
            for (int k = kFrom; k < kTo; k++)
            {
                acc += samples[start + k] * kernel[row + k];
            }

            output[i] = (float)acc;
        }

        return output;
    }

    private static int Gcd(int a, int b)
    {
        while (b != 0)
        {
            (a, b) = (b, a % b);
        }

        return a;
    }

    // Modified Bessel function of the first kind, order 0 (power series).
    private static double BesselI0(double x)
    {
        double q = x * x / 4;
        double term = 1;
        double sum = 1;
        double k = 1;
        while (term > sum * 1e-17)
        {
            term *= q / (k * k);
            sum += term;
            k++;
        }

        return sum;
    }

    // torchaudio.functional._get_sinc_resample_kernel for already gcd-reduced
    // rates. Returns one row of `taps` coefficients per output phase.
    private static double[] SincResampleKernel(int orig, int target, out int width, out int taps)
    {
        double baseFreq = Math.Min(orig, target) * KaiserRolloff;
        width = (int)Math.Ceiling(KaiserLowpassFilterWidth * orig / baseFreq);
        taps = (2 * width) + orig;
        double scale = baseFreq / orig;
        double i0Beta = BesselI0(KaiserBeta);
        double[] kernel = new double[target * taps];
        for (int phase = 0; phase < target; phase++)
        {
            for (int k = 0; k < taps; k++)
            {
                double t = ((-(double)phase / target) + ((double)(k - width) / orig)) * baseFreq;
                t = Math.Clamp(t, -KaiserLowpassFilterWidth, KaiserLowpassFilterWidth);
                double ratio = t / KaiserLowpassFilterWidth;
                double window = BesselI0(KaiserBeta * Math.Sqrt(1 - (ratio * ratio))) / i0Beta;
                double x = t * Math.PI;
                double sinc = x == 0 ? 1 : Math.Sin(x) / x;
                kernel[(phase * taps) + k] = sinc * window * scale;
            }
        }

        return kernel;
    }

    // ------------------------------------------------------------------
    // Filterbank
    // ------------------------------------------------------------------

    /// <summary>
    /// Compute Kaldi log mel filterbank features of mono 16 kHz PCM.
    /// </summary>
    /// <returns>Frame-major <c>[frames * 80]</c>; empty when the input is
    /// shorter than one 25 ms window (frames at the edges are not padded).</returns>
    internal static float[] Fbank(float[] samples)
    {
        ArgumentNullException.ThrowIfNull(samples);
        int numFrames = samples.Length >= FrameLength
            ? 1 + ((samples.Length - FrameLength) / FrameShift)
            : 0;
        double[] window = PoveyWindow();
        double[] banks = MelBanks();
        var fft = new Fft512();
        float[] output = new float[numFrames * NumMelBins];
        double[] frame = new double[FrameLength];
        double[] re = new double[PaddedLength];
        double[] im = new double[PaddedLength];
        double[] power = new double[NumFftBins];

        for (int f = 0; f < numFrames; f++)
        {
            int start = f * FrameShift;
            double mean = 0;
            for (int n = 0; n < FrameLength; n++)
            {
                frame[n] = samples[start + n];
                mean += frame[n];
            }

            mean /= FrameLength;
            for (int n = 0; n < FrameLength; n++)
            {
                frame[n] -= mean;
            }

            // Preemphasis; the first sample uses itself as its predecessor.
            Array.Clear(re);
            Array.Clear(im);
            for (int n = 0; n < FrameLength; n++)
            {
                double prev = n > 0 ? frame[n - 1] : frame[0];
                re[n] = (frame[n] - (Preemphasis * prev)) * window[n];
            }

            fft.Run(re, im);
            for (int k = 0; k < NumFftBins; k++)
            {
                power[k] = (re[k] * re[k]) + (im[k] * im[k]);
            }

            for (int m = 0; m < NumMelBins; m++)
            {
                double energy = 0;
                int row = m * NumFftBins;
                for (int k = 0; k < NumFftBins; k++)
                {
                    energy += banks[row + k] * power[k];
                }

                output[(f * NumMelBins) + m] = (float)Math.Log(Math.Max(energy, Float32Epsilon));
            }
        }

        return output;
    }

    /// <summary>
    /// Subtract each mel bin's mean over time from a frame-major
    /// <c>[frames * 80]</c> array (<c>features -= features.mean(dim=0)</c> in
    /// the Python recipe).
    /// </summary>
    internal static void SubtractBandMeans(float[] features)
    {
        ArgumentNullException.ThrowIfNull(features);
        int frames = features.Length / NumMelBins;
        if (frames == 0)
        {
            return;
        }

        for (int m = 0; m < NumMelBins; m++)
        {
            double sum = 0;
            for (int f = 0; f < frames; f++)
            {
                sum += features[(f * NumMelBins) + m];
            }

            double mean = sum / frames;
            for (int f = 0; f < frames; f++)
            {
                int i = (f * NumMelBins) + m;
                features[i] = (float)(features[i] - mean);
            }
        }
    }

    private static double MelScale(double freq) => 1127 * Math.Log(1 + (freq / 700));

    // torch.hann_window(400, periodic=False).pow(0.85)
    private static double[] PoveyWindow()
    {
        double[] w = new double[FrameLength];
        for (int n = 0; n < FrameLength; n++)
        {
            double hann = 0.5 - (0.5 * Math.Cos(2 * Math.PI * n / (FrameLength - 1)));
            w[n] = Math.Pow(hann, 0.85);
        }

        return w;
    }

    // torchaudio.compliance.kaldi.get_mel_banks without VTLN warping; the
    // Nyquist bin (index 256) gets zero weight, as torchaudio pads it.
    private static double[] MelBanks()
    {
        double binWidth = (double)SampleRate / PaddedLength;
        double melLow = MelScale(LowFreq);
        double melHigh = MelScale(SampleRate / 2.0);
        double delta = (melHigh - melLow) / (NumMelBins + 1);
        double[] banks = new double[NumMelBins * NumFftBins];
        for (int m = 0; m < NumMelBins; m++)
        {
            double left = melLow + (m * delta);
            double center = melLow + ((m + 1) * delta);
            double right = melLow + ((m + 2) * delta);
            for (int k = 0; k < NumFftBins; k++)
            {
                double mel = MelScale(binWidth * k);
                double up = (mel - left) / (center - left);
                double down = (right - mel) / (right - center);
                banks[(m * NumFftBins) + k] = Math.Max(0, Math.Min(up, down));
            }
        }

        return banks;
    }

    // Iterative radix-2 FFT of PaddedLength points.
    private sealed class Fft512
    {
        private readonly int[] _reverse = new int[PaddedLength];
        private readonly double[] _cos = new double[PaddedLength / 2];
        private readonly double[] _sin = new double[PaddedLength / 2];

        public Fft512()
        {
            int bits = System.Numerics.BitOperations.Log2(PaddedLength);
            for (int i = 0; i < PaddedLength; i++)
            {
                int r = 0;
                for (int b = 0; b < bits; b++)
                {
                    r = (r << 1) | ((i >> b) & 1);
                }

                _reverse[i] = r;
            }

            for (int i = 0; i < PaddedLength / 2; i++)
            {
                _cos[i] = Math.Cos(2 * Math.PI * i / PaddedLength);
                _sin[i] = -Math.Sin(2 * Math.PI * i / PaddedLength);
            }
        }

        public void Run(double[] re, double[] im)
        {
            for (int i = 0; i < PaddedLength; i++)
            {
                int j = _reverse[i];
                if (j > i)
                {
                    (re[i], re[j]) = (re[j], re[i]);
                    (im[i], im[j]) = (im[j], im[i]);
                }
            }

            for (int size = 2; size <= PaddedLength; size <<= 1)
            {
                int half = size >> 1;
                int step = PaddedLength / size;
                for (int start = 0; start < PaddedLength; start += size)
                {
                    for (int k = 0; k < half; k++)
                    {
                        double wr = _cos[k * step];
                        double wi = _sin[k * step];
                        int a = start + k;
                        int b = a + half;
                        double tr = (re[b] * wr) - (im[b] * wi);
                        double ti = (re[b] * wi) + (im[b] * wr);
                        re[b] = re[a] - tr;
                        im[b] = im[a] - ti;
                        re[a] += tr;
                        im[a] += ti;
                    }
                }
            }
        }
    }
}
