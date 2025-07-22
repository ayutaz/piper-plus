/**
 * Retry Handler for Network and Inference Operations
 * 
 * Provides exponential backoff retry logic for resilient operations
 */

export interface RetryOptions {
  maxRetries?: number;
  initialDelay?: number;
  maxDelay?: number;
  backoffFactor?: number;
  onRetry?: (error: Error, attempt: number) => void;
}

export class RetryHandler {
  private readonly defaultOptions: Required<RetryOptions> = {
    maxRetries: 3,
    initialDelay: 1000,
    maxDelay: 30000,
    backoffFactor: 2,
    onRetry: () => {}
  };
  
  /**
   * Execute an operation with retry logic
   */
  async execute<T>(
    operation: () => Promise<T>,
    options: RetryOptions = {}
  ): Promise<T> {
    const config = { ...this.defaultOptions, ...options };
    let lastError: Error;
    
    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        if (attempt === config.maxRetries) {
          break;
        }
        
        // Check if error is retryable
        if (!this.isRetryableError(lastError)) {
          throw lastError;
        }
        
        // Calculate delay with exponential backoff
        const delay = Math.min(
          config.initialDelay * Math.pow(config.backoffFactor, attempt),
          config.maxDelay
        );
        
        console.warn(`Operation failed (attempt ${attempt + 1}/${config.maxRetries + 1}), retrying in ${delay}ms...`, lastError.message);
        config.onRetry(lastError, attempt + 1);
        
        await this.delay(delay);
      }
    }
    
    throw new Error(`Operation failed after ${config.maxRetries + 1} attempts: ${lastError!.message}`);
  }
  
  /**
   * Execute a network request with retry logic
   */
  async fetchWithRetry(
    url: string,
    init?: RequestInit,
    options?: RetryOptions
  ): Promise<Response> {
    return this.execute(async () => {
      const response = await fetch(url, init);
      
      // Retry on server errors (5xx) or network errors
      if (response.status >= 500) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
      }
      
      return response;
    }, options);
  }
  
  /**
   * Determine if an error is retryable
   */
  private isRetryableError(error: Error): boolean {
    const message = error.message.toLowerCase();
    
    // Network errors
    if (error.name === 'NetworkError' || 
        error.name === 'TypeError' ||
        message.includes('network')) {
      return true;
    }
    
    // ONNX Runtime errors that might be transient
    if (message.includes('timeout') || 
        message.includes('oom') || 
        message.includes('out of memory')) {
      return true;
    }
    
    // Server errors
    if (message.includes('server error') ||
        message.includes('502') ||
        message.includes('503') ||
        message.includes('504') ||
        message.includes('service unavailable')) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Delay execution
   */
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  /**
   * Create a timeout wrapper for operations
   */
  withTimeout<T>(
    operation: () => Promise<T>,
    timeoutMs: number
  ): Promise<T> {
    return Promise.race([
      operation(),
      new Promise<T>((_, reject) => 
        setTimeout(() => reject(new Error(`Operation timed out after ${timeoutMs}ms`)), timeoutMs)
      )
    ]);
  }
}