/**
 * Piper ONNX Runtime - Main Class
 * 
 * Manages ONNX Runtime initialization and provides high-level TTS API
 */

import * as ort from 'onnxruntime-web';
import { ModelLoader } from './ModelLoader';
import { VoiceSynthesizer } from './VoiceSynthesizer';
import { AudioPlayer } from './AudioPlayer';
import { MemoryManager, ResourceTracker } from './MemoryManager';
import { WebGLOptimizer } from './WebGLOptimizer';
import { RuntimeOptions, SynthesisOptions, SynthesisResult } from './types';

export class PiperONNXRuntime {
  private modelLoader: ModelLoader;
  private synthesizer: VoiceSynthesizer | null = null;
  private audioPlayer: AudioPlayer;
  private memoryManager: MemoryManager;
  private resourceTracker: ResourceTracker;
  private webglOptimizer: WebGLOptimizer;
  private initialized = false;
  
  constructor(options: RuntimeOptions = {}) {
    this.webglOptimizer = new WebGLOptimizer();
    this.setupONNXRuntime(options);
    this.modelLoader = new ModelLoader();
    this.audioPlayer = new AudioPlayer();
    this.memoryManager = new MemoryManager();
    this.resourceTracker = this.memoryManager.createResourceTracker();
    
    // Setup memory management
    this.setupMemoryManagement();
  }
  
  private setupONNXRuntime(options: RuntimeOptions) {
    // Configure ONNX Runtime Web
    const env = ort.env;
    
    // Set WASM paths if provided
    if (options.wasmPaths) {
      env.wasm.wasmPaths = options.wasmPaths as any;
    }
    
    // Set number of threads
    if (options.numThreads) {
      env.wasm.numThreads = options.numThreads;
    }
    
    // Enable debug mode in development
    if (process.env.NODE_ENV === 'development') {
      env.logLevel = 'verbose';
      env.debug = true;
    }
    
    // Configure execution providers with WebGL optimization
    const optimizedProviders = this.webglOptimizer.getOptimalExecutionProviders({
      preferredBackend: options.preferredBackend,
      enableProfiling: options.enableProfiling,
      powerPreference: options.powerPreference
    });
    
    console.log(`ONNX Runtime configured with providers: ${optimizedProviders.join(', ')}`);
    
    // Log recommendations
    const recommendations = this.webglOptimizer.getRecommendations();
    if (recommendations.length > 0) {
      console.log('Performance recommendations:', recommendations);
    }
  }
  
  /**
   * Initialize the runtime with a model
   */
  async initialize(modelPath: string, configPath?: string): Promise<void> {
    try {
      console.log('Initializing Piper ONNX Runtime...');
      
      // Load model
      const model = await this.modelLoader.load(modelPath, configPath);
      
      // Create synthesizer
      this.synthesizer = new VoiceSynthesizer(model);
      await this.synthesizer.initialize();
      
      // Initialize audio player
      await this.audioPlayer.initialize();
      
      this.initialized = true;
      console.log('Piper ONNX Runtime initialized successfully');
      
    } catch (error) {
      console.error('Failed to initialize Piper ONNX Runtime:', error);
      throw error;
    }
  }
  
  /**
   * Synthesize speech from phoneme IDs
   */
  async synthesizeFromPhonemes(
    phonemeIds: number[], 
    options: SynthesisOptions = {}
  ): Promise<SynthesisResult> {
    if (!this.initialized || !this.synthesizer) {
      throw new Error('Runtime not initialized. Call initialize() first.');
    }
    
    return await this.synthesizer.synthesize(phonemeIds, options);
  }
  
  /**
   * Synthesize speech from PUA-encoded string
   */
  async synthesizeFromPUA(
    puaString: string, 
    options: SynthesisOptions = {}
  ): Promise<SynthesisResult> {
    if (!this.initialized || !this.synthesizer) {
      throw new Error('Runtime not initialized. Call initialize() first.');
    }
    
    // Convert PUA string to phoneme IDs
    const phonemeIds = this.puaToPhonemeIds(puaString);
    
    return await this.synthesizeFromPhonemes(phonemeIds, options);
  }
  
