/**
 * Unit tests for Error Handler
 */

import { ErrorHandler, ErrorType, PiperError } from '../src/ErrorHandler';

describe('ErrorHandler', () => {
  let errorHandler: ErrorHandler;
  
  beforeEach(() => {
    errorHandler = new ErrorHandler();
  });
  
  describe('error type detection', () => {
    test('should detect network errors', () => {
      const error = new Error('Failed to fetch model');
      const result = errorHandler.handleError(error, {
        type: ErrorType.NETWORK,
        operation: 'fetch'
      });
      
      expect(result).toBeInstanceOf(PiperError);
      expect(result.type).toBe(ErrorType.NETWORK);
      expect(result.recoverable).toBe(true);
    });
    
    test('should detect memory errors', () => {
      const error = new Error('Out of memory');
      const result = errorHandler.handleError(error, {
        type: ErrorType.MEMORY,
        operation: 'allocate'
      });
      
      expect(result.type).toBe(ErrorType.MEMORY);
      expect(result.recoverable).toBe(true);
    });
    
    test('should detect inference errors', () => {
      const error = new Error('Invalid tensor shape');
      const result = errorHandler.handleError(error, {
        type: ErrorType.INFERENCE,
        operation: 'synthesize'
      });
      
      expect(result.type).toBe(ErrorType.INFERENCE);
    });
  });
  
  describe('error callbacks', () => {
    test('should call specific error callbacks', () => {
      const networkCallback = jest.fn();
      const memoryCallback = jest.fn();
      
      errorHandler.onError(ErrorType.NETWORK, networkCallback);
      errorHandler.onError(ErrorType.MEMORY, memoryCallback);
      
      const error = new Error('Network timeout');
      errorHandler.handleError(error, {
        type: ErrorType.NETWORK,
        operation: 'download'
      });
      
      expect(networkCallback).toHaveBeenCalledTimes(1);
      expect(memoryCallback).not.toHaveBeenCalled();
    });
    
    test('should call global error callback', () => {
      const globalCallback = jest.fn();
      errorHandler.onAnyError(globalCallback);
      
      const error = new Error('Some error');
      errorHandler.handleError(error, {
        type: ErrorType.UNKNOWN,
        operation: 'test'
      });
      
      expect(globalCallback).toHaveBeenCalledTimes(1);
      expect(globalCallback).toHaveBeenCalledWith(expect.any(PiperError));
    });
  });
  
  describe('recovery suggestions', () => {
    test('should provide network error suggestions', () => {
      const error = new PiperError('Network failed', ErrorType.NETWORK);
      const suggestions = errorHandler.getRecoverySuggestions(error);
      
      expect(suggestions).toContain('Check your internet connection');
      expect(suggestions).toContain('Try again in a few moments');
    });
    
    test('should provide memory error suggestions', () => {
      const error = new PiperError('OOM', ErrorType.MEMORY);
      const suggestions = errorHandler.getRecoverySuggestions(error);
      
      expect(suggestions).toContain('Close other browser tabs');
      expect(suggestions).toContain('Try a smaller model');
    });
    
    test('should provide audio error suggestions', () => {
      const error = new PiperError('Audio failed', ErrorType.AUDIO_PLAYBACK);
      const suggestions = errorHandler.getRecoverySuggestions(error);
      
      expect(suggestions).toContain('Check your audio permissions');
      expect(suggestions).toContain('Try a different browser');
    });
  });
  
  describe('error formatting', () => {
    test('should format initialization errors', () => {
      const error = new Error('WebAssembly not supported');
      const result = errorHandler.handleError(error, {
        type: ErrorType.INITIALIZATION,
        operation: 'WASM'
      });
      
      expect(result.message).toContain('Failed to initialize WASM');
      expect(result.message).toContain('WebAssembly not supported');
    });
    
    test('should format model loading errors', () => {
      const error = new Error('404 Not Found');
      const result = errorHandler.handleError(error, {
        type: ErrorType.MODEL_LOADING,
        operation: 'load'
      });
      
      expect(result.message).toContain('Failed to load model');
      expect(result.message).toContain('404 Not Found');
    });
  });
  
  describe('error context', () => {
    test('should preserve error context', () => {
      const error = new Error('Test error');
      const context = {
        type: ErrorType.INFERENCE,
        operation: 'test-op',
        details: { param1: 'value1', param2: 123 }
      };
      
      const result = errorHandler.handleError(error, context);
      
      expect(result.context).toEqual(context);
      expect(result.cause).toBe(error);
    });
  });
});