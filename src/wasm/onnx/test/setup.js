// Jest setup file
const { TextEncoder, TextDecoder } = require('util');

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock performance
global.performance = {
  now: jest.fn(() => Date.now())
};

// Mock console methods for cleaner test output
global.console = {
  ...console,
  log: jest.fn(),
  warn: jest.fn(),
  error: jest.fn()
};

// Polyfill for ReadableStream (minimal implementation for tests)
if (!global.ReadableStream) {
  global.ReadableStream = class ReadableStream {
    constructor(underlyingSource) {
      this.underlyingSource = underlyingSource;
      this._controller = {
        chunks: [],
        closed: false,
        enqueue: (chunk) => {
          if (!this._controller.closed) {
            this._controller.chunks.push(chunk);
          }
        },
        close: () => {
          this._controller.closed = true;
        },
        error: (e) => {
          this._controller.errorValue = e;
          this._controller.closed = true;
        }
      };
      
      // Start the stream
      if (underlyingSource && underlyingSource.start) {
        Promise.resolve(underlyingSource.start(this._controller)).catch(e => {
          this._controller.error(e);
        });
      }
      
      // Handle cancel
      if (underlyingSource && underlyingSource.cancel) {
        this.cancel = () => underlyingSource.cancel();
      }
    }
    
    getReader() {
      const controller = this._controller;
      let index = 0;
      
      return {
        read: async () => {
          if (controller.errorValue) {
            throw controller.errorValue;
          }
          
          if (index < controller.chunks.length) {
            return { done: false, value: controller.chunks[index++] };
          }
          
          if (controller.closed) {
            return { done: true, value: undefined };
          }
          
          // Wait for more chunks or close
          await new Promise(resolve => setTimeout(resolve, 10));
          return { done: true, value: undefined };
        }
      };
    }
  };
}