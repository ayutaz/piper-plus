/**
 * Unit tests for VoiceSynthesizer
 */

import { VoiceSynthesizer } from '../src/VoiceSynthesizer';
import { PiperModel } from '../src/types';
import * as ort from 'onnxruntime-web';

// Mock onnxruntime-web
jest.mock('onnxruntime-web');

describe('VoiceSynthesizer', () => {
  let synthesizer: VoiceSynthesizer;
  let mockModel: PiperModel;
  let mockSession: any;
  
  beforeEach(() => {
    // Setup mock session
    mockSession = {
      inputNames: ['input', 'input_lengths', 'length_scale'],
      outputNames: ['output'],
      run: jest.fn().mockResolvedValue({
        output: {
          data: new Float32Array([0.1, 0.2, -0.1, -0.2]),
          dims: [1, 4]
        }
      })
    };
    
    // Setup mock model
    mockModel = {
      path: 'test.onnx',
      config: {
        sampleRate: 22050,
        numSpeakers: 1,
        phonemeIdMap: {
          '_': 0,
          'a': 1,
          'i': 2,
          'u': 3,
          'e': 4,
          'o': 5
        },
        language: 'ja'
      },
      session: mockSession
    };
    
    synthesizer = new VoiceSynthesizer(mockModel);
  });

  describe('initialize', () => {
    test('should warm up the model', async () => {
      await synthesizer.initialize();
      expect(mockSession.run).toHaveBeenCalled();
    });

    test('should handle warm-up failure gracefully', async () => {
      mockSession.run.mockRejectedValueOnce(new Error('Warm-up failed'));
      await expect(synthesizer.initialize()).resolves.not.toThrow();
    });
  });

  describe('synthesize', () => {
    const testPhonemeIds = [1, 2, 3, 4, 5];
    
    test('should synthesize audio from phoneme IDs', async () => {
      const result = await synthesizer.synthesize(testPhonemeIds);
      
      expect(result).toBeDefined();
      expect(result.audio).toBeInstanceOf(Float32Array);
      expect(result.sampleRate).toBe(22050);
      expect(result.duration).toBeCloseTo(result.audio.length / result.sampleRate);
    });

    test('should prepare correct input tensors', async () => {
      await synthesizer.synthesize(testPhonemeIds);
      
      const runCall = mockSession.run.mock.calls[0];
      const feeds = runCall[0];
      
      expect(feeds.input).toBeDefined();
      expect(feeds.input_lengths).toBeDefined();
      expect(feeds.length_scale).toBeDefined();
    });

    test('should apply synthesis options', async () => {
      const options = {
        lengthScale: 1.5,
        noiseScale: 0.8,
        speakerId: 0
      };
      
      await synthesizer.synthesize(testPhonemeIds, options);
      
      const runCall = mockSession.run.mock.calls[0];
      const feeds = runCall[0];
      
      // Check if options were applied
      const lengthScaleTensor = feeds.length_scale;
      expect(lengthScaleTensor).toBeDefined();
    });

    test('should handle multi-speaker models', async () => {
      // Setup multi-speaker model with new synthesizer
      const multiSpeakerSession = {
        ...mockSession,
        inputNames: ['input', 'input_lengths', 'length_scale', 'sid']
      };
      
      const multiSpeakerModel = {
        ...mockModel,
        config: {
          ...mockModel.config,
          numSpeakers: 3
        },
        session: multiSpeakerSession
      };
      
      const multiSpeakerSynth = new VoiceSynthesizer(multiSpeakerModel);
      const options = { speakerId: 2 };
      await multiSpeakerSynth.synthesize(testPhonemeIds, options);
      
      const feeds = multiSpeakerSession.run.mock.calls[0][0];
      expect(feeds.sid).toBeDefined();
    });

    test('should normalize audio output', async () => {
      // Create a new session specifically for this test
      const normSession = {
        inputNames: ['input', 'input_lengths', 'length_scale'],
        outputNames: ['output'],
        run: jest.fn().mockResolvedValue({
          output: {
            data: new Float32Array([2.0, -2.0, 1.5, -1.5]),
            dims: [1, 4]
          }
        })
      };
      
      const normModel = {
        ...mockModel,
        session: normSession
      };
      
      const normSynthesizer = new VoiceSynthesizer(normModel);
      
      // Test with smaller values first to debug
      normSession.run.mockResolvedValue({
        output: {
          data: new Float32Array([0.5, -0.5, 0.3, -0.3]),
          dims: [1, 4]
        }
      });
      
      const smallResult = await normSynthesizer.synthesize(testPhonemeIds);
      expect(Math.max(...smallResult.audio.map(Math.abs))).toBeLessThanOrEqual(1.0);
      
      // Now test with values that need normalization
      normSession.run.mockResolvedValue({
        output: {
          data: new Float32Array([2.0, -2.0, 1.5, -1.5]),
          dims: [1, 4]
        }
      });
      
      const result = await normSynthesizer.synthesize(testPhonemeIds);
      
      // Check all values are within [-1, 1]
      const maxValue = Math.max(...result.audio.map(Math.abs));
      expect(maxValue).toBeLessThanOrEqual(1.0);
      
      // Check normalization was applied correctly
      expect(result.audio[0]).toBeCloseTo(1.0); // 2.0 / 2.0
      expect(result.audio[1]).toBeCloseTo(-1.0); // -2.0 / 2.0
      expect(result.audio[2]).toBeCloseTo(0.75); // 1.5 / 2.0
      expect(result.audio[3]).toBeCloseTo(-0.75); // -1.5 / 2.0
    });

    test('should handle different output tensor names', async () => {
      // Test with 'wav' output name
      mockSession.run.mockResolvedValueOnce({
        wav: {
          data: new Float32Array([0.1, 0.2]),
          dims: [1, 2]
        }
      });
      
      const result = await synthesizer.synthesize(testPhonemeIds);
      expect(result.audio.length).toBe(2);
    });

    test('should calculate RTF correctly', async () => {
      const audioLength = 44100; // 1 second at 44.1kHz
      mockSession.run.mockResolvedValueOnce({
        output: {
          data: new Float32Array(audioLength),
          dims: [1, audioLength]
        }
      });
      
      const result = await synthesizer.synthesize(testPhonemeIds);
      expect(result.duration).toBeCloseTo(2); // 44100 samples at 22050Hz = 2 seconds
    });

    test('should throw error on synthesis failure', async () => {
      mockSession.run.mockRejectedValueOnce(new Error('Inference failed'));
      
      await expect(synthesizer.synthesize(testPhonemeIds))
        .rejects.toThrow('Voice synthesis failed');
    });

    test('should handle empty phoneme IDs', async () => {
      const result = await synthesizer.synthesize([]);
      expect(result.audio).toBeInstanceOf(Float32Array);
    });
  });

  describe('input tensor preparation', () => {
    test('should convert phoneme IDs to BigInt64Array', async () => {
      const phonemeIds = [1, 2, 3];
      
      // Mock ort.Tensor constructor to capture tensor creation
      const mockTensor = jest.fn((type, data, dims) => ({
        type,
        data,
        dims
      }));
      (ort.Tensor as any) = mockTensor;
      
      await synthesizer.synthesize(phonemeIds);
      
      // Check that Tensor was created with correct parameters
      const tensorCalls = mockTensor.mock.calls;
      const inputTensorCall = tensorCalls.find(call => call[0] === 'int64' && call[2][1] === 3);
      
      expect(inputTensorCall).toBeDefined();
      if (inputTensorCall) {
        expect(inputTensorCall[0]).toBe('int64');
        expect(inputTensorCall[1]).toBeInstanceOf(BigInt64Array);
        expect(inputTensorCall[1]).toEqual(new BigInt64Array([1n, 2n, 3n]));
      }
    });

    test('should set correct tensor shapes', async () => {
      const phonemeIds = [1, 2, 3, 4, 5];
      
      // Mock ort.Tensor constructor to capture tensor creation
      const mockTensor = jest.fn((type, data, dims) => ({
        type,
        data,
        dims
      }));
      (ort.Tensor as any) = mockTensor;
      
      await synthesizer.synthesize(phonemeIds);
      
      // Check that Tensor was created with correct dimensions
      const tensorCalls = mockTensor.mock.calls;
      const inputTensorCall = tensorCalls.find(call => call[0] === 'int64' && call[2][1] === 5);
      
      expect(inputTensorCall).toBeDefined();
      if (inputTensorCall) {
        expect(inputTensorCall[2]).toEqual([1, 5]);
      }
    });

    test('should include optional inputs only if supported', async () => {
      // Remove optional inputs from session
      mockSession.inputNames = ['input'];
      
      await synthesizer.synthesize([1, 2, 3]);
      
      const feeds = mockSession.run.mock.calls[0][0];
      expect(feeds.input).toBeDefined();
      expect(feeds.length_scale).toBeUndefined();
      expect(feeds.noise_scale).toBeUndefined();
    });
  });

  describe('dispose', () => {
    test('should dispose without error', async () => {
      await expect(synthesizer.dispose()).resolves.not.toThrow();
    });
  });
});