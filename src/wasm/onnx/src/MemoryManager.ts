/**
 * Memory Manager for Piper ONNX Runtime
 * 
 * Tracks and manages memory usage, provides cleanup utilities
 */

export interface MemoryStats {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
  wasmMemory?: number;
  tensorsInMemory?: number;
}

export class MemoryManager {
  private readonly memoryThreshold = 0.85; // 85% memory usage threshold
  private memoryWarningCallback?: (stats: MemoryStats) => void;
  private cleanupCallbacks: Array<() => Promise<void>> = [];
  private monitoringInterval?: NodeJS.Timeout;
  
  /**
   * Start memory monitoring
   */
  startMonitoring(intervalMs: number = 5000): void {
    if (this.monitoringInterval) {
      return;
    }
    
    this.monitoringInterval = setInterval(() => {
      const stats = this.getMemoryStats();
      
      if (this.isMemoryPressureHigh(stats)) {
        console.warn('High memory pressure detected', stats);
        
        if (this.memoryWarningCallback) {
          this.memoryWarningCallback(stats);
        }
        
        // Attempt automatic cleanup
        this.performCleanup().catch(console.error);
      }
    }, intervalMs);
  }
  
  /**
   * Stop memory monitoring
   */
  stopMonitoring(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = undefined;
    }
  }
  
  /**
   * Get current memory statistics
   */
  getMemoryStats(): MemoryStats {
    const stats: MemoryStats = {
      usedJSHeapSize: 0,
      totalJSHeapSize: 0,
      jsHeapSizeLimit: 0
    };
    
    // Browser memory API
    if ('memory' in performance && (performance as any).memory) {
      const memory = (performance as any).memory;
      stats.usedJSHeapSize = memory.usedJSHeapSize || 0;
      stats.totalJSHeapSize = memory.totalJSHeapSize || 0;
      stats.jsHeapSizeLimit = memory.jsHeapSizeLimit || 0;
    }
    
    // WebAssembly memory
    if (typeof WebAssembly !== 'undefined' && WebAssembly.Memory) {
      try {
        // This is a rough estimate - actual WASM memory tracking would need
        // to be implemented in the WASM module itself
        stats.wasmMemory = this.estimateWasmMemory();
      } catch (e) {
        // Ignore errors in WASM memory estimation
      }
    }
    
    return stats;
  }
  
  /**
   * Check if memory pressure is high
   */
  isMemoryPressureHigh(stats?: MemoryStats): boolean {
    const currentStats = stats || this.getMemoryStats();
    
    if (currentStats.jsHeapSizeLimit > 0) {
      const usageRatio = currentStats.usedJSHeapSize / currentStats.jsHeapSizeLimit;
      return usageRatio > this.memoryThreshold;
    }
    
    // Fallback: check absolute memory usage (> 1GB)
    return currentStats.usedJSHeapSize > 1024 * 1024 * 1024;
  }
  
  /**
   * Register a cleanup callback
   */
  registerCleanupCallback(callback: () => Promise<void>): void {
    this.cleanupCallbacks.push(callback);
  }
  
  /**
   * Set memory warning callback
   */
  onMemoryWarning(callback: (stats: MemoryStats) => void): void {
    this.memoryWarningCallback = callback;
  }
  
  /**
   * Perform memory cleanup
   */
  async performCleanup(): Promise<void> {
    console.log('Performing memory cleanup...');
    
    // Run all registered cleanup callbacks
    const cleanupPromises = this.cleanupCallbacks.map(callback => 
      callback().catch(error => console.error('Cleanup callback error:', error))
    );
    
    await Promise.all(cleanupPromises);
    
    // Request garbage collection if available
    if (typeof gc !== 'undefined') {
      gc();
    }
    
    // Log memory stats after cleanup
    const afterStats = this.getMemoryStats();
    console.log('Memory after cleanup:', {
      usedMB: Math.round(afterStats.usedJSHeapSize / 1024 / 1024),
      totalMB: Math.round(afterStats.totalJSHeapSize / 1024 / 1024)
    });
  }
  
  /**
   * Create a disposable resource tracker
   */
  createResourceTracker(): ResourceTracker {
    return new ResourceTracker();
  }
  
  /**
   * Estimate WASM memory usage
   */
  private estimateWasmMemory(): number {
    // This is a placeholder - actual implementation would need
    // integration with the WASM module
    return 0;
  }
  
  /**
   * Format bytes for display
   */
  formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
}

/**
 * Resource tracker for managing disposable resources
 */
export class ResourceTracker {
  private resources: Array<{ name: string; dispose: () => Promise<void> }> = [];
  
  /**
   * Register a resource for tracking
   */
  register(name: string, dispose: () => Promise<void>): void {
    this.resources.push({ name, dispose });
  }
  
  /**
   * Dispose all tracked resources
   */
  async disposeAll(): Promise<void> {
    const errors: Error[] = [];
    
    for (const resource of this.resources) {
      try {
        await resource.dispose();
      } catch (error) {
        console.error(`Failed to dispose resource: ${resource.name}`, error);
        errors.push(error as Error);
      }
    }
    
    this.resources = [];
    
    if (errors.length > 0) {
      throw new Error(`Failed to dispose ${errors.length} resources`);
    }
  }
  
  /**
   * Get number of tracked resources
   */
  get count(): number {
    return this.resources.length;
  }
}