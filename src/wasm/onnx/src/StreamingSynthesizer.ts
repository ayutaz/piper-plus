/**
 * Streaming Voice Synthesizer
 * 
 * Enables real-time streaming TTS by processing text in chunks
 */

import * as ort from 'onnxruntime-web';
import { PiperModel, SynthesisOptions } from './types';
import { VoiceSynthesizer } from './VoiceSynthesizer';
import { MemoryManager } from './MemoryManager';

export interface StreamingOptions extends SynthesisOptions {
  chunkSize?: number;  // Number of phonemes per chunk
  bufferSize?: number; // Number of chunks to buffer ahead
  onChunk?: (chunk: Float32Array, chunkIndex: number) => void;
  memoryManager?: MemoryManager;
}

export interface StreamingResult {
  audioStream: ReadableStream<Float32Array>;
  sampleRate: number;
  cancel: () => void;
}

export class StreamingSynthesizer {
  private synthesizer: VoiceSynthesizer;
  private isStreaming: boolean = false;
  private abortController: AbortController | null = null;
  
  constructor(model: PiperModel) {
    this.synthesizer = new VoiceSynthesizer(model);
  }
  
  async initialize(): Promise<void> {
    await this.synthesizer.initialize();
  }
  
  /**
   * Stream audio synthesis from phoneme IDs
   */
  async streamSynthesize(
    phonemeIds: number[], 
    options: StreamingOptions = {}
  ): Promise<StreamingResult> {
    const {
      chunkSize = 50,  // Process 50 phonemes at a time
      bufferSize = 3,   // Buffer 3 chunks ahead
      onChunk,
      ...synthesisOptions
    } = options;
    
    // Create abort controller for cancellation
    this.abortController = new AbortController();
    const signal = this.abortController.signal;
    
    // Create audio stream
    const audioStream = new ReadableStream<Float32Array>({
      start: async (controller) => {
        this.isStreaming = true;
        
        try {
          // Split phonemes into chunks
          const chunks = this.createChunks(phonemeIds, chunkSize);
          const audioBuffer: Float32Array[] = [];
          
          // Process chunks
          for (let i = 0; i < chunks.length; i++) {
            if (signal.aborted) {
              controller.close();
              return;
            }
            
            // Check memory pressure before processing
            if (options.memoryManager && options.memoryManager.isMemoryPressureHigh()) {
              console.warn('High memory pressure detected, performing cleanup...');
              await options.memoryManager.performCleanup();
              
              // Small delay to allow memory to settle
              await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            const chunk = chunks[i];
            
            // Add silence between chunks if not first/last
            const paddedChunk = this.addChunkPadding(chunk, i, chunks.length);
            
            // Synthesize chunk
            const result = await this.synthesizer.synthesize(paddedChunk, synthesisOptions);
            const audioChunk = this.trimSilence(result.audio, i, chunks.length);
            
            // Buffer management
            audioBuffer.push(audioChunk);
            
            // Stream when buffer is full or last chunk
            if (audioBuffer.length >= bufferSize || i === chunks.length - 1) {
              const combinedAudio = this.combineAudioChunks(audioBuffer);
              controller.enqueue(combinedAudio);
              
              // Callback for progress tracking
              if (onChunk) {
                onChunk(combinedAudio, i);
              }
              
              // Clear buffer to free memory
              audioBuffer.length = 0;
              
              // Explicitly nullify references to help GC
              audioBuffer.forEach((_, idx) => audioBuffer[idx] = null as any);
            }
            
            // Yield to prevent blocking
            await this.yieldToMain();
          }
          
          controller.close();
        } catch (error) {
          controller.error(error);
        } finally {
          this.isStreaming = false;
          this.abortController = null;
        }
      },
      
      cancel: () => {
        this.cancelStream();
      }
    });
    
    return {
      audioStream,
      sampleRate: this.synthesizer.model.config.sampleRate,
      cancel: () => this.cancelStream()
    };
  }
  
  /**
   * Create chunks from phoneme IDs
   */
  private createChunks(phonemeIds: number[], chunkSize: number): number[][] {
    const chunks: number[][] = [];
    
    for (let i = 0; i < phonemeIds.length; i += chunkSize) {
      const chunk = phonemeIds.slice(i, i + chunkSize);
      chunks.push(chunk);
    }
    
    return chunks;
  }
  
  /**
   * Add padding/silence tokens to chunks for smooth transitions
   */
  private addChunkPadding(chunk: number[], index: number, totalChunks: number): number[] {
    const silenceId = 0; // Assuming 0 is silence/pad token
    const padSize = 2;
    
    // First chunk: add padding at end
    if (index === 0 && totalChunks > 1) {
      return [...chunk, ...Array(padSize).fill(silenceId)];
    }
    
    // Middle chunks: add padding at both ends
    if (index > 0 && index < totalChunks - 1) {
      return [
        ...Array(padSize).fill(silenceId),
        ...chunk,
        ...Array(padSize).fill(silenceId)
      ];
    }
    
    // Last chunk: add padding at start
    if (index === totalChunks - 1 && totalChunks > 1) {
      return [...Array(padSize).fill(silenceId), ...chunk];
    }
    
    // Single chunk: no padding
    return chunk;
  }
  
  /**
   * Trim silence from audio chunks for smooth concatenation
   */
  private trimSilence(audio: Float32Array, index: number, totalChunks: number): Float32Array {
    const trimSamples = Math.floor(this.synthesizer.model.config.sampleRate * 0.02); // 20ms
    
    // Don't trim single chunk
    if (totalChunks === 1) {
      return audio;
    }
    
    // First chunk: trim end
    if (index === 0) {
      return audio.slice(0, -trimSamples);
    }
    
    // Middle chunks: trim both ends
    if (index < totalChunks - 1) {
      return audio.slice(trimSamples, -trimSamples);
    }
    
    // Last chunk: trim start
    return audio.slice(trimSamples);
  }
  
  /**
   * Combine audio chunks with crossfade
   */
  private combineAudioChunks(chunks: Float32Array[]): Float32Array {
    if (chunks.length === 0) {
      return new Float32Array(0);
    }
    
    if (chunks.length === 1) {
      return chunks[0];
    }
    
    // Calculate total length
    const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const combined = new Float32Array(totalLength);
    
    let offset = 0;
    for (const chunk of chunks) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    
    return combined;
  }
  
  /**
   * Yield control back to main thread
   */
  private async yieldToMain(): Promise<void> {
    return new Promise(resolve => {
      setTimeout(resolve, 0);
    });
  }
  
  /**
   * Cancel ongoing stream
   */
  private cancelStream(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isStreaming = false;
  }
  
  /**
   * Check if currently streaming
   */
  isActive(): boolean {
    return this.isStreaming;
  }
  
  /**
   * Dispose of resources
   */
  async dispose(): Promise<void> {
    this.cancelStream();
    await this.synthesizer.dispose();
  }
}