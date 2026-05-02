// Type definitions for piper-plus
// Browser-based multilingual neural TTS with VITS

// ---------------------------------------------------------------------------
// Language type
// ---------------------------------------------------------------------------

/** Supported language codes. */
export type Language = 'ja' | 'en' | 'zh' | 'ko' | 'es' | 'fr' | 'pt' | 'sv';

// ---------------------------------------------------------------------------
// ModelConfig
// ---------------------------------------------------------------------------

/** Audio section of the model configuration. */
export interface ModelConfigAudio {
  sample_rate: number;
  quality?: string;
}

/** Inference parameters from the model configuration. */
export interface ModelConfigInference {
  noise_scale: number;
  length_scale: number;
  noise_w: number;
}

/** Model configuration loaded from the companion JSON file. */
export interface ModelConfig {
  audio: ModelConfigAudio;
  inference: ModelConfigInference;
  phoneme_id_map: Record<string, number[]>;
  phoneme_type?: string;
  phoneme_map?: Record<string, string>;
  num_symbols: number;
  num_speakers: number;
  num_languages?: number;
  speaker_id_map?: Record<string, number>;
  language_id_map?: Record<string, number>;
  prosody_num_symbols?: number;
  prosody_id_map?: Record<string, number[]>;
  dataset?: string;
  piper_version?: string;
  espeak?: { voice: string };
  language?: { code: string };
}

// ---------------------------------------------------------------------------
// Progress types
// ---------------------------------------------------------------------------

/** Progress information emitted during PiperPlus initialization. */
export interface ProgressInfo {
  stage: 'model' | 'phonemizer' | 'ready' | 'init';
  progress: number;
  message: string;
}

/** Progress information emitted during model download. */
export interface ModelDownloadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

// ---------------------------------------------------------------------------
// PiperPlus options
// ---------------------------------------------------------------------------

/** Options for PiperPlus.initialize(). */
export interface PiperPlusOptions {
  /** HuggingFace model name or direct URL to an ONNX file. */
  model: string;
  /** onnxruntime-web instance. When omitted, globalThis.ort is used. */
  ort?: any;
  /** Progress callback invoked during initialization. */
  onProgress?: (info: ProgressInfo) => void;
}

/** Options for PiperPlus.synthesize(). */
export interface SynthesizeOptions {
  /** Target language. Omit for auto-detection. */
  language?: Language;
  /** Controls speaker variation. Default: 0.667. */
  noiseScale?: number;
  /** Controls speech speed. Default: 1.0. */
  lengthScale?: number;
  /** Controls phoneme duration variation. Default: 0.8. */
  noiseW?: number;
}

/** Options for PiperPlus.synthesizeStreaming(). */
export interface StreamingSynthesizeOptions extends SynthesizeOptions {
  /** Called with each generated audio chunk. */
  onChunk?: (chunk: Float32Array) => void;
}

// ---------------------------------------------------------------------------
// Short-text mitigation helpers (Strategy A + B)
// ---------------------------------------------------------------------------

/**
 * Minimum phoneme ID count below which Strategy A padding is applied.
 * See docs/spec/short-text-contract.toml.
 */
export const MIN_PHONEME_IDS: number;

/**
 * Minimum body length (= phoneme IDs minus BOS/EOS) for Strategy A to
 * apply. Below this threshold pad-token audio dominates the actual
 * content (issue #356); the runtime emits raw VITS output instead.
 */
export const MIN_BODY_FOR_STRATEGY_A: number;

/**
 * Number of EOS frames retained by `trimPaddingByDurations`. Defaults
 * to 0 (drop the entire EOS) — see issue #356.
 */
export const TRIM_EOS_MAX_FRAMES: number;

/**
 * Default hop length when `config.json` does not declare
 * `audio.hop_size`. Used by `trimPaddingByDurations`.
 */
export const DEFAULT_HOP_SIZE: number;

/**
 * Strategy A: Pad short phoneme ID sequences with silence tokens.
 *
 * Inserts pause tokens (ID = 0) evenly after BOS and before EOS until
 * the sequence reaches MIN_PHONEME_IDS length. The result also carries
 * `frontPad` and `backPad` so the durations-based post-trim can locate
 * the padding precisely (added in 0.5.0; existing fields are unchanged).
 */
