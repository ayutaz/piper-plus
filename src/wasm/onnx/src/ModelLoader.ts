/**
 * Model Loader for Piper TTS Models
 * 
 * Handles loading and caching of ONNX models and their configurations
 */

import * as ort from 'onnxruntime-web';
import { PiperModel, ModelConfig } from './types';
import { RetryHandler } from './RetryHandler';
import { ErrorHandler, ErrorType } from './ErrorHandler';

export class ModelLoader {
  private modelCache = new Map<string, PiperModel>();
  private retryHandler = new RetryHandler();
  private errorHandler = new ErrorHandler();
  
  /**
   * Load a Piper model from URL
   */
  async load(modelPath: string, configPath?: string): Promise<PiperModel> {
    // Check cache
    if (this.modelCache.has(modelPath)) {
      console.log(`Model loaded from cache: ${modelPath}`);
      return this.modelCache.get(modelPath)!;
    }
    
    try {
      console.log(`Loading model: ${modelPath}`);
      
      // Auto-detect config path if not provided
      if (!configPath) {
        // Try both .json and .onnx.json patterns
        const jsonPath = modelPath.replace('.onnx', '.json');
        const onnxJsonPath = modelPath + '.json';
        
        // Check which one exists
        try {
          const response = await fetch(onnxJsonPath);
          if (response.ok) {
            configPath = onnxJsonPath;
          } else {
            configPath = jsonPath;
          }
        } catch {
          configPath = jsonPath;
        }
      }
      
      // Load model configuration with retry
      const config = await this.retryHandler.execute(
        () => this.loadConfig(configPath!),
        {
          maxRetries: 3,
          onRetry: (error, attempt) => {
            console.log(`Retrying config load (attempt ${attempt})...`);
          }
        }
      );
      
      // Create ONNX session with retry
      const sessionOptions: ort.InferenceSession.SessionOptions = {
        executionProviders: this.getExecutionProviders(),
        graphOptimizationLevel: 'all',
        enableCpuMemArena: true,
        enableMemPattern: true,
        executionMode: 'sequential',
        logId: 'piper-tts',
        logSeverityLevel: 3
      };
      
      const session = await this.retryHandler.execute(
        () => ort.InferenceSession.create(modelPath, sessionOptions),
        {
          maxRetries: 2,
          initialDelay: 2000,
          onRetry: (error, attempt) => {
            console.log(`Retrying model load (attempt ${attempt})...`);
            // Clear any partial state
            if (typeof gc !== 'undefined') gc();
          }
        }
      );
      
      // Validate model
      this.validateModel(session, config);
      
      // Create model object
      const model: PiperModel = {
        path: modelPath,
        config,
        session
      };
      
      // Cache model
      this.modelCache.set(modelPath, model);
      
      console.log(`Model loaded successfully: ${config.language} (${config.numSpeakers} speakers)`);
      return model;
      
    } catch (error) {
      const piperError = this.errorHandler.handleError(error as Error, {
        type: ErrorType.MODEL_LOADING,
        operation: 'ModelLoader.load',
        details: { modelPath, configPath }
      });
      throw piperError;
    }
  }
  
  /**
   * Load model configuration
   */
  private async loadConfig(configPath: string): Promise<ModelConfig> {
    try {
      const response = await fetch(configPath);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const configData = await response.json();
      
      // Validate and normalize Piper config format
      const config: ModelConfig = {
        sampleRate: configData.audio?.sample_rate || 22050,
        numSpeakers: configData.num_speakers || 1,
        phonemeIdMap: this.buildPhonemeIdMap(configData),
        language: configData.language?.code || configData.espeak?.voice || 'ja',
        espeak: configData.espeak,
        phonemeType: configData.phoneme_type,
        inference: configData.inference,
        piperVersion: configData.piper_version
      };
      
      // Log config details for debugging
      console.log(`Loaded config: ${config.language}, phoneme_type: ${config.phonemeType}, version: ${config.piperVersion}`);
      
      return config;
      
    } catch (error) {
      console.warn(`Failed to load config from ${configPath}, using defaults`);
      
      // Return default config for Japanese
      return {
        sampleRate: 22050,
        numSpeakers: 1,
        phonemeIdMap: this.getDefaultJapanesePhonemeMap(),
        language: 'ja',
        phonemeType: 'openjtalk'
      };
    }
  }
  
