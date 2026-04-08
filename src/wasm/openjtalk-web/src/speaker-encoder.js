/**
 * SpeakerEncoder — Browser-based voice cloning via ECAPA-TDNN ONNX model.
 *
 * Loads a speaker encoder model, computes mel spectrograms from AudioBuffer
 * or Float32Array input, and extracts speaker embeddings for voice cloning.
 *
 * Mel spectrogram parameters (unified across all runtimes):
 *   sr=16000, n_fft=512, hop=160, n_mels=80, fmin=20, fmax=7600
 *
 * @module speaker-encoder
 */

const MEL_SAMPLE_RATE = 16000;
const MEL_N_FFT = 512;
const MEL_HOP_LENGTH = 160;
const MEL_N_MELS = 80;
const MEL_FMIN = 20;
const MEL_FMAX = 7600;

export class SpeakerEncoder {
  /** @private */
  constructor() {
    this._session = null;
    this._ort = null;
  }

  /**
   * Initialize the speaker encoder with an ONNX model.
   *
   * @param {Object} options
   * @param {string} options.modelUrl - URL to the speaker encoder ONNX model.
   * @param {Object} [options.ort] - onnxruntime-web instance (defaults to globalThis.ort).
   * @returns {Promise<SpeakerEncoder>}
   */
  static async initialize(options = {}) {
    const instance = new SpeakerEncoder();
    const ort = options.ort || globalThis.ort;
    if (!ort) {
      throw new Error(
        'onnxruntime-web is required. Pass it via options.ort or load it globally.'
      );
    }
    instance._ort = ort;

    if (!options.modelUrl) {
      throw new Error('options.modelUrl is required for SpeakerEncoder');
    }

    instance._session = await ort.InferenceSession.create(options.modelUrl, {
      executionProviders: ['wasm'],
      graphOptimizationLevel: 'all',
    });

    return instance;
  }

  /**
   * Encode audio into a speaker embedding vector.
   *
   * @param {AudioBuffer|Float32Array} audio - Audio data to encode.
   *   AudioBuffer: uses the first channel; auto-resamples from buffer's sample rate.
   *   Float32Array: assumed to be mono 16kHz PCM.
   * @param {number} [sampleRate] - Sample rate when audio is Float32Array (default: 16000).
   * @returns {Promise<Float32Array>} Speaker embedding (typically 256 dimensions).
   */
  async encode(audio, sampleRate) {
    if (!this._session) {
      throw new Error('SpeakerEncoder not initialized. Call SpeakerEncoder.initialize() first.');
    }

    let samples;
    let rate;

    if (typeof AudioBuffer !== 'undefined' && audio instanceof AudioBuffer) {
      // Extract first channel
      samples = audio.getChannelData(0);
      rate = audio.sampleRate;
    } else if (audio instanceof Float32Array) {
      samples = audio;
      rate = sampleRate || MEL_SAMPLE_RATE;
    } else {
      throw new TypeError('audio must be an AudioBuffer or Float32Array');
    }

    if (samples.length === 0) {
      throw new Error('Audio samples cannot be empty');
    }

    // Resample to 16kHz if needed
    const resampled = rate !== MEL_SAMPLE_RATE
      ? resampleLinear(samples, rate, MEL_SAMPLE_RATE)
      : samples;

    // Compute mel spectrogram
    const mel = computeMelSpectrogram(resampled);
    const nFrames = mel.length / MEL_N_MELS;

    if (nFrames === 0) {
      throw new Error('Audio is too short for mel spectrogram computation');
    }

    // Create input tensor: [1, n_mels, n_frames]
    const ort = this._ort;
    const melTensor = new ort.Tensor('float32', mel, [1, MEL_N_MELS, nFrames]);

    const results = await this._session.run({ input: melTensor });
    const outputTensor = results.output || results[Object.keys(results)[0]];

    return new Float32Array(outputTensor.data);
  }

  /**
   * Release all resources held by this encoder.
   */
  dispose() {
    if (this._session) {
      if (typeof this._session.release === 'function') {
        this._session.release();
      }
      this._session = null;
    }
    this._ort = null;
  }
}

// ---------------------------------------------------------------------------
// Audio processing helpers (internal)
// ---------------------------------------------------------------------------

/**
 * Resample audio via linear interpolation.
 * @param {Float32Array} samples
 * @param {number} fromRate
 * @param {number} toRate
 * @returns {Float32Array}
 */