export function padPhonemeIds(
  phonemeIds: number[],
  prosodyFeatures: number[][] | null,
): {
  phonemeIds: number[];
  prosodyFeatures: number[][] | null;
  wasPadded: boolean;
  /** Pad tokens inserted after BOS (0 when wasPadded is false). */
  frontPad: number;
  /** Pad tokens inserted before EOS (0 when wasPadded is false). */
  backPad: number;
};

/**
 * Strategy A precise post-trim: drop padding-induced samples using the
 * model's `durations` output. Mirrors the cross-runtime contract — every
 * runtime trims by the same number of samples for the same inputs
 * (issue #356).
 *
 * Returns the input unchanged when arguments are inconsistent (null
 * `durations`, non-positive `hopSize`, or fewer durations than
 * `1 + frontPad + backPad + 1`).
 */
export function trimPaddingByDurations(
  audio: Float32Array,
  durations: ArrayLike<number> | null,
  frontPad: number,
  backPad: number,
  hopSize: number,
  eosMaxFrames?: number,
): Float32Array;

/**
 * Strategy A (post-step): Trim leading and trailing silence from audio
 * using a sliding RMS window. Used as a fallback when the model does
 * not expose a `durations` output.
 *
 * Keeps at least TRIM_MIN_SAMPLES (2205) to avoid producing empty audio.
 */
export function trimSilence(audio: Float32Array, windowSize?: number): Float32Array;

/**
 * Strategy B: Adjust noise scales for short inputs.
 *
 * For inputs shorter than MIN_PHONEME_IDS, attenuate noiseScale and
 * noiseW proportionally while keeping lengthScale unchanged.
 */
export function adjustScalesForShortInput(
  phonemeCount: number,
  noiseScale: number,
  noiseW: number,
): { noiseScale: number; noiseW: number };

// ---------------------------------------------------------------------------
// PiperPlus
// ---------------------------------------------------------------------------

/** High-level TTS API that orchestrates phonemization, ONNX inference, and audio output. */
export class PiperPlus {
  /** Use PiperPlus.initialize() instead. */
  private constructor();

  /**
   * Initialize PiperPlus. Downloads (and caches) the ONNX model and config,
   * initializes the WASM phonemizer, then creates an ONNX inference session.
   */
  static initialize(options: PiperPlusOptions): Promise<PiperPlus>;

  /** Synthesize speech from text. */
  synthesize(text: string, options?: SynthesizeOptions): Promise<AudioResult>;

  /**
   * Synthesize speech with voice cloning from a speaker embedding.
   * @param text - Text to synthesize.
   * @param speakerEmbedding - Speaker embedding from SpeakerEncoder.encode().
   * @param options - Synthesis options (same as synthesize).
   */
  synthesizeWithVoiceCloning(text: string, speakerEmbedding: Float32Array, options?: SynthesizeOptions): Promise<AudioResult>;

  /** Streaming synthesis -- splits text into sentences and invokes onChunk for each chunk. */
  synthesizeStreaming(text: string, options?: StreamingSynthesizeOptions): Promise<void>;

  /** Release all held resources (ONNX session, phonemizer, etc.). */
  dispose(): void;

  /** Whether the instance has been fully initialized. */
  readonly isInitialized: boolean;

  /** Model configuration (config.json contents), or null before initialization. */
  readonly config: ModelConfig | null;
}

// ---------------------------------------------------------------------------
// Phoneme timing
// ---------------------------------------------------------------------------

/** Timing information for a single phoneme. */
export interface PhonemeTimingInfo {
  /** Phoneme token (default: `ph_0`, `ph_1`, ... indices). */
  phoneme: string;
  /** Start time in milliseconds from the beginning of the utterance. */
  start_ms: number;
  /** End time in milliseconds from the beginning of the utterance. */
  end_ms: number;
  /** Duration in milliseconds. */
  duration_ms: number;
}

/** Complete timing result for a synthesized utterance. */
export interface TimingResult {
  phonemes: PhonemeTimingInfo[];
  total_duration_ms: number;
  sample_rate: number;
}

