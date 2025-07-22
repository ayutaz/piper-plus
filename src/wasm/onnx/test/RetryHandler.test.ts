/**
 * Unit tests for Retry Handler
 */

import { RetryHandler } from '../src/RetryHandler';

describe('RetryHandler', () => {
  let retryHandler: RetryHandler;
  
  beforeEach(() => {
    retryHandler = new RetryHandler();
  });
  
  describe('execute with retry', () => {
    test('should succeed on first attempt', async () => {
      const operation = jest.fn().mockResolvedValue('success');
      
      const result = await retryHandler.execute(operation);
      
      expect(result).toBe('success');
      expect(operation).toHaveBeenCalledTimes(1);
    });
    
    test('should retry on failure', async () => {
      const operation = jest.fn()
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValue('success');
      
      const result = await retryHandler.execute(operation, {
        maxRetries: 2,
        initialDelay: 10  // Short delay for testing
      });
      
      expect(result).toBe('success');
      expect(operation).toHaveBeenCalledTimes(2);
    });
    
    test('should respect max retries', async () => {
      const operation = jest.fn().mockRejectedValue(new Error('Network error'));
      
      await expect(
        retryHandler.execute(operation, {
          maxRetries: 2,
          initialDelay: 10
        })
      ).rejects.toThrow('Operation failed after 3 attempts');
      
      expect(operation).toHaveBeenCalledTimes(3);
    });
    
    test('should use exponential backoff', async () => {
      const attemptNumbers: number[] = [];
      const operation = jest.fn().mockRejectedValue(new Error('Network error'));
      
      await expect(
        retryHandler.execute(operation, {
          maxRetries: 3,
          initialDelay: 10,
          backoffFactor: 2,
          onRetry: (error, attempt) => {
            attemptNumbers.push(attempt);
          }
        })
      ).rejects.toThrow();
      
      expect(attemptNumbers).toEqual([1, 2, 3]);
      expect(operation).toHaveBeenCalledTimes(4);
    });
    
    test('should respect max delay', async () => {
      const operation = jest.fn().mockRejectedValue(new Error('Network error'));
      
      await expect(
        retryHandler.execute(operation, {
          maxRetries: 5,
          initialDelay: 10,
          maxDelay: 30,
          backoffFactor: 3
        })
      ).rejects.toThrow();
      
      expect(operation).toHaveBeenCalledTimes(6);
    });
    
    test('should not retry non-retryable errors', async () => {
      const operation = jest.fn().mockRejectedValue(new Error('Invalid input'));
      
      await expect(retryHandler.execute(operation)).rejects.toThrow('Invalid input');
      expect(operation).toHaveBeenCalledTimes(1);
    });
    
    test('should call onRetry callback', async () => {
      const onRetry = jest.fn();
      const operation = jest.fn()
        .mockRejectedValueOnce(new Error('Network error'))
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValue('success');
      
      await retryHandler.execute(operation, {
        maxRetries: 3,
        initialDelay: 10,
        onRetry
      });
      
      expect(onRetry).toHaveBeenCalledTimes(2);
      expect(onRetry).toHaveBeenCalledWith(expect.any(Error), 1);
      expect(onRetry).toHaveBeenCalledWith(expect.any(Error), 2);
    });
  });
  
  describe('fetchWithRetry', () => {
    test('should retry on 5xx errors', async () => {
      global.fetch = jest.fn()
        .mockResolvedValueOnce({ status: 503, statusText: 'Service Unavailable' })
        .mockResolvedValueOnce({ status: 200, ok: true });
      
      const result = await retryHandler.fetchWithRetry('https://example.com', {}, {
        maxRetries: 2,
        initialDelay: 10
      });
      
      expect(result.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
    
    test('should not retry on 4xx errors', async () => {
      global.fetch = jest.fn().mockResolvedValue({ 
        status: 404, 
        statusText: 'Not Found',
        ok: false 
      });
      
      const result = await retryHandler.fetchWithRetry('https://example.com');
      
      expect(result.status).toBe(404);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });
  });
  
  describe('withTimeout', () => {
    test('should complete within timeout', async () => {
      const operation = jest.fn().mockResolvedValue('success');
      
      const result = await retryHandler.withTimeout(operation, 1000);
      expect(result).toBe('success');
    });
    
    test('should timeout if operation takes too long', async () => {
      const operation = jest.fn(async () => {
        await new Promise(resolve => setTimeout(resolve, 200));
        return 'success';
      });
      
      await expect(
        retryHandler.withTimeout(operation, 100)
      ).rejects.toThrow('Operation timed out after 100ms');
    });
  });
});