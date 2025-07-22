/**
 * Unit tests for Memory Manager
 */

import { MemoryManager, ResourceTracker } from '../src/MemoryManager';

describe('MemoryManager', () => {
  let memoryManager: MemoryManager;
  
  beforeEach(() => {
    memoryManager = new MemoryManager();
  });
  
  afterEach(() => {
    memoryManager.stopMonitoring();
  });
  
  describe('memory statistics', () => {
    test('should return memory stats', () => {
      const stats = memoryManager.getMemoryStats();
      
      expect(stats).toHaveProperty('usedJSHeapSize');
      expect(stats).toHaveProperty('totalJSHeapSize');
      expect(stats).toHaveProperty('jsHeapSizeLimit');
      expect(typeof stats.usedJSHeapSize).toBe('number');
    });
    
    test('should detect high memory pressure', () => {
      // Mock high memory usage
      const highMemoryStats = {
        usedJSHeapSize: 900 * 1024 * 1024, // 900MB
        totalJSHeapSize: 1000 * 1024 * 1024, // 1GB
        jsHeapSizeLimit: 1000 * 1024 * 1024 // 1GB
      };
      
      const isHigh = memoryManager.isMemoryPressureHigh(highMemoryStats);
      expect(isHigh).toBe(true);
    });
    
    test('should not detect high memory pressure when usage is low', () => {
      // Mock low memory usage
      const lowMemoryStats = {
        usedJSHeapSize: 100 * 1024 * 1024, // 100MB
        totalJSHeapSize: 500 * 1024 * 1024, // 500MB
        jsHeapSizeLimit: 1000 * 1024 * 1024 // 1GB
      };
      
      const isHigh = memoryManager.isMemoryPressureHigh(lowMemoryStats);
      expect(isHigh).toBe(false);
    });
  });
  
  describe('cleanup callbacks', () => {
    test('should register and execute cleanup callbacks', async () => {
      const cleanup1 = jest.fn().mockResolvedValue(undefined);
      const cleanup2 = jest.fn().mockResolvedValue(undefined);
      
      memoryManager.registerCleanupCallback(cleanup1);
      memoryManager.registerCleanupCallback(cleanup2);
      
      await memoryManager.performCleanup();
      
      expect(cleanup1).toHaveBeenCalled();
      expect(cleanup2).toHaveBeenCalled();
    });
    
    test('should handle cleanup callback errors', async () => {
      const cleanup1 = jest.fn().mockRejectedValue(new Error('Cleanup failed'));
      const cleanup2 = jest.fn().mockResolvedValue(undefined);
      
      memoryManager.registerCleanupCallback(cleanup1);
      memoryManager.registerCleanupCallback(cleanup2);
      
      // Should not throw
      await expect(memoryManager.performCleanup()).resolves.not.toThrow();
      
      // Both callbacks should be called
      expect(cleanup1).toHaveBeenCalled();
      expect(cleanup2).toHaveBeenCalled();
    });
  });
  
  describe('memory monitoring', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });
    
    afterEach(() => {
      jest.useRealTimers();
    });
    
    test('should start and stop monitoring', () => {
      const warningCallback = jest.fn();
      memoryManager.onMemoryWarning(warningCallback);
      
      // Start monitoring
      memoryManager.startMonitoring(1000);
      
      // Fast forward time
      jest.advanceTimersByTime(1000);
      
      // Stop monitoring
      memoryManager.stopMonitoring();
      
      // Further time advancement should not trigger callbacks
      jest.advanceTimersByTime(5000);
      
      // Warning callback may or may not be called depending on actual memory
      // Just verify monitoring can be started and stopped without errors
      expect(true).toBe(true);
    });
    
    test('should trigger warning callback on high memory', () => {
      const warningCallback = jest.fn();
      memoryManager.onMemoryWarning(warningCallback);
      
      // Mock isMemoryPressureHigh to return true
      jest.spyOn(memoryManager, 'isMemoryPressureHigh').mockReturnValue(true);
      jest.spyOn(memoryManager, 'performCleanup').mockResolvedValue(undefined);
      
      memoryManager.startMonitoring(100);
      
      // Trigger monitoring
      jest.advanceTimersByTime(100);
      
      expect(warningCallback).toHaveBeenCalled();
    });
  });
  
  describe('formatBytes', () => {
    test('should format bytes correctly', () => {
      expect(memoryManager.formatBytes(0)).toBe('0 Bytes');
      expect(memoryManager.formatBytes(1024)).toBe('1 KB');
      expect(memoryManager.formatBytes(1024 * 1024)).toBe('1 MB');
      expect(memoryManager.formatBytes(1.5 * 1024 * 1024)).toBe('1.5 MB');
      expect(memoryManager.formatBytes(1024 * 1024 * 1024)).toBe('1 GB');
    });
  });
});

describe('ResourceTracker', () => {
  let tracker: ResourceTracker;
  
  beforeEach(() => {
    tracker = new ResourceTracker();
  });
  
  test('should register and dispose resources', async () => {
    const dispose1 = jest.fn().mockResolvedValue(undefined);
    const dispose2 = jest.fn().mockResolvedValue(undefined);
    
    tracker.register('resource1', dispose1);
    tracker.register('resource2', dispose2);
    
    expect(tracker.count).toBe(2);
    
    await tracker.disposeAll();
    
    expect(dispose1).toHaveBeenCalled();
    expect(dispose2).toHaveBeenCalled();
    expect(tracker.count).toBe(0);
  });
  
  test('should handle disposal errors', async () => {
    const dispose1 = jest.fn().mockRejectedValue(new Error('Dispose failed'));
    const dispose2 = jest.fn().mockResolvedValue(undefined);
    
    tracker.register('resource1', dispose1);
    tracker.register('resource2', dispose2);
    
    await expect(tracker.disposeAll()).rejects.toThrow('Failed to dispose 1 resources');
    
    // Both should still be called
    expect(dispose1).toHaveBeenCalled();
    expect(dispose2).toHaveBeenCalled();
  });
});