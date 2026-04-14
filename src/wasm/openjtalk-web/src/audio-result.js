/**
 * AudioResult - TTS output audio wrapper
 *
 * Wraps raw Float32Array samples from the ONNX inference pipeline and
 * provides convenience methods for playback, WAV encoding, and download.
 *
 * Browser-only: relies on AudioContext, Blob, and URL.createObjectURL.
 */

/** @type {AudioContext | null} */
let sharedAudioContext = null;

/**
 * Return a lazily-created AudioContext, reusing it across calls.
 * Creation is deferred until the first invocation so the context is
 * always constructed after a user interaction (required by browsers).
 * @returns {AudioContext}
 */
function getAudioContext() {
  if (!sharedAudioContext) {
    const AudioCtx = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!AudioCtx) {
      throw new Error('AudioContext is not available in this environment');
    }
    sharedAudioContext = new AudioCtx();
  }
  // Resume if the context was suspended (auto-play policy).
  if (sharedAudioContext.state === 'suspended') {
    void sharedAudioContext.resume().catch((err) => {
      if (typeof console !== 'undefined' && console.warn) {
        console.warn('[piper-plus] AudioContext.resume() failed:', err);
      }
    });
  }
  return sharedAudioContext;
}

/**
 * Encode a Float32Array of mono audio samples into a PCM 16-bit WAV
 * ArrayBuffer.
 *
 * @param {Float32Array} samples  - Audio samples in the range -1.0 to 1.0
 * @param {number}       sampleRate
 * @returns {ArrayBuffer}
 */
function encodeWav(samples, sampleRate) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const dataByteLength = samples.length * bytesPerSample;
  // 44 bytes: RIFF header (12) + fmt sub-chunk (24) + data sub-chunk header (8)
  const headerByteLength = 44;
  const buffer = new ArrayBuffer(headerByteLength + dataByteLength);
  const view = new DataView(buffer);

  // --- RIFF header ---
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataByteLength, true); // file size - 8
  writeString(view, 8, 'WAVE');

  // --- fmt sub-chunk ---
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);                              // sub-chunk size (PCM = 16)
  view.setUint16(20, 1, true);                               // audio format (1 = PCM)
  view.setUint16(22, numChannels, true);                     // number of channels
  view.setUint32(24, sampleRate, true);                      // sample rate
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true); // byte rate
  view.setUint16(32, numChannels * bytesPerSample, true);    // block align
  view.setUint16(34, bitsPerSample, true);                   // bits per sample

  // --- data sub-chunk ---
  writeString(view, 36, 'data');
  view.setUint32(40, dataByteLength, true);

  // Convert float32 [-1, 1] -> int16 [-32768, 32767]
  const offset = headerByteLength;
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    const int16 = clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF;
    view.setInt16(offset + i * bytesPerSample, int16, true);
  }

  return buffer;
}

/**
 * Write an ASCII string into a DataView at the given byte offset.
 * @param {DataView} view
 * @param {number}   offset
 * @param {string}   str
 */
function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

/**
 * Deep freeze a TimingResult object so callers cannot accidentally mutate it
 * via `result.timing.phonemes[0].start_ms = ...`. The freeze is shallow at the
 * outer object level plus one level into the `phonemes` array (since each
 * phoneme is a plain object with only primitive fields).
 * @param {object} timing
 * @returns {object}
 */
function deepFreezeTiming(timing) {
  if (timing && Array.isArray(timing.phonemes)) {
    for (const p of timing.phonemes) {
      Object.freeze(p);
    }
    Object.freeze(timing.phonemes);
  }
  return Object.freeze(timing);
}

export class AudioResult {
  /** @type {Float32Array} */
  #samples;
  /** @type {number} */
  #sampleRate;
  /** @type {object | null} Phoneme timing result (TimingResult from timing.js) */
  #timing;

  /**
   * @param {Float32Array} samples    - Audio sample data (range: -1.0 to 1.0)
   * @param {number}       [sampleRate=22050] - Sample rate in Hz
   * @param {object|null}  [timing=null] - Phoneme timing result (TimingResult) or null if unavailable
   */
  constructor(samples, sampleRate = 22050, timing = null) {
    if (!(samples instanceof Float32Array)) {
      throw new TypeError('samples must be a Float32Array');
    }
    if (typeof sampleRate !== 'number' || sampleRate <= 0) {
      throw new TypeError('sampleRate must be a positive number');
    }
    this.#samples = samples;
    this.#sampleRate = sampleRate;
    // Deep freeze the timing result to prevent accidental mutations.
    // Callers reading `result.timing` get a stable, immutable snapshot.
    this.#timing = timing != null ? deepFreezeTiming(timing) : null;
  }

  /** Audio sample data. */
  get samples() {
    return this.#samples;
  }

  /** Sample rate in Hz. */
  get sampleRate() {
    return this.#sampleRate;
  }

  /** Duration of the audio in seconds. */
  get duration() {
    return this.#samples.length / this.#sampleRate;
  }

  /**
   * Phoneme timing information, or null when the model does not output durations.
   * @returns {object|null}
   */
  get timing() {
    return this.#timing;
  }

  /**
   * Whether phoneme timing information is available for this result.
   * @returns {boolean}
   */
  get hasTimingInfo() {
    return this.#timing != null;
  }

  /**
   * Play the audio through the browser's audio output.
   *
   * The AudioContext is created lazily on the first call so it always
   * follows a user-interaction event (required by autoplay policies).
   *
   * @returns {Promise<void>} Resolves when playback finishes.
   */
  async play() {
    const ctx = getAudioContext();
    const audioBuffer = ctx.createBuffer(1, this.#samples.length, this.#sampleRate);
    audioBuffer.copyToChannel(this.#samples, 0);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    return new Promise((resolve) => {
      source.onended = () => resolve();
      source.start();
    });
  }

  /**
   * Generate a WAV Blob (audio/wav).
   * @returns {Blob}
   */
  toBlob() {
    const wavBuffer = this.toWav();
    return new Blob([wavBuffer], { type: 'audio/wav' });
  }

  /**
   * Generate a WAV ArrayBuffer (PCM 16-bit, mono).
   * Pure ArrayBuffer operation -- no AudioContext required.
   * @returns {ArrayBuffer}
   */
  toWav() {
    return encodeWav(this.#samples, this.#sampleRate);
  }

  /**
   * Trigger a file download of the audio as a WAV file.
   * @param {string} [filename='output.wav']
   */
  download(filename = 'output.wav') {
    const blob = this.toBlob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    // Clean up after a short delay so the browser has time to start the download.
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }
}
