package piperplus

// Kaldi-compatible filterbank features and Kaiser-windowed sinc resampling.
//
// Ports the speaker front end the public zs-v1 base was verified with
// (scripts/public_base_runtime.py, the Hugging Face Space's zero_shot.py and
// the browser's kaldi-fbank.js):
//
//   - ResampleKaiserBest: torchaudio.functional.resample with
//     resampling_method="sinc_interp_kaiser", lowpass_filter_width=64,
//     rolloff=0.9475937167399596, beta=14.769656459379492 ("kaiser_best").
//   - KaldiFbank: torchaudio.compliance.kaldi.fbank with its defaults at
//     16 kHz, 80 mel bins, 25 ms / 10 ms frames and dither=0 (povey window,
//     DC removal, preemphasis 0.97, 512-point power spectrum, mel bins from
//     20 Hz to Nyquist, log floored at float32 epsilon).
//
// Arithmetic is float64; kaldi_fbank_test.go checks the result against
// torchaudio (test/fixtures/kaldi_fbank_golden.json).

import (
	"fmt"
	"math"
	"math/bits"
)

const (
	// KaldiFbankSampleRate is the sample rate the features are computed at.
	KaldiFbankSampleRate = 16000
	// KaldiFbankNumMelBins is the number of mel bins per frame.
	KaldiFbankNumMelBins = 80

	kaldiFrameLength = 400 // 25 ms at 16 kHz
	kaldiFrameShift  = 160 // 10 ms at 16 kHz
	kaldiPaddedLen   = 512
	kaldiNumFFTBins  = kaldiPaddedLen / 2
	kaldiPreemphasis = 0.97
	kaldiLowFreq     = 20.0
	float32Epsilon   = 1.1920928955078125e-7

	kaiserLowpassFilterWidth = 64.0
	kaiserRolloff            = 0.9475937167399596
	kaiserBeta               = 14.769656459379492
)

// ---------------------------------------------------------------------------
// Resampling
// ---------------------------------------------------------------------------

func gcdInt(a, b int) int {
	for b != 0 {
		a, b = b, a%b
	}
	return a
}

// besselI0 is the modified Bessel function of the first kind, order 0
// (power series).
func besselI0(x float64) float64 {
	q := x * x / 4
	term, sum := 1.0, 1.0
	for k := 1.0; term > sum*1e-17; k++ {
		term *= q / (k * k)
		sum += term
	}
	return sum
}

// sincResampleKernel is torchaudio.functional._get_sinc_resample_kernel for
// already gcd-reduced rates. It returns one row of taps coefficients per
// output phase.
func sincResampleKernel(orig, target int) (kernel []float64, width, taps int) {
	baseFreq := float64(min(orig, target)) * kaiserRolloff
	width = int(math.Ceil(kaiserLowpassFilterWidth * float64(orig) / baseFreq))
	taps = 2*width + orig
	scale := baseFreq / float64(orig)
	i0Beta := besselI0(kaiserBeta)
	kernel = make([]float64, target*taps)
	for phase := 0; phase < target; phase++ {
		for k := 0; k < taps; k++ {
			t := (-float64(phase)/float64(target) + float64(k-width)/float64(orig)) * baseFreq
			t = math.Max(-kaiserLowpassFilterWidth, math.Min(kaiserLowpassFilterWidth, t))
			ratio := t / kaiserLowpassFilterWidth
			window := besselI0(kaiserBeta*math.Sqrt(1-ratio*ratio)) / i0Beta
			x := t * math.Pi
			sinc := 1.0
			if x != 0 {
				sinc = math.Sin(x) / x
			}
			kernel[phase*taps+k] = sinc * window * scale
		}
	}
	return kernel, width, taps
}

// ResampleKaiserBest resamples mono PCM with torchaudio's "kaiser_best"
// sinc interpolation. It returns the input itself when the rates are equal.
func ResampleKaiserBest(samples []float32, fromRate, toRate int) ([]float32, error) {
	if fromRate <= 0 || toRate <= 0 {
		return nil, fmt.Errorf("sample rate must be positive, got %d -> %d", fromRate, toRate)
	}
	if fromRate == toRate {
		return samples, nil
	}
	g := gcdInt(fromRate, toRate)
	orig, target := fromRate/g, toRate/g
	kernel, width, taps := sincResampleKernel(orig, target)

	// Input is zero-padded by width on the left (F.pad in torchaudio);
	// reads outside the signal contribute nothing.
	length := len(samples)
	outLength := (target*length + orig - 1) / orig
	out := make([]float32, outLength)
	for i := range out {
		frame := i / target
		phase := i - frame*target
		start := frame*orig - width
		row := kernel[phase*taps : (phase+1)*taps]
		kFrom := max(0, -start)
		kTo := min(taps, length-start)
		acc := 0.0
		for k := kFrom; k < kTo; k++ {
			acc += float64(samples[start+k]) * row[k]
		}
		out[i] = float32(acc)
	}
	return out, nil
}

// ---------------------------------------------------------------------------
// Filterbank
// ---------------------------------------------------------------------------

func kaldiMelScale(freq float64) float64 {
	return 1127 * math.Log(1+freq/700)
}

// poveyWindow is torch.hann_window(400, periodic=False).pow(0.85).
func poveyWindow() []float64 {
	w := make([]float64, kaldiFrameLength)
	for n := range w {
		hann := 0.5 - 0.5*math.Cos(2*math.Pi*float64(n)/float64(kaldiFrameLength-1))
		w[n] = math.Pow(hann, 0.85)
	}
	return w
}