/**
 * Convert ONNX duration tensor output to phoneme timing information.
 *
 * @param durations - Frame counts from the ONNX `durations` output tensor
 * @param sampleRate - Audio sample rate (e.g. 22050)
 * @param hopLength - STFT hop length (default: 256 for VITS medium)
 * @param phonemeTokens - Optional phoneme names; defaults to `ph_0`, `ph_1`, …
 * @throws {TypeError} If sampleRate or hopLength are not finite positive numbers
 * @throws {RangeError} If phonemeTokens length differs from durations length
 *
 * @example
 * const durations = new Float32Array([10, 15, 12]);
 * const timing = durationsToTiming(durations, 22050);
 * // timing.phonemes[0] = { phoneme: "ph_0", start_ms: 0, end_ms: 116.1, duration_ms: 116.1 }
 *
 * @example
 * // With explicit phoneme tokens
 * const timing = durationsToTiming(durations, 22050, 256, ["a", "e", "i"]);
 * // timing.phonemes[0].phoneme === "a"
 */
export function durationsToTiming(
  durations: Float32Array | number[],
  sampleRate: number,
  hopLength?: number,
  phonemeTokens?: string[] | null,
): TimingResult;

/** Serialize a TimingResult to pretty-printed JSON (matches Rust/Go output). */
export function timingToJson(result: TimingResult): string;

/** Serialize a TimingResult to compact single-line JSON. */
export function timingToJsonCompact(result: TimingResult): string;

/** Serialize a TimingResult to TSV (matches Rust/Go output). */
export function timingToTsv(result: TimingResult): string;

/** Serialize a TimingResult to SRT subtitle format (matches Rust output). */
export function timingToSrt(result: TimingResult): string;

/**
 * STFT hop length used by VITS medium-quality models.
 */
export const DEFAULT_HOP_LENGTH: number;

/**
 * Build a reverse lookup map from phoneme ID to phoneme token string.
 *
 * Given a model config's `phoneme_id_map` (phoneme string → list of IDs),
 * returns a flat `{ id: string }` map for efficient reverse lookup. When
 * multiple IDs point to the same phoneme, the first occurrence wins.
 *
 * PUA characters (U+E000–U+F8FF) without an explicit `puaToMultiChar`
 * mapping are rendered as `U+XXXX`.
 *
 * @param phonemeIdMap - Model config's phoneme_id_map
 * @param puaToMultiChar - Optional PUA char → multi-char name mapping
 * @returns Flat ID → display name map
 *
 * @example
 * const map = buildPhonemeIdToTokenMap({ "a": [7], "k": [10] });
 * // { 7: "a", 10: "k" }
 */
export function buildPhonemeIdToTokenMap(
  phonemeIdMap: Record<string, number[]> | null | undefined,
  puaToMultiChar?: Record<string, string> | null,
): Record<number, string>;

// ---------------------------------------------------------------------------
// AudioResult
// ---------------------------------------------------------------------------

/** Wraps raw audio samples and provides playback, encoding, and download helpers. */
export class AudioResult {
  /**
   * @param samples - Audio sample data (range: -1.0 to 1.0)
   * @param sampleRate - Sample rate in Hz (default: 22050)
   * @param timing - Phoneme timing info, or null if unavailable
   */
  constructor(samples: Float32Array, sampleRate?: number, timing?: TimingResult | null);

  /** Audio sample data. */
  readonly samples: Float32Array;

  /** Sample rate in Hz. */
  readonly sampleRate: number;

  /** Duration of the audio in seconds. */
  readonly duration: number;

  /**
   * Phoneme timing information for lip-sync / subtitle / karaoke use cases.
   * Returns `null` if the ONNX model does not output a `durations` tensor.
   *
   * The object is deeply frozen — attempts to mutate any field throw
   * `TypeError` in strict mode.
   *
   * @example
   * const result = await piper.synthesize("Hello");
   * if (result.hasTimingInfo) {
   *   for (const p of result.timing.phonemes) {
   *     console.log(`${p.phoneme}: ${p.start_ms}ms–${p.end_ms}ms`);
   *   }
   * }
   */
  readonly timing: TimingResult | null;

  /** Whether phoneme timing information is available for this result. */
  readonly hasTimingInfo: boolean;

  /** Play the audio through the browser's audio output. Resolves when playback finishes. */
  play(): Promise<void>;

  /** Generate a WAV Blob (audio/wav). */
  toBlob(): Blob;

