/**
 * Error Handler for Piper ONNX Runtime
 * 
 * Provides centralized error handling and recovery strategies
 */

export enum ErrorType {
  INITIALIZATION = 'INITIALIZATION',
  MODEL_LOADING = 'MODEL_LOADING',
  INFERENCE = 'INFERENCE',
  AUDIO_PLAYBACK = 'AUDIO_PLAYBACK',
  MEMORY = 'MEMORY',
  NETWORK = 'NETWORK',
  INVALID_INPUT = 'INVALID_INPUT',
  UNKNOWN = 'UNKNOWN'
}

export interface ErrorContext {
  type: ErrorType;
  operation: string;
  details?: Record<string, any>;
}

export class PiperError extends Error {
  constructor(
    message: string,
    public readonly type: ErrorType,
    public readonly cause?: Error,
    public readonly recoverable: boolean = false,
    public readonly context?: ErrorContext
  ) {
    super(message);
    this.name = 'PiperError';
  }
}

export class ErrorHandler {
  private errorCallbacks = new Map<ErrorType, Array<(error: PiperError) => void>>();
  private globalErrorCallback?: (error: PiperError) => void;
  
  /**
   * Register an error callback for specific error types
   */
  onError(type: ErrorType, callback: (error: PiperError) => void): void {
    if (!this.errorCallbacks.has(type)) {
      this.errorCallbacks.set(type, []);
    }
    this.errorCallbacks.get(type)!.push(callback);
  }
  
  /**
   * Register a global error callback
   */
  onAnyError(callback: (error: PiperError) => void): void {
    this.globalErrorCallback = callback;
  }
  
  /**
   * Handle an error and determine recovery strategy
   */
  handleError(error: Error, context: ErrorContext): PiperError {
    const piperError = this.wrapError(error, context);
    
    // Notify specific callbacks
    const callbacks = this.errorCallbacks.get(piperError.type) || [];
    callbacks.forEach(cb => cb(piperError));
    
    // Notify global callback
    if (this.globalErrorCallback) {
      this.globalErrorCallback(piperError);
    }
    
    // Log error details
    console.error(`[${piperError.type}] ${piperError.message}`, {
      operation: context.operation,
      details: context.details,
      cause: piperError.cause
    });
    
    return piperError;
  }
  
  /**
   * Wrap a generic error into a PiperError
   */
  private wrapError(error: Error, context: ErrorContext): PiperError {
    const type = this.detectErrorType(error, context);
    const recoverable = this.isRecoverable(error, type);
    const message = this.formatErrorMessage(error, context);
    
    return new PiperError(message, type, error, recoverable, context);
  }
  
  /**
   * Detect error type from error message and context
   */
  private detectErrorType(error: Error, context: ErrorContext): ErrorType {
    // Use provided type if available
    if (context.type) {
      return context.type;
    }
    
    const message = error.message.toLowerCase();
    
    // Network errors
    if (message.includes('fetch') || 
        message.includes('network') || 
        message.includes('cors') ||
        message.includes('http')) {
      return ErrorType.NETWORK;
    }
    
    // Memory errors
    if (message.includes('memory') || 
        message.includes('oom') || 
        message.includes('allocation')) {
      return ErrorType.MEMORY;
    }
    
    // Model loading errors
    if (message.includes('model') || 
        message.includes('onnx') || 
        message.includes('session')) {
      return ErrorType.MODEL_LOADING;
    }
    
    // Inference errors
    if (message.includes('inference') || 
        message.includes('tensor') || 
        message.includes('shape')) {
      return ErrorType.INFERENCE;
    }
    
    // Audio errors
    if (message.includes('audio') || 
        message.includes('context') || 
        message.includes('playback')) {
      return ErrorType.AUDIO_PLAYBACK;
    }
    
    return ErrorType.UNKNOWN;
  }
  
  /**
   * Determine if an error is recoverable
   */
  private isRecoverable(error: Error, type: ErrorType): boolean {
    switch (type) {
      case ErrorType.NETWORK:
        return true; // Can retry
      
      case ErrorType.MEMORY:
        return true; // Can clear cache and retry
      
      case ErrorType.AUDIO_PLAYBACK:
        return true; // Can reinitialize audio context
      
      case ErrorType.INVALID_INPUT:
        return false; // User must fix input
      
      case ErrorType.MODEL_LOADING:
        // Recoverable if network issue, not if corrupted
        return error.message.includes('fetch') || error.message.includes('404');
      
      case ErrorType.INFERENCE:
        // Some inference errors are recoverable
        return error.message.includes('timeout') || error.message.includes('busy');
      
      default:
        return false;
    }
  }
  
  /**
   * Format error message for user display
   */
  private formatErrorMessage(error: Error, context: ErrorContext): string {
    const baseMessage = error.message;
    const operation = context.operation;
    
    switch (context.type) {
      case ErrorType.INITIALIZATION:
        return `Failed to initialize ${operation}: ${baseMessage}`;
      
      case ErrorType.MODEL_LOADING:
        return `Failed to load model: ${baseMessage}`;
      
      case ErrorType.INFERENCE:
        return `Synthesis failed: ${baseMessage}`;
      
      case ErrorType.AUDIO_PLAYBACK:
        return `Audio playback error: ${baseMessage}`;
      
      case ErrorType.MEMORY:
        return `Out of memory during ${operation}. Try closing other applications.`;
      
      case ErrorType.NETWORK:
        return `Network error during ${operation}: ${baseMessage}`;
      
      case ErrorType.INVALID_INPUT:
        return `Invalid input: ${baseMessage}`;
      
      default:
        return `${operation} failed: ${baseMessage}`;
    }
  }
  
  /**
   * Get recovery suggestions for an error
   */
  getRecoverySuggestions(error: PiperError): string[] {
    const suggestions: string[] = [];
    
    switch (error.type) {
      case ErrorType.NETWORK:
        suggestions.push('Check your internet connection');
        suggestions.push('Try again in a few moments');
        suggestions.push('Check if the model URL is correct');
        break;
      
      case ErrorType.MEMORY:
        suggestions.push('Close other browser tabs');
        suggestions.push('Try a smaller model');
        suggestions.push('Refresh the page');
        break;
      
      case ErrorType.AUDIO_PLAYBACK:
        suggestions.push('Check your audio permissions');
        suggestions.push('Try a different browser');
        suggestions.push('Ensure audio is not muted');
        break;
      
      case ErrorType.MODEL_LOADING:
        suggestions.push('Verify the model file exists');
        suggestions.push('Check the model format is correct');
        suggestions.push('Try downloading the model again');
        break;
      
      case ErrorType.INFERENCE:
        suggestions.push('Try with shorter text');
        suggestions.push('Check input phonemes are valid');
        suggestions.push('Reduce synthesis parameters');
        break;
    }
    
    return suggestions;
  }
}