// kaldiMelBanks is torchaudio.compliance.kaldi.get_mel_banks without VTLN
// warping; the Nyquist bin (index 256) gets zero weight, as torchaudio pads
// it.
func kaldiMelBanks() []float64 {
	binWidth := float64(KaldiFbankSampleRate) / kaldiPaddedLen
	melLow := kaldiMelScale(kaldiLowFreq)
	melHigh := kaldiMelScale(KaldiFbankSampleRate / 2)
	delta := (melHigh - melLow) / (KaldiFbankNumMelBins + 1)
	banks := make([]float64, KaldiFbankNumMelBins*kaldiNumFFTBins)
	for m := 0; m < KaldiFbankNumMelBins; m++ {
		left := melLow + float64(m)*delta
		center := melLow + float64(m+1)*delta
		right := melLow + float64(m+2)*delta
		for k := 0; k < kaldiNumFFTBins; k++ {
			mel := kaldiMelScale(binWidth * float64(k))
			up := (mel - left) / (center - left)
			down := (right - mel) / (right - center)
			banks[m*kaldiNumFFTBins+k] = math.Max(0, math.Min(up, down))
		}
	}
	return banks
}

// fft512 holds the twiddle factors and bit-reversal table for a radix-2
// FFT of kaldiPaddedLen points.
type fft512 struct {
	reverse  []int
	cos, sin []float64
}

func newFFT512() *fft512 {
	n := kaldiPaddedLen
	shift := 64 - bits.TrailingZeros(uint(n))
	f := &fft512{
		reverse: make([]int, n),
		cos:     make([]float64, n/2),
		sin:     make([]float64, n/2),
	}
	for i := range f.reverse {
		f.reverse[i] = int(bits.Reverse64(uint64(i)) >> shift)
	}
	for i := range f.cos {
		f.cos[i] = math.Cos(2 * math.Pi * float64(i) / float64(n))
		f.sin[i] = -math.Sin(2 * math.Pi * float64(i) / float64(n))
	}
	return f
}

// run is an in-place iterative radix-2 FFT.
func (f *fft512) run(re, im []float64) {
	n := kaldiPaddedLen
	for i := 0; i < n; i++ {
		if j := f.reverse[i]; j > i {
			re[i], re[j] = re[j], re[i]
			im[i], im[j] = im[j], im[i]
		}
	}
	for size := 2; size <= n; size <<= 1 {
		half := size >> 1
		step := n / size
		for start := 0; start < n; start += size {
			for k := 0; k < half; k++ {
				wr, wi := f.cos[k*step], f.sin[k*step]
				a := start + k
				b := a + half
				tr := re[b]*wr - im[b]*wi
				ti := re[b]*wi + im[b]*wr
				re[b] = re[a] - tr
				im[b] = im[a] - ti
				re[a] += tr
				im[a] += ti
			}
		}
	}
}

// KaldiFbank computes Kaldi log mel filterbank features of mono 16 kHz PCM.
// It returns a frame-major [frames * 80] slice; empty when the input is
// shorter than one 25 ms window (frames at the edges are not padded).
func KaldiFbank(samples []float32) []float32 {
	numFrames := 0
	if len(samples) >= kaldiFrameLength {
		numFrames = 1 + (len(samples)-kaldiFrameLength)/kaldiFrameShift
	}
	window := poveyWindow()
	banks := kaldiMelBanks()
	fft := newFFT512()
	out := make([]float32, numFrames*KaldiFbankNumMelBins)
	frame := make([]float64, kaldiFrameLength)
	re := make([]float64, kaldiPaddedLen)
	im := make([]float64, kaldiPaddedLen)
	power := make([]float64, kaldiNumFFTBins)

	for f := 0; f < numFrames; f++ {
		start := f * kaldiFrameShift
		mean := 0.0
		for n := range frame {
			frame[n] = float64(samples[start+n])
			mean += frame[n]
		}
		mean /= kaldiFrameLength
		for n := range frame {
			frame[n] -= mean
		}
		// Preemphasis; the first sample uses itself as its predecessor.
		clear(re)
		clear(im)
		for n := range frame {
			prev := frame[0]
			if n > 0 {
				prev = frame[n-1]
			}
			re[n] = (frame[n] - kaldiPreemphasis*prev) * window[n]
		}
		fft.run(re, im)
		for k := range power {
			power[k] = re[k]*re[k] + im[k]*im[k]
		}
		for m := 0; m < KaldiFbankNumMelBins; m++ {
			row := banks[m*kaldiNumFFTBins : (m+1)*kaldiNumFFTBins]
			energy := 0.0
			for k, b := range row {
				energy += b * power[k]
			}
			out[f*KaldiFbankNumMelBins+m] = float32(math.Log(math.Max(energy, float32Epsilon)))
		}
	}
	return out
}

// subtractBandMeans subtracts each mel bin's mean over time from a
// frame-major [frames * 80] slice (features -= features.mean(dim=0) in the
// Python recipe).
func subtractBandMeans(features []float32) {
	frames := len(features) / KaldiFbankNumMelBins
	if frames == 0 {
		return
	}
	for m := 0; m < KaldiFbankNumMelBins; m++ {
		sum := 0.0
		for f := 0; f < frames; f++ {
			sum += float64(features[f*KaldiFbankNumMelBins+m])
		}
		mean := sum / float64(frames)
		for f := 0; f < frames; f++ {
			i := f*KaldiFbankNumMelBins + m
			features[i] = float32(float64(features[i]) - mean)
		}
	}
}
