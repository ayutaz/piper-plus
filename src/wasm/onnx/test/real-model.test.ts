/**
 * Test with real Piper model
 */

import { ModelLoader } from '../src/ModelLoader';
import { VoiceSynthesizer } from '../src/VoiceSynthesizer';
import * as ort from 'onnxruntime-web';
import * as fs from 'fs';
import * as path from 'path';

// Mock fetch to load local files
global.fetch = jest.fn((url: string) => {
  const filePath = url.startsWith('file://') ? url.slice(7) : url;
  
  try {
    const content = fs.readFileSync(filePath);
    
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => {
        if (filePath.endsWith('.json')) {
          return JSON.parse(content.toString());
        }
        throw new Error('Not JSON');
      },
      arrayBuffer: async () => content.buffer,
      text: async () => content.toString()
    } as Response);
  } catch (error) {
    return Promise.resolve({
      ok: false,
      status: 404
    } as Response);
  }
}) as jest.Mock;

// Mock ONNX Runtime
jest.mock('onnxruntime-web', () => ({
  env: {
    wasm: {},
    versions: { common: '1.0.0' }
  },
  InferenceSession: {
    create: jest.fn((modelPath: string) => {
      // Return a mock session that simulates real model structure
      return Promise.resolve({
        inputNames: ['input', 'input_lengths', 'scales'],
        outputNames: ['output'],
        run: jest.fn(async (feeds) => {
          // Simulate inference
          const inputLength = feeds['input'].dims[1];
          const audioLength = inputLength * 200; // ~200 samples per phoneme
          
          return {
            output: {
              data: new Float32Array(audioLength).map(() => Math.random() * 0.2 - 0.1),
              dims: [1, audioLength]
            }
          };
        })
      });
    })
  },
  Tensor: jest.fn((type, data, dims) => ({
    type,
    data,
    dims
  }))
}));

describe('Real Piper Model Integration', () => {
  const modelPath = '/Users/s19447/Desktop/total-piper/piper/test/models/ja_JP-test-medium.onnx';
  const configPath = modelPath + '.json';
  
  test('should load real model configuration', async () => {
    const loader = new ModelLoader();
    
    // Check if the config file exists
    if (!fs.existsSync(configPath)) {
      console.log('Skipping test: Config file not found at', configPath);
      return;
    }
    
    const model = await loader.load(`file://${modelPath}`);
    
    // Verify Piper-specific config was loaded
    expect(model.config).toMatchObject({
      sampleRate: 22050,
      language: 'ja',
      phonemeType: 'openjtalk',
      piperVersion: '1.0.0'
    });
    
    // Check inference parameters
    expect(model.config.inference).toMatchObject({
      noise_scale: 0.667,
      length_scale: 1,
      noise_w: 0.8
    });
    
    // Verify phoneme mappings
    expect(model.config.phonemeIdMap).toHaveProperty('_', 0);
    expect(model.config.phonemeIdMap).toHaveProperty('\ue000', 17);
    expect(Object.keys(model.config.phonemeIdMap).length).toBe(58);
  });
  
  test('should synthesize audio with real model config', async () => {
    const loader = new ModelLoader();
    
    if (!fs.existsSync(configPath)) {
      console.log('Skipping test: Config file not found');
      return;
    }
    
    const model = await loader.load(`file://${modelPath}`);
    const synthesizer = new VoiceSynthesizer(model);
    
    // Test phoneme sequence: "ko n ni chi wa" 
    const phonemeIds = [
      25, // k
      11, // o
      22, // N
      50, // n
      8,  // i
      32, // chi
      56, // w
      7,  // a
      0   // silence
    ];
    
    const result = await synthesizer.synthesize(phonemeIds);
    
    expect(result).toHaveProperty('audio');
    expect(result).toHaveProperty('sampleRate', 22050);
    expect(result.audio).toBeInstanceOf(Float32Array);
    expect(result.audio.length).toBeGreaterThan(0);
  });
  
  test('should handle PUA-encoded phonemes correctly', async () => {
    const loader = new ModelLoader();
    
    if (!fs.existsSync(configPath)) {
      console.log('Skipping test: Config file not found');
      return;
    }
    
    const model = await loader.load(`file://${modelPath}`);
    
    // Test PUA mappings
    const puaPhonemes = ['\ue000', '\ue006', '\ue00a'];
    const expectedIds = [17, 26, 32];
    
    puaPhonemes.forEach((phoneme, index) => {
      expect(model.config.phonemeIdMap[phoneme]).toBe(expectedIds[index]);
    });
  });
  
  test('should auto-detect .onnx.json config file', async () => {
    const loader = new ModelLoader();
    
    if (!fs.existsSync(configPath)) {
      console.log('Skipping test: Config file not found');
      return;
    }
    
    // Load without specifying config path
    const model = await loader.load(`file://${modelPath}`);
    
    // Should still load the config
    expect(model.config.phonemeType).toBe('openjtalk');
    expect(model.config.piperVersion).toBe('1.0.0');
  });
});