  /**
   * Build phoneme to ID mapping
   */
  private buildPhonemeIdMap(configData: any): Record<string, number> {
    const phonemeIdMap: Record<string, number> = {};
    
    if (configData.phoneme_id_map) {
      // Piper format: phoneme_id_map has arrays with IDs
      for (const [phoneme, idArray] of Object.entries(configData.phoneme_id_map)) {
        // Extract the first ID from the array
        const id = Array.isArray(idArray) ? idArray[0] : idArray;
        phonemeIdMap[phoneme] = id as number;
      }
    } else if (configData.phonemes) {
      // Build mapping from phoneme list
      configData.phonemes.forEach((phoneme: string, index: number) => {
        phonemeIdMap[phoneme] = index;
      });
    } else {
      // Use default Japanese mapping
      return this.getDefaultJapanesePhonemeMap();
    }
    
    return phonemeIdMap;
  }
  
  /**
   * Get default Japanese phoneme mapping
   */
  private getDefaultJapanesePhonemeMap(): Record<string, number> {
    const phonemes = [
      '_', // 0: silence
      'a', 'i', 'u', 'e', 'o',
      'ka', 'ki', 'ku', 'ke', 'ko',
      'ga', 'gi', 'gu', 'ge', 'go',
      'sa', 'shi', 'su', 'se', 'so',
      'za', 'ji', 'zu', 'ze', 'zo',
      'ta', 'chi', 'tsu', 'te', 'to',
      'da', 'de', 'do',
      'na', 'ni', 'nu', 'ne', 'no',
      'ha', 'hi', 'fu', 'he', 'ho',
      'ba', 'bi', 'bu', 'be', 'bo',
      'pa', 'pi', 'pu', 'pe', 'po',
      'ma', 'mi', 'mu', 'me', 'mo',
      'ya', 'yu', 'yo',
      'ra', 'ri', 'ru', 're', 'ro',
      'wa', 'wo', 'n',
      'kya', 'kyu', 'kyo',
      'gya', 'gyu', 'gyo',
      'sha', 'shu', 'sho',
      'ja', 'ju', 'jo',
      'cha', 'chu', 'cho',
      'nya', 'nyu', 'nyo',
      'hya', 'hyu', 'hyo',
      'bya', 'byu', 'byo',
      'pya', 'pyu', 'pyo',
      'mya', 'myu', 'myo',
      'rya', 'ryu', 'ryo',
      'q', // glottal stop
      'N', // moraic nasal
      'cl', // closure
      'pau' // pause
    ];
    
    const map: Record<string, number> = {};
    phonemes.forEach((phoneme, index) => {
      map[phoneme] = index;
    });
    
    return map;
  }
  
  /**
   * Get execution providers based on availability
   */
  private getExecutionProviders(): string[] {
    const providers: string[] = [];
    
    // Check WebGPU support
    if ('gpu' in navigator) {
      providers.push('webgpu');
    }
    
    // Always include WebGL and WASM as fallbacks
    providers.push('webgl');
    providers.push('wasm');
    
    return providers;
  }
  
  /**
   * Validate loaded model
   */
  private validateModel(session: ort.InferenceSession, config: ModelConfig): void {
    // Check input names
    const inputNames = session.inputNames;
    if (!inputNames.includes('input')) {
      throw new Error('Model missing required input: "input"');
    }
    
    // Check output names
    const outputNames = session.outputNames;
    if (!outputNames.includes('output')) {
      throw new Error('Model missing required output: "output"');
    }
    
    console.log('Model validation passed');
  }
  
  /**
   * Clear model cache
   */
  clearCache(): void {
    this.modelCache.clear();
  }
  
  /**
   * Get cached model
   */
  getCached(modelPath: string): PiperModel | undefined {
    return this.modelCache.get(modelPath);
  }
}