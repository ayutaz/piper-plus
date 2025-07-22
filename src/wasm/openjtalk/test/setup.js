// Setup for OpenJTalk WebAssembly tests
const { TextEncoder, TextDecoder } = require('util');

// Polyfill for Node.js environment
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock fetch for WASM loading
global.fetch = jest.fn();

// Mock performance if not available
if (typeof global.performance === 'undefined') {
  global.performance = {
    now: () => Date.now()
  };
}