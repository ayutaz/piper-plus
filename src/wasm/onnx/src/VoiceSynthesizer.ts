/**
 * Voice Synthesizer
 * 
 * Converts phoneme IDs to audio waveforms using ONNX inference
 */

import * as ort from 'onnxruntime-web';
import { PiperModel, SynthesisOptions, SynthesisResult } from './types';

export class VoiceSynthesizer {
  readonly model: PiperModel;
  private session: ort.InferenceSession;
  
  constructor(model: PiperModel) {
    this.model = model;
    this.session = model.session!;
  }
  
  async initialize(): Promise<void> {
    // Warm up the model with a dummy inference
    try {
      const dummyInput = new Int32Array([0, 1, 2, 3, 0]); // Simple phoneme sequence
      await this.synthesize(Array.from(dummyInput), {});
      console.log('Voice synthesizer initialized');
    } catch (error) {
      console.warn('Warm-up inference failed:', error);
    }
  }
  
  /**
   * Synthesize audio from phoneme IDs
   */
  async synthesize(
    phonemeIds: number[], 
    options: SynthesisOptions = {}
  ): Promise<SynthesisResult> {
    const startTime = performance.now();
    
    try {
      // Prepare input tensors
      const feeds = await this.prepareInputs(phonemeIds, options);
      
      // Run inference
      const results = await this.session.run(feeds);
      
      // Extract audio from output
      const audio = this.extractAudio(results);
      
      const inferenceTime = performance.now() - startTime;
      const duration = audio.length / this.model.config.sampleRate;
      const rtf = duration * 1000 / inferenceTime; // Real-time factor
      
      console.log(`Synthesis completed: ${duration.toFixed(2)}s audio in ${inferenceTime.toFixed(0)}ms (RTF: ${rtf.toFixed(1)}x)`);
      
      return {
        audio,
        sampleRate: this.model.config.sampleRate,
        duration
      };
      
    } catch (error) {
      console.error('Synthesis failed:', error);
      throw new Error(`Voice synthesis failed: ${error}`);
    }
  }
  
  /**
   * Prepare input tensors for inference
   */
  private async prepareInputs(
    phonemeIds: number[], 
    options: SynthesisOptions
  ): Promise<Record<string, ort.Tensor>> {
    const feeds: Record<string, ort.Tensor> = {};
    
    // Main input: phoneme IDs
    // Shape: [batch_size, sequence_length]
    const inputData = new BigInt64Array(phonemeIds.map(id => BigInt(id)));
    feeds['input'] = new ort.Tensor('int64', inputData, [1, phonemeIds.length]);
    
    // Input lengths (for batching)
    if (this.session.inputNames.includes('input_lengths')) {
      const lengthData = new BigInt64Array([BigInt(phonemeIds.length)]);
      feeds['input_lengths'] = new ort.Tensor('int64', lengthData, [1]);
    }
    
    // Speaker ID (for multi-speaker models)
    if (this.session.inputNames.includes('sid') && this.model.config.numSpeakers > 1) {
      const speakerId = options.speakerId || 0;
      const sidData = new BigInt64Array([BigInt(speakerId)]);
      feeds['sid'] = new ort.Tensor('int64', sidData, [1]);
    }
    
    // Length scale (controls speech speed)
    if (this.session.inputNames.includes('length_scale')) {
      const lengthScale = options.lengthScale || this.model.config.inference?.length_scale || 1.0;
      const scaleData = new Float32Array([lengthScale]);
      feeds['length_scale'] = new ort.Tensor('float32', scaleData, [1]);
    }
    
    // Noise scale (controls variability)
    if (this.session.inputNames.includes('noise_scale')) {
      const noiseScale = options.noiseScale || this.model.config.inference?.noise_scale || 0.667;
      const noiseData = new Float32Array([noiseScale]);
      feeds['noise_scale'] = new ort.Tensor('float32', noiseData, [1]);
    }
    
    // Noise weight
    if (this.session.inputNames.includes('noise_w')) {
      const noiseW = options.noiseW || this.model.config.inference?.noise_w || 0.8;
      const noiseWData = new Float32Array([noiseW]);
      feeds['noise_w'] = new ort.Tensor('float32', noiseWData, [1]);
    }
    
    return feeds;
  }
  
  /**
   * Extract audio waveform from model output
   */
  private extractAudio(results: ort.InferenceSession.OnnxValueMapType): Float32Array {
    // Get output tensor
    const outputTensor = results['output'] || results['wav'] || results['audio'];
    
    if (!outputTensor) {
      throw new Error('No audio output found in model results');
    }
    
    // Extract audio data
    let audioData: Float32Array;
    
    // In test environment, data might be directly accessible
    if (outputTensor.data instanceof Float32Array) {
      audioData = outputTensor.data as Float32Array;
    } else if (outputTensor instanceof Float32Array) {
      // Handle case where outputTensor is the data itself
      audioData = outputTensor;
    } else {
      // Convert to Float32Array if needed
      audioData = new Float32Array(outputTensor.data as any);
    }
    
    // Handle batch dimension if present
    // Expected shape: [batch_size, num_samples] or [batch_size, 1, num_samples]
    const shape = outputTensor.dims;
    // Note: We process normalization after handling dimensions
    
    // Normalize audio to [-1, 1] range if needed
    const maxValue = Math.max(...Array.from(audioData).map(Math.abs));
    if (maxValue > 1.0) {
      const scale = 1.0 / maxValue;
      const normalizedData = new Float32Array(audioData.length);
      for (let i = 0; i < audioData.length; i++) {
        normalizedData[i] = audioData[i] * scale;
      }
      return normalizedData;
    }
    
    return audioData;
  }
  
  /**
   * Dispose of resources
   */
  async dispose(): Promise<void> {
    // Session disposal is handled by the model loader
    console.log('Voice synthesizer disposed');
  }
}