  /** Generate a WAV ArrayBuffer (PCM 16-bit, mono). */
  toWav(): ArrayBuffer;

  /** Trigger a file download of the audio as a WAV file. */
  download(filename?: string): void;
}

// ---------------------------------------------------------------------------
// ModelManager
// ---------------------------------------------------------------------------

/** Options for the ModelManager constructor. */
export interface ModelManagerOptions {
  /** IndexedDB database name for caching. Default: 'piper-plus-models'. */
  cachePrefix?: string;
}

// ---------------------------------------------------------------------------
// SpeakerEncoder
// ---------------------------------------------------------------------------

/** Options for SpeakerEncoder.initialize(). */
export interface SpeakerEncoderOptions {
  /** URL to the speaker encoder ONNX model. */
  modelUrl: string;
  /** onnxruntime-web instance (defaults to globalThis.ort). */
  ort?: any;
}

/**
 * Speaker encoder for voice cloning.
 * Loads an ECAPA-TDNN ONNX model and extracts speaker embeddings from audio.
 */
export class SpeakerEncoder {
  private constructor();

  /** Initialize the speaker encoder with an ONNX model. */
  static initialize(options: SpeakerEncoderOptions): Promise<SpeakerEncoder>;

  /**
   * Encode audio into a speaker embedding vector.
   * @param audio - AudioBuffer (first channel, auto-resampled) or Float32Array (mono 16kHz).
   * @param sampleRate - Sample rate when audio is Float32Array (default: 16000).
   * @returns Speaker embedding (typically 256-d Float32Array).
   */
  encode(audio: AudioBuffer | Float32Array, sampleRate?: number): Promise<Float32Array>;

  /** Release resources held by this encoder. */
  dispose(): void;
}

// ---------------------------------------------------------------------------
// ModelManager
// ---------------------------------------------------------------------------

/** Result returned by ModelManager.loadModel() and getFromCache(). */
export interface ModelLoadResult {
  modelData: ArrayBuffer;
  config: ModelConfig;
}

/** Download and cache ONNX models from HuggingFace. */
export class ModelManager {
  constructor(options?: ModelManagerOptions);

  /**
   * Load a model and its config, using the IndexedDB cache when available.
   *
   * @param modelNameOrUrl - Registry shortcut, HuggingFace repo name, or direct URL.
   * @param options - Optional settings including progress callback.
   */
  loadModel(
    modelNameOrUrl: string,
    options?: { onProgress?: (info: ModelDownloadProgress) => void },
  ): Promise<ModelLoadResult>;

  /** Retrieve a model from the IndexedDB cache. Returns null if not cached. */
  getFromCache(key: string): Promise<ModelLoadResult | null>;

  /**
   * Retrieve a dictionary from the IndexedDB cache.
   * @param key - Cache key (e.g. 'naist-jdic-v1').
   * @returns The dictionary data, or null if not cached.
   */
  getDictionaryFromCache(key: string): Promise<ArrayBuffer | null>;

  /**
   * Save a dictionary to the IndexedDB cache.
   * @param key - Cache key (e.g. 'naist-jdic-v1').
   * @param data - Dictionary binary data.
   */
  cacheDictionary(key: string, data: ArrayBuffer): Promise<void>;

  /**
   * Fetch a dictionary from a URL, cache it in IndexedDB, and return the data.
   * If the dictionary is already cached, returns the cached version.
   * @param url - URL to fetch the dictionary from.
   * @param key - Cache key (e.g. 'naist-jdic-v1').
   * @param options - Optional settings including progress callback.
   */
  fetchAndCacheDictionary(
    url: string,
    key: string,
    options?: { onProgress?: (info: ModelDownloadProgress) => void },
  ): Promise<ArrayBuffer>;

  /**
   * Resolve a model identifier to concrete URLs for the ONNX model and its
   * companion config JSON.
   *
   * Accepted formats:
   *   - Registry shortcut: "css10"
   *   - HuggingFace repo:  "ayousanz/piper-plus-css10-ja-6lang"
   *   - Direct URL:        "https://example.com/model.onnx"
   *
   * @param modelNameOrUrl - Registry shortcut, HuggingFace repo, or direct URL.
   */
  resolveUrls(modelNameOrUrl: string): Promise<{
    modelUrl: string;
    configUrl: string;
    configFallbackUrl: string | null;
    cacheKey: string;
  }>;

