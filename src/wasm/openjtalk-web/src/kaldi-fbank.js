/**
 * Kaldi-compatible filterbank features and Kaiser-windowed sinc resampling.
 *
 * Ports the speaker front end the public zs-v1 base was verified with
 * (scripts/public_base_runtime.py, the Hugging Face Space's zero_shot.py):
 *
 *   - resampleKaiserBest: torchaudio.functional.resample with
 *     resampling_method="sinc_interp_kaiser", lowpass_filter_width=64,
 *     rolloff=0.9475937167399596, beta=14.769656459379492 ("kaiser_best").
 *   - kaldiFbank: torchaudio.compliance.kaldi.fbank with its defaults at
 *     16 kHz, 80 mel bins, 25 ms / 10 ms frames and dither=0 (povey window,
 *     DC removal, preemphasis 0.97, 512-point power spectrum, mel bins from
 *     20 Hz to Nyquist, log floored at float32 epsilon).
 *
 * Arithmetic is float64; test/js/test-kaldi-fbank-golden.js checks the
 * result against torchaudio (test/fixtures/kaldi_fbank_golden.json).
 *
 * @module kaldi-fbank
 */

export const KALDI_FBANK_SAMPLE_RATE = 16000;
export const KALDI_FBANK_NUM_MEL_BINS = 80;

const FRAME_LENGTH = 400; // 25 ms at 16 kHz
const FRAME_SHIFT = 160; // 10 ms at 16 kHz
const PADDED_LENGTH = 512;
const PREEMPHASIS = 0.97;
const LOW_FREQ = 20;
const FLOAT32_EPSILON = 1.1920928955078125e-7;

const KAISER_BEST = {
  lowpassFilterWidth: 64,
  rolloff: 0.9475937167399596,
  beta: 14.769656459379492,
};

// ---------------------------------------------------------------------------
// Resampling
// ---------------------------------------------------------------------------

function gcd(a, b) {
  while (b) {
    [a, b] = [b, a % b];
  }
  return a;
}

// Modified Bessel function of the first kind, order 0 (power series).
function besselI0(x) {
  const q = (x * x) / 4;
  let term = 1;
  let sum = 1;
  for (let k = 1; term > sum * 1e-17; k++) {
    term *= q / (k * k);
    sum += term;
  }
  return sum;
}

const kernelCache = new Map();

// torchaudio.functional._get_sinc_resample_kernel for already gcd-reduced
// rates. Returns one row of 2 * width + orig taps per output phase.
function sincResampleKernel(orig, target) {
  const key = `${orig}:${target}`;
  const cached = kernelCache.get(key);
  if (cached) {
    return cached;
  }
  const { lowpassFilterWidth: lpw, rolloff, beta } = KAISER_BEST;
  const baseFreq = Math.min(orig, target) * rolloff;
  const width = Math.ceil((lpw * orig) / baseFreq);
  const taps = 2 * width + orig;
  const scale = baseFreq / orig;
  const i0Beta = besselI0(beta);
  const kernel = new Float64Array(target * taps);
  for (let phase = 0; phase < target; phase++) {
    for (let k = 0; k < taps; k++) {
      let t = (-phase / target + (k - width) / orig) * baseFreq;
      t = Math.max(-lpw, Math.min(lpw, t));
      const ratio = t / lpw;
      const window = besselI0(beta * Math.sqrt(1 - ratio * ratio)) / i0Beta;
      const x = t * Math.PI;
      kernel[phase * taps + k] = (x === 0 ? 1 : Math.sin(x) / x) * window * scale;
    }
  }
  const entry = { kernel, width, taps };
  kernelCache.set(key, entry);
  return entry;
}

/**
 * Resample mono PCM with torchaudio's "kaiser_best" sinc interpolation.
 *
 * @param {Float32Array} samples
 * @param {number} fromRate - Positive integer sample rate.
 * @param {number} toRate - Positive integer sample rate.
 * @returns {Float32Array} The input itself when the rates are equal.
 */
