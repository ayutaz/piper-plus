/**
 * SpeakerEncoder — Browser-based voice cloning via ECAPA-TDNN ONNX model.
 *
 * Loads a speaker encoder model, computes mel spectrograms from AudioBuffer
 * or Float32Array input, and extracts speaker embeddings for voice cloning.
 *
 * Mel spectrogram parameters (unified across all runtimes):
 *   sr=16000, n_fft=400, hop=160, n_mels=80, fmin=20, fmax=7600
 *   (n_fft=400 matches Kaldi frame_length=25ms at 16kHz; canonical across
 *    Python/Rust/Go/C#/C++ — see test/generate_speaker_encoder_golden.py.)
 *
 * @module speaker-encoder
 */

const MEL_SAMPLE_RATE = 16000;
const MEL_N_FFT = 400;
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
      throw new Error("onnxruntime-web is required. Pass it via options.ort or load it globally.");
    }
    instance._ort = ort;

    if (!options.modelUrl) {
      throw new Error("options.modelUrl is required for SpeakerEncoder");
    }

    instance._session = await ort.InferenceSession.create(options.modelUrl, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "all",
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
      throw new Error("SpeakerEncoder not initialized. Call SpeakerEncoder.initialize() first.");
    }

    let samples;
    let rate;

    if (typeof AudioBuffer !== "undefined" && audio instanceof AudioBuffer) {
      // Extract first channel
      samples = audio.getChannelData(0);
      rate = audio.sampleRate;
    } else if (audio instanceof Float32Array) {
      samples = audio;
      rate = sampleRate || MEL_SAMPLE_RATE;
    } else {
      throw new TypeError("audio must be an AudioBuffer or Float32Array");
    }

    if (samples.length === 0) {
      throw new Error("Audio samples cannot be empty");
    }

    // Resample to 16kHz if needed
    const resampled =
      rate !== MEL_SAMPLE_RATE ? resampleLinear(samples, rate, MEL_SAMPLE_RATE) : samples;

    // Compute mel spectrogram
    const mel = computeMelSpectrogram(resampled);
    const nFrames = mel.length / MEL_N_MELS;

    if (nFrames === 0) {
      throw new Error("Audio is too short for mel spectrogram computation");
    }

    // Create input tensor: [1, n_frames, n_mels] (frame-major, as expected
    // by CAM++ — matches Rust/Go/C#/C++ runtimes).
    const ort = this._ort;
    const melTensor = new ort.Tensor("float32", mel, [1, nFrames, MEL_N_MELS]);

    const results = await this._session.run({ input: melTensor });
    const outputTensor = results.output || results[Object.keys(results)[0]];

    return new Float32Array(outputTensor.data);
  }

  /**
   * Release all resources held by this encoder.
   */
  dispose() {
    if (this._session) {
      if (typeof this._session.release === "function") {
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
  if (fromRate === toRate) {
    return samples;
  }

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
 * @returns {Float32Array} Flattened [n_frames * n_mels] in frame-major order
 *   (frame 0 mel 0, frame 0 mel 1, ..., frame 1 mel 0, ...). Matches the
 *   CAM++ expected input layout [batch, T, 80] used by Python/Rust/Go/C#/C++.
 *   Per-band mean subtraction (CMVN) is applied after computing the log mel.
 */
// fr32 forces a value to its nearest float32 representation. Used at every
// arithmetic step so the JS path matches Python's float32 semantics
// byte-for-byte (see test/generate_speaker_encoder_golden.py — F32 alias).
const fr32 = Math.fround;

export function computeMelSpectrogram(samples) {
  const melFilters = createMelFilterbank();
  const window = hannWindow(MEL_N_FFT);

  const nFrames =
    samples.length >= MEL_N_FFT ? Math.floor((samples.length - MEL_N_FFT) / MEL_HOP_LENGTH) + 1 : 0;

  const fftBins = Math.floor(MEL_N_FFT / 2) + 1;
  // Frame-major layout: melSpec[frameIdx * MEL_N_MELS + melIdx]
  const melSpec = new Float32Array(nFrames * MEL_N_MELS);

  for (let frameIdx = 0; frameIdx < nFrames; frameIdx++) {
    const start = frameIdx * MEL_HOP_LENGTH;

    // Power spectrum via DFT. Match the Python reference numerics:
    //   - `sample` (= audio[i] * window[i]) is float32.
    //   - cos/sin compute in float64 (Math.cos input is auto-promoted),
    //     so the multiplication `sample * cos(angle)` happens in f64
    //     (mirrors Python `f32 * np.cos(f32_angle) → f64`).
    //   - Accumulators `real`/`imag` are clamped back to float32 after each
    //     add via Math.fround — matches numpy's `F32_scalar += f64_value`
    //     semantics (the addition uses higher precision, the result is
    //     truncated to f32 on store).
    // Casting cos/sin to f32 (the old behavior) produced stationary output
    // for pure sines, which CMVN then collapsed to zero — see Go runtime's
    // identical comment for the same trap.
    const powerSpec = new Float32Array(fftBins);
    for (let k = 0; k < fftBins; k++) {
      let real = fr32(0),
        imag = fr32(0);
      const freq = (-2 * Math.PI * k) / MEL_N_FFT;
      for (let n = 0; n < MEL_N_FFT; n++) {
        const winSample =
          start + n < samples.length ? fr32(fr32(samples[start + n]) * fr32(window[n])) : fr32(0);
        const angle = freq * n;
        real = fr32(real + winSample * Math.cos(angle));
        imag = fr32(imag + winSample * Math.sin(angle));
      }
      powerSpec[k] = fr32(fr32(real * real) + fr32(imag * imag));
    }

    // Apply mel filterbank — float32 arithmetic. Store in frame-major order.
    for (let melIdx = 0; melIdx < MEL_N_MELS; melIdx++) {
      let energy = fr32(0);
      for (let k = 0; k < fftBins; k++) {
        energy = fr32(energy + fr32(melFilters[melIdx * fftBins + k] * powerSpec[k]));
      }
      // np.log accepts a Python float (f64); the output is then cast to f32
      // when stored in mel_spec (which is dtype=F32). Match that here:
      // log of f32-clamped energy, then cast result to f32.
      melSpec[frameIdx * MEL_N_MELS + melIdx] = fr32(Math.log(Math.max(fr32(energy), 1e-10)));
    }
  }

  // CMVN: subtract per-band mean across all frames (matches Python/Rust).
  if (nFrames > 0) {
    for (let melIdx = 0; melIdx < MEL_N_MELS; melIdx++) {
      let sum = 0;
      for (let frameIdx = 0; frameIdx < nFrames; frameIdx++) {
        sum += melSpec[frameIdx * MEL_N_MELS + melIdx];
      }
      const mean = fr32(sum / nFrames);
      for (let frameIdx = 0; frameIdx < nFrames; frameIdx++) {
        melSpec[frameIdx * MEL_N_MELS + melIdx] = fr32(
          melSpec[frameIdx * MEL_N_MELS + melIdx] - mean
        );
      }
    }
  }

  return melSpec;
}

export function hannWindow(length) {
  const window = new Float32Array(length);
  for (let n = 0; n < length; n++) {
    window[n] = fr32(fr32(0.5) * fr32(1 - Math.cos((fr32(2 * Math.PI) * fr32(n)) / fr32(length))));
  }
  return window;
}

export function createMelFilterbank() {
  const fftBins = Math.floor(MEL_N_FFT / 2) + 1;
  const filterbank = new Float32Array(MEL_N_MELS * fftBins);

  const melFmin = hzToMel(fr32(MEL_FMIN));
  const melFmax = hzToMel(fr32(MEL_FMAX));

  const melPoints = [];
  for (let i = 0; i <= MEL_N_MELS + 1; i++) {
    // Python: F32(mel_fmin) + (mel_fmax - mel_fmin) * F32(i) / F32(N_MELS + 1)
    melPoints.push(
      fr32(melFmin + fr32((fr32(melFmax - melFmin) * fr32(i)) / fr32(MEL_N_MELS + 1)))
    );
  }

  const binPoints = melPoints.map((m) =>
    fr32((fr32(melToHz(m)) * fr32(MEL_N_FFT)) / fr32(MEL_SAMPLE_RATE))
  );

  for (let m = 0; m < MEL_N_MELS; m++) {
    // Convert to integer bin indices (matching Python's np.floor().astype(int))
    const left = Math.floor(binPoints[m]);
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

    // Rising slope — float32 arithmetic.
    for (let k = left; k < center; k++) {
      if (center > left) {
        filterbank[m * fftBins + k] = fr32(fr32(k - left) / fr32(center - left));
      }
    }

    // Falling slope.
    for (let k = center; k < right; k++) {
      if (right > center) {
        filterbank[m * fftBins + k] = fr32(fr32(right - k) / fr32(right - center));
      }
    }

    // Ensure center bin always has weight >= 1.0 (the Python reference
    // upcasts to f64 inside max() and stores the f64 1.0 as f32 1.0).
    if (center < fftBins) {
      filterbank[m * fftBins + center] = Math.max(filterbank[m * fftBins + center], 1.0);
    }
  }

  return filterbank;
}

export function hzToMel(hz) {
  return fr32(fr32(2595) * fr32(Math.log10(fr32(1 + fr32(hz) / fr32(700)))));
}

export function melToHz(mel) {
  return fr32(fr32(700) * fr32(Math.pow(10, fr32(mel) / fr32(2595)) - 1));
}

export function resampleLinearForTesting(samples, fromRate, toRate) {
  return resampleLinear(samples, fromRate, toRate);
}

// Aggregator for cross-runtime golden-fixture parity tests
// (test/js/test-speaker-encoder-parity.js). Bundles the constants and
// internal helpers the test harness destructures, so callers see one
// stable shape rather than touching ten named imports.
export const _internalForTesting = {
  MEL_SAMPLE_RATE,
  MEL_N_FFT,
  MEL_HOP_LENGTH,
  MEL_N_MELS,
  MEL_FMIN,
  MEL_FMAX,
  hannWindow,
  createMelFilterbank,
  computeMelSpectrogram,
  resampleLinear,
  hzToMel,
  melToHz,
};
