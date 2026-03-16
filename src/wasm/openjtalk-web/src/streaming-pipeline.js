/**
 * StreamingTTSPipeline & supporting classes
 * Phase 3: ストリーミング再生
 */

// --- TextChunker ---

const ABBREVIATIONS = /(?:Mr|Dr|Mrs|Ms|Prof|Sr|Jr|St|Mt|Inc|Ltd|Corp|Co|vs|etc|Vol|Dept|Est|approx|Gen|Gov|Sgt|Cpl|Pvt|Capt|Lt|Col|Maj|Rev|Ph\.D)\./gi;

export class TextChunker {
  /**
   * Split text into sentence chunks.
   * @param {string} text
   * @param {string} lang - 'ja' or 'en'
   * @returns {string[]}
   */
  static split(text, lang) {
    if (!text) return [];

    if (lang === 'ja') {
      return TextChunker._splitJapanese(text);
    }
    return TextChunker._splitEnglish(text);
  }

  static _splitJapanese(text) {
    // Split on 。！？!? keeping the delimiter attached to the chunk
    const chunks = [];
    let current = '';
    for (let i = 0; i < text.length; i++) {
      current += text[i];
      if ('。！？!?'.includes(text[i])) {
        chunks.push(current);
        current = '';
      }
    }
    if (current) {
      chunks.push(current);
    }
    return chunks;
  }

  static _splitEnglish(text) {
    // Replace abbreviation periods with a placeholder to avoid splitting on them
    const placeholder = '\x00';
    const abbrPositions = [];
    const replaced = text.replace(ABBREVIATIONS, (match, offset) => {
      abbrPositions.push({ offset, match });
      // Replace the final period of the abbreviation with placeholder
      return match.slice(0, -1) + placeholder;
    });

    // Split on sentence-ending punctuation (. ! ?)
    const chunks = [];
    let current = '';
    for (let i = 0; i < replaced.length; i++) {
      current += replaced[i];
      if ('.!?'.includes(replaced[i])) {
        // Restore placeholders and push
        chunks.push(current.replaceAll(placeholder, '.'));
        current = '';
      }
    }
    if (current) {
      chunks.push(current.replaceAll(placeholder, '.'));
    }

    // Trim leading whitespace from chunks (except the first)
    return chunks.map((c, i) => i === 0 ? c : c.trimStart()).filter(c => c.length > 0);
  }
}

// --- RingBuffer ---

export class RingBuffer {
  /**
   * @param {number} capacity - Maximum number of items
   */
  constructor(capacity) {
    this._capacity = capacity;
    this._buffer = new Array(capacity);
    this._head = 0; // read position
    this._tail = 0; // write position
    this._count = 0;
  }

  /**
   * Add an item. If full, overwrite the oldest.
   * @param {Float32Array} item
   */
  enqueue(item) {
    if (this._count === this._capacity) {
      // Overwrite oldest: advance head
      this._buffer[this._tail] = item;
      this._tail = (this._tail + 1) % this._capacity;
      this._head = (this._head + 1) % this._capacity;
    } else {
      this._buffer[this._tail] = item;
      this._tail = (this._tail + 1) % this._capacity;
      this._count++;
    }
  }

  /**
   * Remove and return the oldest item, or null if empty.
   * @returns {Float32Array|null}
   */
  dequeue() {
    if (this._count === 0) return null;
    const item = this._buffer[this._head];
    this._buffer[this._head] = undefined;
    this._head = (this._head + 1) % this._capacity;
    this._count--;
    return item;
  }

  /**
   * @returns {number} Current number of items
   */
  size() {
    return this._count;
  }
}

// --- ChunkCrossfader ---

export class ChunkCrossfader {
  /**
   * @param {number} crossfadeMs - Crossfade duration in milliseconds
   * @param {number} sampleRate - Audio sample rate
   */
  constructor(crossfadeMs, sampleRate) {
    this._crossfadeMs = crossfadeMs;
    this._sampleRate = sampleRate;
    this._prevTail = null;
  }

  /**
   * Add a chunk and return the crossfaded result.
   * @param {Float32Array} chunk
   * @returns {Float32Array}
   */
  addChunk(chunk) {
    if (chunk.length === 0) {
      return new Float32Array(0);
    }

    const fadeLen = Math.ceil(this._sampleRate * this._crossfadeMs / 1000);

    if (this._prevTail === null || fadeLen === 0) {
      // First chunk or no crossfade: store tail and return a copy
      this._storeTail(chunk, fadeLen);
      return new Float32Array(chunk);
    }

    // Crossfade the overlap region
    const prev = this._prevTail;
    const actualFadeLen = Math.min(fadeLen, prev.length, chunk.length);
    const output = new Float32Array(chunk.length);

    const fadeDenom = actualFadeLen > 1 ? actualFadeLen - 1 : 1;
    for (let i = 0; i < actualFadeLen; i++) {
      const t = actualFadeLen === 1 ? 0.5 : i / fadeDenom;
      output[i] = prev[i] * (1 - t) + chunk[i] * t;
    }

    // Copy the rest of the chunk after the fade region
    for (let i = actualFadeLen; i < chunk.length; i++) {
      output[i] = chunk[i];
    }

    this._storeTail(chunk, fadeLen);
    return output;
  }

  /**
   * Store the tail of the chunk for next crossfade.
   * @param {Float32Array} chunk
   * @param {number} fadeLen
   */
  _storeTail(chunk, fadeLen) {
    if (fadeLen === 0 || chunk.length === 0) {
      this._prevTail = null;
      return;
    }
    const start = Math.max(0, chunk.length - fadeLen);
    this._prevTail = chunk.slice(start);
  }
}

// --- StreamingTTSPipeline ---

export class StreamingTTSPipeline {
  /**
   * @param {Object} opts
   * @param {function(string): Promise<number[]>} opts.phonemize
   * @param {function(number[]): Promise<Float32Array>} opts.synthesize
   * @param {function(Float32Array): void} opts.onAudioChunk
   */
  constructor({ phonemize, synthesize, onAudioChunk }) {
    if (typeof phonemize !== 'function') throw new TypeError('phonemize must be a function');
    if (typeof synthesize !== 'function') throw new TypeError('synthesize must be a function');
    if (typeof onAudioChunk !== 'function') throw new TypeError('onAudioChunk must be a function');
    this._phonemize = phonemize;
    this._synthesize = synthesize;
    this._onAudioChunk = onAudioChunk;
  }

  /**
   * Split text, then pipeline: phonemize chunk N+1 while synthesizing chunk N.
   * @param {string} text
   * @param {string} lang
   */
  async synthesizeAndPlay(text, lang) {
    const chunks = TextChunker.split(text, lang);
    if (chunks.length === 0) return;

    // Phonemize the first chunk
    let nextPhonemeIds = await this._phonemize(chunks[0]);

    for (let i = 0; i < chunks.length; i++) {
      const currentIds = nextPhonemeIds;

      // Pipeline: synthesize current chunk while phonemizing next chunk
      let synthesizePromise = this._synthesize(currentIds);
      let phonemizePromise = (i + 1 < chunks.length)
        ? this._phonemize(chunks[i + 1])
        : Promise.resolve(null);

      const [audio, nextIds] = await Promise.all([synthesizePromise, phonemizePromise]);

      this._onAudioChunk(audio);
      nextPhonemeIds = nextIds;
    }
  }
}