  /** Remove all cached models and dictionaries. */
  clearCache(): Promise<void>;
}


// ---------------------------------------------------------------------------
// WebGPUSessionManager
// ---------------------------------------------------------------------------

/** Constructor options for WebGPUSessionManager. */
export interface WebGPUSessionManagerOptions {
  /** onnxruntime-web module. */
  ort: any;
  /** navigator.gpu object, or undefined if WebGPU is not available. */
  gpu?: GPU;
}

/** Manages ONNX inference sessions with WebGPU/WASM fallback. */
export class WebGPUSessionManager {
  constructor(options: WebGPUSessionManagerOptions);

  /** The currently active execution provider ('webgpu' or 'wasm'), or null before session creation. */
  currentProvider: string | null;

  /**
   * Create an InferenceSession, trying providers in fallback order:
   * webgpu -> wasm.
   */
  createSession(modelPath: string): Promise<any>;

  /** Check if the GPU can handle a model of the given size. */
  checkGPUCapacity(modelSizeBytes: number): Promise<boolean>;
}

// ---------------------------------------------------------------------------
// StreamingTTSPipeline
// ---------------------------------------------------------------------------

/** Constructor options for StreamingTTSPipeline. */
export interface StreamingTTSPipelineOptions {
  /** Function that converts a text chunk to phoneme IDs. */
  phonemize: (text: string) => Promise<number[]>;
  /** Function that converts phoneme IDs to audio samples. */
  synthesize: (phonemeIds: number[]) => Promise<Float32Array>;
  /** Callback invoked with each generated audio chunk. */
  onAudioChunk: (chunk: Float32Array) => void;
}

/** Streaming TTS pipeline that splits text into sentences and pipelines phonemization with synthesis. */
export class StreamingTTSPipeline {
  constructor(options: StreamingTTSPipelineOptions);

  /** Split text, then pipeline: phonemize chunk N+1 while synthesizing chunk N. */
  synthesizeAndPlay(text: string, lang: Language | string): Promise<void>;
}

// ---------------------------------------------------------------------------
// TextChunker
// ---------------------------------------------------------------------------

/** Splits text into sentence-level chunks for streaming synthesis. */
export class TextChunker {
  /** Split text into sentence chunks based on language-specific rules. */
  static split(text: string, lang: Language | string): string[];
}

// ---------------------------------------------------------------------------
// RingBuffer
// ---------------------------------------------------------------------------

/** Fixed-capacity ring buffer that overwrites the oldest entry when full. */
export class RingBuffer {
  constructor(capacity: number);

  /** Add an item. If full, overwrites the oldest. */
  enqueue(item: Float32Array): void;

  /** Remove and return the oldest item, or null if empty. */
  dequeue(): Float32Array | null;

  /** Current number of items in the buffer. */
  size(): number;
}

// ---------------------------------------------------------------------------
// ChunkCrossfader
// ---------------------------------------------------------------------------

/** Applies crossfade between consecutive audio chunks for smooth transitions. */
export class ChunkCrossfader {
  /**
   * @param crossfadeMs - Crossfade duration in milliseconds.
   * @param sampleRate - Audio sample rate.
   */
  constructor(crossfadeMs: number, sampleRate: number);

  /** Add a chunk and return the crossfaded result. */
  addChunk(chunk: Float32Array): Float32Array;
}

// ---------------------------------------------------------------------------
// CacheManager
// ---------------------------------------------------------------------------

/** Cache entry metadata. */
export interface CacheSetMeta {
  version: string;
  priority?: 'high' | 'medium' | 'low';
}

/** A cached entry returned by CacheManager.get(). */
export interface CacheEntry {
  key: string;
  data: ArrayBuffer;
  version: string;
  priority: string;
  storedAt: number;
}

/** Cache usage statistics. */
export interface CacheUsage {
  used: number;
  quota: number;
}

/** Options for the CacheManager.create() factory. */
export interface CacheManagerCreateOptions {
  dbName?: string;
  dbVersion?: number;
  storeName?: string;
}

/** Options for the CacheManager constructor. */
export interface CacheManagerConstructorOptions {
  dbFactory: () => IDBDatabase;
}