function resampleLinear(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples;

  const ratio = fromRate / toRate;
  const outputLen = Math.ceil(samples.length / ratio);
  const output = new Float32Array(outputLen);

  for (let i = 0; i < outputLen; i++) {
    const srcPos = i * ratio;
    const idx = Math.floor(srcPos);
    const frac = srcPos - idx;

    if (idx + 1 < samples.length) {
      output[i] = samples[idx] * (1 - frac) + samples[idx + 1] * frac;
    } else if (idx < samples.length) {
      output[i] = samples[idx];
    }
  }

  return output;
}

/**
 * Compute log mel spectrogram.
 * @param {Float32Array} samples - Mono 16kHz audio.
 * @returns {Float32Array} Flattened [n_mels * n_frames] in mel-major order.
 */
function computeMelSpectrogram(samples) {
  const melFilters = createMelFilterbank();
  const window = hannWindow(MEL_N_FFT);

  const nFrames = samples.length >= MEL_N_FFT
    ? Math.floor((samples.length - MEL_N_FFT) / MEL_HOP_LENGTH) + 1
    : 0;

  const fftBins = Math.floor(MEL_N_FFT / 2) + 1;
  const melSpec = new Float32Array(MEL_N_MELS * nFrames);

  for (let frameIdx = 0; frameIdx < nFrames; frameIdx++) {
    const start = frameIdx * MEL_HOP_LENGTH;

    // Power spectrum via DFT
    const powerSpec = new Float32Array(fftBins);
    for (let k = 0; k < fftBins; k++) {
      let real = 0, imag = 0;
      const freq = -2 * Math.PI * k / MEL_N_FFT;
      for (let n = 0; n < MEL_N_FFT; n++) {
        const sample = (start + n < samples.length)
          ? samples[start + n] * window[n]
          : 0;
        const angle = freq * n;
        real += sample * Math.cos(angle);
        imag += sample * Math.sin(angle);
      }
      powerSpec[k] = real * real + imag * imag;
    }

    // Apply mel filterbank
    for (let melIdx = 0; melIdx < MEL_N_MELS; melIdx++) {
      let energy = 0;
      for (let k = 0; k < fftBins; k++) {
        energy += melFilters[melIdx * fftBins + k] * powerSpec[k];
      }
      melSpec[melIdx * nFrames + frameIdx] = Math.log(Math.max(energy, 1e-10));
    }
  }

  return melSpec;
}

function hannWindow(length) {
  const window = new Float32Array(length);
  for (let n = 0; n < length; n++) {
    window[n] = 0.5 * (1 - Math.cos(2 * Math.PI * n / length));
  }
  return window;
}

function createMelFilterbank() {
  const fftBins = Math.floor(MEL_N_FFT / 2) + 1;
  const filterbank = new Float32Array(MEL_N_MELS * fftBins);

  const melFmin = hzToMel(MEL_FMIN);
  const melFmax = hzToMel(MEL_FMAX);

  const melPoints = [];
  for (let i = 0; i <= MEL_N_MELS + 1; i++) {
    melPoints.push(melFmin + (melFmax - melFmin) * i / (MEL_N_MELS + 1));
  }

  const binPoints = melPoints.map(m => melToHz(m) * MEL_N_FFT / MEL_SAMPLE_RATE);

  for (let m = 0; m < MEL_N_MELS; m++) {
    // Convert to integer bin indices (matching Python's np.floor().astype(int))
    let left = Math.floor(binPoints[m]);
    let center = Math.floor(binPoints[m + 1]);
    let right = Math.floor(binPoints[m + 2]);

    // Edge case: if the triangle collapses to a single bin, widen it to
    // guarantee a non-zero response (matches Python reference).
    if (left === center && center === right) {
      center = Math.min(center + 1, fftBins - 1);
      right = Math.min(right + 2, fftBins - 1);
    } else if (left === center) {
      center = Math.min(center + 1, fftBins - 1);
    }
    if (center === right) {
      right = Math.min(right + 1, fftBins - 1);
    }

    // Rising slope
    for (let k = left; k < center; k++) {
      if (center > left) {
        filterbank[m * fftBins + k] = (k - left) / (center - left);
      }
    }

    // Falling slope
    for (let k = center; k < right; k++) {
      if (right > center) {
        filterbank[m * fftBins + k] = (right - k) / (right - center);
      }
    }

    // Ensure center bin always has weight >= 1.0
    if (center < fftBins) {
      filterbank[m * fftBins + center] = Math.max(filterbank[m * fftBins + center], 1.0);
    }
  }

  return filterbank;
}

function hzToMel(hz) {
  return 2595 * Math.log10(1 + hz / 700);
}

function melToHz(mel) {
  return 700 * (Math.pow(10, mel / 2595) - 1);
}
