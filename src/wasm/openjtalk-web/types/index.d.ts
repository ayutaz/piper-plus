// Type definitions for piper-plus
// Browser-based multilingual neural TTS with VITS

// ---------------------------------------------------------------------------
// Language type
// ---------------------------------------------------------------------------

/** Supported language codes. */
export type Language = 'ja' | 'en' | 'zh' | 'es' | 'fr' | 'pt' | 'sv';

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
  stage: 'model' | 'dict' | 'voice' | 'phonemizer' | 'ready' | 'init';
  progress: number;
  message: string;
}

/** Progress information emitted during model download. */
export interface ModelDownloadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

/** Progress information emitted during dictionary download. */
export interface DictDownloadProgress {
  phase: 'dict' | 'voice';
  file: string;
  loaded: number;
  total: number;
  overallPercent: number;
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
  /** OpenJTalk dictionary URL. */
  dictUrl?: string;
  /** HTS voice URL. */
  voiceUrl?: string;
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
// PiperPlus
// ---------------------------------------------------------------------------

/** High-level TTS API that orchestrates phonemization, ONNX inference, and audio output. */
export class PiperPlus {
  /** Use PiperPlus.initialize() instead. */
  private constructor();

  /**
   * Initialize PiperPlus. Downloads (and caches) the ONNX model, config,
   * OpenJTalk dictionary, and HTS voice, then creates an ONNX inference session.
   */
  static initialize(options: PiperPlusOptions): Promise<PiperPlus>;

  /** Synthesize speech from text. */
  synthesize(text: string, options?: SynthesizeOptions): Promise<AudioResult>;

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
// AudioResult
// ---------------------------------------------------------------------------

/** Wraps raw audio samples and provides playback, encoding, and download helpers. */
export class AudioResult {
  /**
   * @param samples - Audio sample data (range: -1.0 to 1.0)
   * @param sampleRate - Sample rate in Hz (default: 22050)
   */
  constructor(samples: Float32Array, sampleRate?: number);

  /** Audio sample data. */
  readonly samples: Float32Array;

  /** Sample rate in Hz. */
  readonly sampleRate: number;

  /** Duration of the audio in seconds. */
  readonly duration: number;

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

  /** Remove all cached models. */
  clearCache(): Promise<void>;
}

// ---------------------------------------------------------------------------
// DictManager
// ---------------------------------------------------------------------------

/** Options for the DictManager constructor. */
export interface DictManagerOptions {
  /** IndexedDB database name for caching. Default: 'piper-plus-dict'. */
  cachePrefix?: string;
}

/** Options for DictManager.loadDictionary(). */
export interface LoadDictionaryOptions {
  /** Custom tar.gz URL for the dictionary archive (default: GitHub Releases). */
  dictUrl?: string;
  /** URL for the HTS voice file. */
  voiceUrl?: string;
  /** Progress callback. */
  onProgress?: (info: DictDownloadProgress) => void;
}

/** Result returned by DictManager.resolveUrls(). */
export interface DictResolveResult {
  dictUrl: string;
  voiceUrl: string;
}

/** Result returned by DictManager.loadDictionary(). */
export interface DictLoadResult {
  dictFiles: Record<string, ArrayBuffer>;
  voiceData: ArrayBuffer;
}

/**
 * Download and cache OpenJTalk dictionary files from GitHub Releases
 * (same source as Rust/C#/C++ implementations) and HTS voice file.
 */
export class DictManager {
  constructor(options?: DictManagerOptions);

  /** Resolve dictionary and voice URLs without downloading. */
  resolveUrls(options?: { dictUrl?: string; voiceUrl?: string }): DictResolveResult;

  /** Download (or retrieve from cache) dictionary files and the HTS voice file. */
  loadDictionary(options?: LoadDictionaryOptions): Promise<DictLoadResult>;

  /** Check whether all dictionary files and the voice file are already cached. */
  isCached(): Promise<boolean>;

  /** Remove all cached dictionary and voice data. */
  clearCache(): Promise<void>;
}

// ---------------------------------------------------------------------------
// SimpleUnifiedPhonemizer
// ---------------------------------------------------------------------------

/** Deployment configuration for path resolution. */
export interface DeploymentConfig {
  isGitHubPages: boolean;
  basePath: string;
}

/** Constructor options for SimpleUnifiedPhonemizer. */
export interface SimpleUnifiedPhonemizerOptions {
  /** Pre-set phoneme_id_map from model config. */
  phonemeIdMap?: Record<string, number[]> | null;
  /** Deployment configuration for GitHub Pages path adjustments. */
  deploymentConfig?: DeploymentConfig;
}

/** OpenJTalk initialization config passed to initialize(). */
export interface OpenJTalkConfig {
  jsPath: string;
  wasmPath: string;
  dictPath: string;
  voicePath: string;
}

/** Phonemizer initialization config. */
export interface PhonemizerInitConfig {
  openjtalk?: OpenJTalkConfig;
}

/**
 * Unified phonemizer supporting Japanese (OpenJTalk), English (rule-based),
 * and character-based fallbacks for zh/es/fr/pt.
 */
export class SimpleUnifiedPhonemizer {
  constructor(options?: SimpleUnifiedPhonemizerOptions);

  /** Whether the phonemizer has been initialized. */
  readonly initialized: boolean;

  /** Initialize the phonemizer. */
  initialize(config: PhonemizerInitConfig): Promise<void>;

  /**
   * Convert text to phonemes.
   *
   * For ja: returns OpenJTalk full-context labels (string).
   * For en: returns IPA string.
   * For zh/es/fr/pt: returns phoneme ID array (number[]).
   *
   * @param text - Input text.
   * @param language - Language code. Omit for auto-detection.
   */
  textToPhonemes(text: string, language?: Language | null): Promise<string | number[]>;

  /**
   * Extract phoneme tokens from raw phonemizer output.
   *
   * For ja: extracts phonemes from OpenJTalk labels.
   * For en: extracts phonemes from IPA string.
   * For zh/es/fr/pt: passes through the phoneme ID array.
   */
  extractPhonemes(labels: string | number[], language?: Language): string[] | number[];

  /**
   * Set the phoneme_id_map from model config.
   * Required for zh/es/fr/pt fallback phonemization.
   */
  setPhonemeIdMap(phonemeIdMap: Record<string, number[]>): void;

  /**
   * Get the phoneme ID map for the specified language.
   * Returns null for Japanese (map comes from model config).
   */
  getPhonemeIdMap(language: Language): Record<string, number[]> | null;

  /**
   * Detect language from text.
   * Priority: JA (Hiragana/Katakana) > ZH (CJK without Kana) > EN (default).
   */
  detectLanguage(text: string): Language;

  /** Release resources (OpenJTalk WASM module). */
  dispose(): void;
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
