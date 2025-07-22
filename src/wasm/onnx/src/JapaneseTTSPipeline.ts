/**
 * Japanese TTS Pipeline Integration
 * 
 * Integrates MeCab, OpenJTalk, and ONNX Runtime for complete TTS
 */

import { PiperONNXRuntime } from './PiperONNXRuntime';
import { StreamingSynthesizer } from './StreamingSynthesizer';
import { RuntimeOptions, SynthesisOptions, SynthesisResult } from './types';

// Import types for MeCab and OpenJTalk wrappers
interface MeCabWrapper {
  initialize(options?: any): Promise<void>;
  parse(text: string): string;
  dispose(): void;
}

interface OpenJTalkWrapper {
  initialize(options?: any): Promise<void>;
  processText(mecabOutput: string): string;
  processToPUA(mecabOutput: string): string;
  dispose(): void;
}

interface JapaneseTTSOptions extends RuntimeOptions {
  mecabWasmPath?: string;
  mecabDataPath?: string;
  openjtalkWasmPath?: string;
  modelPath: string;
  modelConfigPath?: string;
  enableStreaming?: boolean;
  streamingChunkSize?: number;
}

export class JapaneseTTSPipeline {
  private runtime: PiperONNXRuntime;
  private streamingSynthesizer?: StreamingSynthesizer;
  private mecab?: MeCabWrapper;
  private openjtalk?: OpenJTalkWrapper;
  private initialized = false;
  private options: JapaneseTTSOptions;

  constructor(options: JapaneseTTSOptions) {
    this.options = options;
    this.runtime = new PiperONNXRuntime(options);
  }

  /**
   * Initialize the complete TTS pipeline
   */
  async initialize(): Promise<void> {
    try {
      console.log('Initializing Japanese TTS Pipeline...');

      // Step 1: Initialize MeCab
      // @ts-ignore - Dynamic import of JavaScript module
      const { MeCabWrapper } = await import('../../mecab/dist/mecab-wrapper.js');
      this.mecab = new MeCabWrapper();
      await this.mecab!.initialize({
        wasmPath: this.options.mecabWasmPath || '../../mecab/dist/mecab_wasm.wasm',
        dataPath: this.options.mecabDataPath || '../../mecab/dist/mecab_wasm.data'
      });
      console.log('MeCab initialized');

      // Step 2: Initialize OpenJTalk
      // @ts-ignore - Dynamic import of JavaScript module
      const { OpenJTalkWrapper } = await import('../../openjtalk/dist/openjtalk-wrapper.js');
      this.openjtalk = new OpenJTalkWrapper();
      await this.openjtalk!.initialize({
        wasmPath: this.options.openjtalkWasmPath || '../../openjtalk/dist/openjtalk_wasm.wasm'
      });
      console.log('OpenJTalk initialized');

      // Step 3: Initialize ONNX Runtime
      await this.runtime.initialize(this.options.modelPath, this.options.modelConfigPath);
      console.log('ONNX Runtime initialized');

      // Step 4: Initialize streaming if enabled
      if (this.options.enableStreaming) {
        // TODO: Implement proper streaming support
        console.log('Streaming support is not yet implemented');
      }

      this.initialized = true;
      console.log('Japanese TTS Pipeline initialized successfully');

    } catch (error) {
      console.error('Failed to initialize Japanese TTS Pipeline:', error);
      throw error;
    }
  }

  /**
   * Synthesize speech from Japanese text
   */
  async synthesize(text: string, options: SynthesisOptions = {}): Promise<SynthesisResult> {
    if (!this.initialized) {
      throw new Error('Pipeline not initialized. Call initialize() first.');
    }

    if (!this.mecab || !this.openjtalk) {
      throw new Error('Text processing modules not initialized');
    }

    try {
      console.log('Processing text:', text);

      // Step 1: Morphological analysis with MeCab
      const mecabOutput = this.mecab.parse(text);
      console.log('MeCab output:', mecabOutput);

      // Step 2: Convert to PUA-encoded phonemes with OpenJTalk
      const puaPhonemes = this.openjtalk.processToPUA(mecabOutput);
      console.log('PUA phonemes:', puaPhonemes);

      // Step 3: Synthesize with ONNX Runtime
      const result = await this.runtime.synthesizeFromPUA(puaPhonemes, options);
      console.log('Synthesis complete:', {
        duration: result.duration,
        sampleRate: result.sampleRate,
        audioLength: result.audio.length
      });

      return result;

    } catch (error) {
      console.error('Synthesis error:', error);
      throw error;
    }
  }

  /**
   * Stream synthesized speech from Japanese text
   */
  async *synthesizeStream(
    text: string, 
    options: SynthesisOptions = {}
  ): AsyncGenerator<Float32Array, void, unknown> {
    if (!this.initialized || !this.streamingSynthesizer) {
      throw new Error('Streaming not initialized. Enable streaming in options.');
    }

    if (!this.mecab || !this.openjtalk) {
      throw new Error('Text processing modules not initialized');
    }

    // Process text to PUA phonemes
    const mecabOutput = this.mecab.parse(text);
    const puaPhonemes = this.openjtalk.processToPUA(mecabOutput);

    // Stream synthesis
    // TODO: Implement streaming synthesis
    const result = await this.runtime.synthesizeFromPUA(puaPhonemes, options);
    yield result.audio;
  }

  /**
   * Convenience method to synthesize and play audio
   */
  async synthesizeAndPlay(text: string, options: SynthesisOptions = {}): Promise<void> {
    const result = await this.synthesize(text, options);
    await this.runtime.play(result);
  }

  /**
   * Stop audio playback
   */
  stop(): void {
    this.runtime.stop();
  }

  /**
   * Get phoneme sequence for debugging
   */
  async getPhonemes(text: string): Promise<{
    mecabOutput: string;
    phonemes: string;
    puaEncoded: string;
  }> {
    if (!this.mecab || !this.openjtalk) {
      throw new Error('Text processing modules not initialized');
    }

    const mecabOutput = this.mecab.parse(text);
    const phonemes = this.openjtalk.processText(mecabOutput);
    const puaEncoded = this.openjtalk.processToPUA(mecabOutput);

    return {
      mecabOutput,
      phonemes,
      puaEncoded
    };
  }

  /**
   * Get pipeline information
   */
  getInfo(): Record<string, any> {
    const info: Record<string, any> = {
      initialized: this.initialized,
      ...this.runtime.getInfo()
    };

    if (this.initialized) {
      info.pipeline = {
        mecab: 'initialized',
        openjtalk: 'initialized',
        streaming: this.options.enableStreaming ? 'enabled' : 'disabled'
      };
    }

    return info;
  }

  /**
   * Get memory statistics
   */
  getMemoryStats() {
    return this.runtime.getMemoryStats();
  }

  /**
   * Cleanup resources
   */
  async dispose(): Promise<void> {
    if (this.streamingSynthesizer) {
      this.streamingSynthesizer.dispose();
    }

    if (this.mecab) {
      this.mecab.dispose();
    }

    if (this.openjtalk) {
      this.openjtalk.dispose();
    }

    await this.runtime.dispose();
    this.initialized = false;
  }
}

// Export convenience factory function
export async function createJapaneseTTS(options: JapaneseTTSOptions): Promise<JapaneseTTSPipeline> {
  const pipeline = new JapaneseTTSPipeline(options);
  await pipeline.initialize();
  return pipeline;
}