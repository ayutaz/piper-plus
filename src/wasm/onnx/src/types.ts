/**
 * Type definitions for Piper ONNX Runtime
 */

export interface PiperModel {
  readonly path: string;
  readonly config: ModelConfig;
  readonly session?: any; // ort.InferenceSession
}

export interface ModelConfig {
  readonly sampleRate: number;
  readonly numSpeakers: number;
  readonly phonemeIdMap: Record<string, number>;
  readonly language: string;
  readonly espeak?: {
    voice: string;
  };
  readonly phonemeType?: string;
  readonly inference?: {
    noise_scale?: number;
    length_scale?: number;
    noise_w?: number;
  };
  readonly piperVersion?: string;
}

export interface SynthesisOptions {
  speakerId?: number;
  lengthScale?: number;
  noiseScale?: number;
  noiseW?: number;
}

export interface AudioConfig {
  sampleRate: number;
  channels: number;
  bitDepth: number;
}

export interface SynthesisResult {
  audio: Float32Array;
  sampleRate: number;
  duration: number;
}

export type ExecutionProvider = 'webgpu' | 'webgl' | 'wasm';

export interface RuntimeOptions {
  executionProviders?: ExecutionProvider[];
  wasmPaths?: {
    'ort-wasm.wasm'?: string;
    'ort-wasm-simd.wasm'?: string;
    'ort-wasm-threaded.wasm'?: string;
    'ort-wasm-simd-threaded.wasm'?: string;
  };
  numThreads?: number;
  graphOptimizationLevel?: 'disabled' | 'basic' | 'extended' | 'all';
  preferredBackend?: 'cpu' | 'webgl' | 'webgpu' | 'wasm' | 'auto';
  enableProfiling?: boolean;
  powerPreference?: 'low-power' | 'high-performance' | 'default';
}