  /**
   * Play synthesized audio
   */
  async play(audio: Float32Array | SynthesisResult): Promise<void> {
    if (audio instanceof Float32Array) {
      const sampleRate = this.synthesizer?.model.config.sampleRate || 22050;
      await this.audioPlayer.play(audio, sampleRate);
    } else {
      await this.audioPlayer.play(audio.audio, audio.sampleRate);
    }
  }
  
  /**
   * Stop audio playback
   */
  stop(): void {
    this.audioPlayer.stop();
  }
  
  /**
   * Convert PUA string to phoneme IDs
   */
  private puaToPhonemeIds(puaString: string): number[] {
    if (!this.synthesizer) {
      throw new Error('Synthesizer not initialized');
    }
    
    const phonemeIdMap = this.synthesizer.model.config.phonemeIdMap;
    const phonemeIds: number[] = [];
    
    // Process each character
    for (const char of puaString) {
      const codePoint = char.charCodeAt(0);
      
      // Check if it's in PUA range
      if (codePoint >= 0xE000 && codePoint <= 0xF8FF) {
        // Map PUA code to phoneme ID
        const phonemeIndex = codePoint - 0xE000;
        if (phonemeIndex < Object.keys(phonemeIdMap).length) {
          phonemeIds.push(phonemeIndex);
        }
      } else {
        // Handle special characters
        switch (char) {
          case ' ':
            phonemeIds.push(phonemeIdMap['_'] || 0); // Silence
            break;
          case '.':
          case '。':
            phonemeIds.push(phonemeIdMap['_'] || 0); // Pause
            phonemeIds.push(phonemeIdMap['_'] || 0);
            break;
          default:
            // Skip unknown characters
            console.warn(`Unknown character in PUA string: ${char}`);
        }
      }
    }
    
    return phonemeIds;
  }
  
  /**
   * Get runtime information
   */
  getInfo(): Record<string, any> {
    return {
      initialized: this.initialized,
      modelLoaded: this.synthesizer !== null,
      onnxVersion: (ort.env.versions as any).onnxruntime || ort.env.versions.common,
      webAssemblySupported: typeof WebAssembly !== 'undefined',
      webGPUSupported: 'gpu' in navigator,
      audioContextState: this.audioPlayer.getState()
    };
  }
  
  /**
   * Setup memory management
   */
  private setupMemoryManagement(): void {
    // Register cleanup callbacks
    this.memoryManager.registerCleanupCallback(async () => {
      // Clear model cache
      this.modelLoader.clearCache();
      
      // Force garbage collection if available
      if (typeof gc !== 'undefined') {
        gc();
      }
    });
    
    // Set memory warning handler
    this.memoryManager.onMemoryWarning((stats) => {
      console.warn('Memory warning:', {
        used: this.memoryManager.formatBytes(stats.usedJSHeapSize),
        total: this.memoryManager.formatBytes(stats.totalJSHeapSize),
        limit: this.memoryManager.formatBytes(stats.jsHeapSizeLimit)
      });
    });
    
    // Start monitoring in production
    if (process.env.NODE_ENV === 'production') {
      this.memoryManager.startMonitoring();
    }
  }
  
  /**
   * Get memory statistics
   */
  getMemoryStats() {
    return this.memoryManager.getMemoryStats();
  }
  
  /**
   * Perform manual memory cleanup
   */
  async cleanupMemory(): Promise<void> {
    await this.memoryManager.performCleanup();
  }
  
  /**
   * Cleanup resources
   */
  async dispose(): Promise<void> {
    this.stop();
    
    // Stop memory monitoring
    this.memoryManager.stopMonitoring();
    
    // Dispose tracked resources
    await this.resourceTracker.disposeAll();
    
    if (this.synthesizer) {
      await this.synthesizer.dispose();
      this.synthesizer = null;
    }
    
    if (this.audioPlayer) {
      this.audioPlayer.dispose();
    }
    
    this.initialized = false;
  }
}