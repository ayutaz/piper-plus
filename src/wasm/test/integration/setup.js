// Setup for integration tests
const { TextEncoder, TextDecoder } = require('util');

// Polyfill for Node.js environment
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock fetch for WASM loading
global.fetch = jest.fn((url) => {
  // Mock response for different file types
  if (url.endsWith('.wasm')) {
    return Promise.resolve({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(100))
    });
  } else if (url.endsWith('.onnx')) {
    return Promise.resolve({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(1000))
    });
  } else if (url.endsWith('.json')) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        sampleRate: 22050,
        numSpeakers: 1,
        language: 'ja'
      })
    });
  }
  
  return Promise.reject(new Error(`Unknown URL: ${url}`));
});

// Mock performance if not available
if (typeof global.performance === 'undefined') {
  global.performance = {
    now: () => Date.now()
  };
}

// Mock AudioContext
class MockAudioContext {
  state = 'running';
  sampleRate = 44100;
  destination = {};
  
  createGain() {
    return {
      gain: { value: 1.0 },
      connect: jest.fn()
    };
  }
  
  createBuffer(channels, length, sampleRate) {
    return {
      numberOfChannels: channels,
      length,
      sampleRate,
      copyToChannel: jest.fn(),
      getChannelData: jest.fn(() => new Float32Array(length))
    };
  }
  
  createBufferSource() {
    return {
      buffer: null,
      connect: jest.fn(),
      start: jest.fn(),
      stop: jest.fn(),
      disconnect: jest.fn(),
      onended: null
    };
  }
  
  resume = jest.fn().mockResolvedValue(undefined);
  close = jest.fn().mockResolvedValue(undefined);
}

global.AudioContext = MockAudioContext;