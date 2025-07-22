/**
 * Unit tests for ModelLoader
 */

import { ModelLoader } from '../src/ModelLoader';
import * as ort from 'onnxruntime-web';

// Mock onnxruntime-web
jest.mock('onnxruntime-web', () => ({
  InferenceSession: {
    create: jest.fn()
  },
  env: {
    wasm: {},
    versions: { common: '1.17.0' }
  }
}));

// Mock fetch
global.fetch = jest.fn();

describe('ModelLoader', () => {
  let modelLoader: ModelLoader;
  
  beforeEach(() => {
    modelLoader = new ModelLoader();
    jest.clearAllMocks();
  });

  describe('load', () => {
    const mockModelPath = 'https://example.com/model.onnx';
    const mockConfigPath = 'https://example.com/model.json';
    
    const mockSession = {
      inputNames: ['input'],
      outputNames: ['output']
    };
    
    const mockConfig = {
      audio: { sample_rate: 22050 },
      num_speakers: 1,
      language: { code: 'ja' },
      phonemes: ['_', 'a', 'i', 'u', 'e', 'o']
    };

    beforeEach(() => {
      (ort.InferenceSession.create as jest.Mock).mockResolvedValue(mockSession);
    });

    test('should load model successfully', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      const model = await modelLoader.load(mockModelPath);
      
      expect(model).toBeDefined();
      expect(model.path).toBe(mockModelPath);
      expect(model.config.sampleRate).toBe(22050);
      expect(model.config.numSpeakers).toBe(1);
      expect(model.config.language).toBe('ja');
      expect(model.session).toBe(mockSession);
    });

    test('should use cached model on second load', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      const model1 = await modelLoader.load(mockModelPath);
      const model2 = await modelLoader.load(mockModelPath);
      
      expect(model1).toBe(model2);
      expect(ort.InferenceSession.create).toHaveBeenCalledTimes(1);
    });

    test('should handle missing config gracefully', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Not found'));

      const model = await modelLoader.load(mockModelPath);
      
      expect(model.config.language).toBe('ja');
      expect(model.config.sampleRate).toBe(22050);
      expect(Object.keys(model.config.phonemeIdMap).length).toBeGreaterThan(0);
    });

    test('should validate model has required inputs/outputs', async () => {
      const invalidSession = {
        inputNames: ['wrong'],
        outputNames: ['wrong']
      };
      
      (ort.InferenceSession.create as jest.Mock).mockResolvedValueOnce(invalidSession);
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      await expect(modelLoader.load(mockModelPath)).rejects.toThrow('Model missing required input');
    });

    test('should build phoneme ID map from config', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      const model = await modelLoader.load(mockModelPath);
      
      expect(model.config.phonemeIdMap['_']).toBe(0);
      expect(model.config.phonemeIdMap['a']).toBe(1);
      expect(model.config.phonemeIdMap['i']).toBe(2);
    });

    test('should detect execution providers', async () => {
      // Mock navigator.gpu
      Object.defineProperty(navigator, 'gpu', {
        value: {},
        configurable: true
      });

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      await modelLoader.load(mockModelPath);
      
      const sessionOptions = (ort.InferenceSession.create as jest.Mock).mock.calls[0][1];
      expect(sessionOptions.executionProviders).toContain('webgpu');
      expect(sessionOptions.executionProviders).toContain('webgl');
      expect(sessionOptions.executionProviders).toContain('wasm');
    });
  });

  describe('clearCache', () => {
    test('should clear model cache', async () => {
      const mockSession = {
        inputNames: ['input'],
        outputNames: ['output']
      };
      
      (ort.InferenceSession.create as jest.Mock).mockResolvedValue(mockSession);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ phonemes: [] })
      });

      const modelPath = 'test.onnx';
      await modelLoader.load(modelPath);
      
      expect(modelLoader.getCached(modelPath)).toBeDefined();
      
      modelLoader.clearCache();
      
      expect(modelLoader.getCached(modelPath)).toBeUndefined();
    });
  });
});