/** IndexedDB-backed cache with version management and eviction. */
export class CacheManager {
  /** Async factory for real IndexedDB usage. */
  static create(options?: CacheManagerCreateOptions): Promise<CacheManager>;

  constructor(options: CacheManagerConstructorOptions);

  /** Store data under a key with metadata. */
  set(key: string, data: ArrayBuffer, meta?: CacheSetMeta): Promise<void>;

  /** Retrieve a cached entry. Returns the entry or null. */
  get(key: string): Promise<CacheEntry | null>;

  /** Remove a single key. */
  delete(key: string): Promise<void>;

  /** Returns true if the key exists and its stored version matches. */
  isValid(key: string, version: string): Promise<boolean>;

  /** Returns usage statistics: total bytes used and quota. */
  getUsage(): Promise<CacheUsage>;

  /** Remove all cached entries. */
  clear(): Promise<void>;

  /** Return an array of all stored keys. */
  getKeys(): Promise<string[]>;

  /**
   * If the cache contains the key at the given version, return cached data.
   * Otherwise call fetcherFn(), cache the result, and return it.
   */
  getOrFetch(
    key: string,
    version: string,
    fetcherFn: () => Promise<ArrayBuffer>,
    options?: { priority?: 'high' | 'medium' | 'low' },
  ): Promise<ArrayBuffer>;
}

// ---------------------------------------------------------------------------
// AudioBackendFactory & backends
// ---------------------------------------------------------------------------

/** Options for AudioBackendFactory.create(). */
export interface AudioBackendCreateOptions {
  /** URL to audio-worklet-processor.js. Default: './audio-worklet-processor.js'. */
  workletUrl?: string;
  /** Output sample rate. Default: 48000. */
  sampleRate?: number;
}

/** Common interface for all audio playback backends. */
export interface AudioBackend {
  /** Backend type identifier. */
  readonly type: 'audioworklet' | 'scriptprocessor' | 'htmlaudio';
  /** Play a full audio buffer. */
  play(audioData: Float32Array): Promise<void>;
  /** Push an audio chunk for streaming playback. */
  pushChunk(chunk: Float32Array): void;
  /** Stop current playback. */
  stop(): void;
  /** Release all resources. */
  dispose(): void | Promise<void>;
}

/** Creates the best available audio playback backend with automatic fallback. */
export class AudioBackendFactory {
  /**
   * Create the best available audio backend.
   * Fallback chain: AudioWorklet -> ScriptProcessor -> HTMLAudioElement.
   */
  static create(options?: AudioBackendCreateOptions): Promise<AudioBackend>;
}

// ---------------------------------------------------------------------------
// TypedArrayPool
// ---------------------------------------------------------------------------

/** Supported typed-array type names. */
export type TypedArrayType =
  | 'float32'
  | 'float64'
  | 'int8'
  | 'int16'
  | 'int32'
  | 'uint8'
  | 'uint16'
  | 'uint32'
  | 'bigint64'
  | 'biguint64';

/** Union of all TypedArray constructors. */
export type TypedArray =
  | Float32Array
  | Float64Array
  | Int8Array
  | Int16Array
  | Int32Array
  | Uint8Array
  | Uint16Array
  | Uint32Array
  | BigInt64Array
  | BigUint64Array;

/** Pool statistics. */
export interface TypedArrayPoolStats {
  hits: number;
  misses: number;
  evictions: number;
  totalPools: number;
}

/** Options for the TypedArrayPool constructor. */
export interface TypedArrayPoolOptions {
  /** Maximum age in milliseconds before an entry is eligible for cleanup. Default: 60000. */
  maxAgeMs?: number;
}

/** Reusable typed-array memory pool. */
export class TypedArrayPool {
  static MAX_POOL_SIZE: number;

  constructor(options?: TypedArrayPoolOptions);

  /** Return a typed array of the requested type and length. Reuses a pooled buffer when available. */
  getArray(type: TypedArrayType, length: number): TypedArray;

  /** Return an array to the pool for future reuse. The array is zero-cleared before storing. */
  returnArray(type: TypedArrayType, length: number, array: TypedArray): void;

  /** Remove all pool entries older than maxAgeMs. */
  cleanup(): void;

  /** Return pool statistics. */
  getStats(): TypedArrayPoolStats;
}