export function resampleKaiserBest(samples, fromRate, toRate) {
  for (const rate of [fromRate, toRate]) {
    if (!Number.isInteger(rate) || rate <= 0) {
      throw new RangeError(`sample rate must be a positive integer, got ${rate}`);
    }
  }
  if (fromRate === toRate) {
    return samples;
  }
  const g = gcd(fromRate, toRate);
  const orig = fromRate / g;
  const target = toRate / g;
  const { kernel, width, taps } = sincResampleKernel(orig, target);

  // Input is zero-padded by `width` on the left (F.pad in torchaudio); reads
  // outside the signal contribute nothing.
  const length = samples.length;
  const outLength = Math.ceil((target * length) / orig);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const frame = Math.floor(i / target);
    const phase = i - frame * target;
    const start = frame * orig - width;
    const row = phase * taps;
    const kFrom = Math.max(0, -start);
    const kTo = Math.min(taps, length - start);
    let acc = 0;
    for (let k = kFrom; k < kTo; k++) {
      acc += samples[start + k] * kernel[row + k];
    }
    out[i] = acc;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Filterbank
// ---------------------------------------------------------------------------

function melScale(freq) {
  return 1127 * Math.log(1 + freq / 700);
}

let povey = null;
let melBanks = null;
let fftTables = null;

// torch.hann_window(400, periodic=False).pow(0.85)
function poveyWindow() {
  if (!povey) {
    povey = new Float64Array(FRAME_LENGTH);
    for (let n = 0; n < FRAME_LENGTH; n++) {
      const hann = 0.5 - 0.5 * Math.cos((2 * Math.PI * n) / (FRAME_LENGTH - 1));
      povey[n] = Math.pow(hann, 0.85);
    }
  }
  return povey;
}

// torchaudio.compliance.kaldi.get_mel_banks without VTLN warping; the
// Nyquist bin (index 256) gets zero weight, as torchaudio pads it.
function melFilterbank() {
  if (!melBanks) {
    const numFftBins = PADDED_LENGTH / 2;
    const binWidth = KALDI_FBANK_SAMPLE_RATE / PADDED_LENGTH;
    const melLow = melScale(LOW_FREQ);
    const melHigh = melScale(KALDI_FBANK_SAMPLE_RATE / 2);
    const delta = (melHigh - melLow) / (KALDI_FBANK_NUM_MEL_BINS + 1);
    melBanks = new Float64Array(KALDI_FBANK_NUM_MEL_BINS * numFftBins);
    for (let m = 0; m < KALDI_FBANK_NUM_MEL_BINS; m++) {
      const left = melLow + m * delta;
      const center = melLow + (m + 1) * delta;
      const right = melLow + (m + 2) * delta;
      for (let k = 0; k < numFftBins; k++) {
        const mel = melScale(binWidth * k);
        const up = (mel - left) / (center - left);
        const down = (right - mel) / (right - center);
        melBanks[m * numFftBins + k] = Math.max(0, Math.min(up, down));
      }
    }
  }
  return melBanks;
}

function fftSetup() {
  if (!fftTables) {
    const n = PADDED_LENGTH;
    const bits = Math.log2(n);
    const reverse = new Uint16Array(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) {
        r = (r << 1) | ((i >> b) & 1);
      }
      reverse[i] = r;
    }
    const cos = new Float64Array(n / 2);
    const sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      cos[i] = Math.cos((2 * Math.PI * i) / n);
      sin[i] = -Math.sin((2 * Math.PI * i) / n);
    }
    fftTables = { reverse, cos, sin };
  }
  return fftTables;
}

// In-place iterative radix-2 FFT of length PADDED_LENGTH.
function fft(re, im) {
  const n = PADDED_LENGTH;
  const { reverse, cos, sin } = fftSetup();
  for (let i = 0; i < n; i++) {
    const j = reverse[i];
    if (j > i) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let size = 2; size <= n; size <<= 1) {
    const half = size >> 1;
    const step = n / size;
    for (let start = 0; start < n; start += size) {
      for (let k = 0; k < half; k++) {
        const wr = cos[k * step];
        const wi = sin[k * step];
        const a = start + k;
        const b = a + half;
        const tr = re[b] * wr - im[b] * wi;
        const ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
      }
    }
  }
}

/**
 * Compute Kaldi log mel filterbank features of mono 16 kHz PCM.
 *
 * @param {Float32Array} samples - Mono PCM at 16 kHz.
 * @returns {Float32Array} Frame-major [frames * 80]; empty when the input is
 *   shorter than one 25 ms window (frames at the edges are not padded).
 */
export function kaldiFbank(samples) {
  const numFrames =
    samples.length >= FRAME_LENGTH
      ? 1 + Math.floor((samples.length - FRAME_LENGTH) / FRAME_SHIFT)
      : 0;
  const numFftBins = PADDED_LENGTH / 2;
  const window = poveyWindow();
  const banks = melFilterbank();
  const out = new Float32Array(numFrames * KALDI_FBANK_NUM_MEL_BINS);
  const frame = new Float64Array(FRAME_LENGTH);
  const re = new Float64Array(PADDED_LENGTH);
  const im = new Float64Array(PADDED_LENGTH);
  const power = new Float64Array(numFftBins);

  for (let f = 0; f < numFrames; f++) {
    const start = f * FRAME_SHIFT;
    let mean = 0;
    for (let n = 0; n < FRAME_LENGTH; n++) {
      frame[n] = samples[start + n];
      mean += frame[n];
    }
    mean /= FRAME_LENGTH;
    for (let n = 0; n < FRAME_LENGTH; n++) {
      frame[n] -= mean;
    }
    // Preemphasis; the first sample uses itself as its predecessor.
    re.fill(0);
    im.fill(0);
    for (let n = FRAME_LENGTH - 1; n >= 0; n--) {
      const prev = n > 0 ? frame[n - 1] : frame[0];
      re[n] = (frame[n] - PREEMPHASIS * prev) * window[n];
    }
    fft(re, im);
    for (let k = 0; k < numFftBins; k++) {
      power[k] = re[k] * re[k] + im[k] * im[k];
    }
    for (let m = 0; m < KALDI_FBANK_NUM_MEL_BINS; m++) {
      let energy = 0;
      const row = m * numFftBins;
      for (let k = 0; k < numFftBins; k++) {
        energy += banks[row + k] * power[k];
      }
      out[f * KALDI_FBANK_NUM_MEL_BINS + m] = Math.log(Math.max(energy, FLOAT32_EPSILON));
    }
  }
  return out;
}
