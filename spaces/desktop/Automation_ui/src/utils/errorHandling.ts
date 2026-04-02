/**
 * Standardized Error Handling Utility
 * 
 * Provides consistent error handling patterns across all services:
 * - Error transformation to user-friendly messages
 * - Retry logic with exponential backoff
 * - Error context for better debugging
 * - Error logging integration
 */

export interface ServiceError {
  code: string;
  message: string;
  userMessage: string;
  details?: Record<string, any>;
  timestamp: string;
  retryable: boolean;
}

export interface RetryOptions {
  maxRetries?: number;
  initialDelay?: number;
  maxDelay?: number;
  backoffMultiplier?: number;
  retryableErrors?: string[];
}

/**
 * Error codes for different error types
 */
export enum ErrorCode {
  // Network errors
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT_ERROR = 'TIMEOUT_ERROR',
  CONNECTION_ERROR = 'CONNECTION_ERROR',
  
  // API errors
  API_ERROR = 'API_ERROR',
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  NOT_FOUND = 'NOT_FOUND',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  
  // WebSocket errors
  WEBSOCKET_ERROR = 'WEBSOCKET_ERROR',
  WEBSOCKET_CLOSED = 'WEBSOCKET_CLOSED',
  WEBSOCKET_SEND_FAILED = 'WEBSOCKET_SEND_FAILED',
  
  // Service errors
  SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE',
  INVALID_STATE = 'INVALID_STATE',
  OPERATION_FAILED = 'OPERATION_FAILED',
  
  // Generic
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}

/**
 * Transforms any error into a standardized ServiceError
 */
export function transformError(
  error: unknown,
  context?: Record<string, any>
): ServiceError {
  const timestamp = new Date().toISOString();
  
  // Handle Error objects
  if (error instanceof Error) {
    return {
      code: extractErrorCode(error),
      message: error.message,
      userMessage: getUserFriendlyMessage(error),
      details: {
        ...context,
        stack: import.meta.env.DEV ? error.stack : undefined,
        name: error.name,
      },
      timestamp,
      retryable: isRetryableError(error),
    };
  }

  // Handle string errors
  if (typeof error === 'string') {
    return {
      code: ErrorCode.UNKNOWN_ERROR,
      message: error,
      userMessage: getUserFriendlyMessage(error),
      details: context,
      timestamp,
      retryable: false,
    };
  }

  // Handle Supabase errors
  if (error && typeof error === 'object' && 'code' in error) {
    const supabaseError = error as { code?: string; message?: string; details?: string };
    return {
      code: supabaseError.code || ErrorCode.API_ERROR,
      message: supabaseError.message || 'Database error occurred',
      userMessage: getUserFriendlyMessage(supabaseError),
      details: {
        ...context,
        supabaseCode: supabaseError.code,
        supabaseDetails: supabaseError.details,
      },
      timestamp,
      retryable: isRetryableSupabaseError(supabaseError.code),
    };
  }

  // Handle fetch errors
  if (error && typeof error === 'object' && 'response' in error) {
    const fetchError = error as { response?: Response; status?: number };
    return {
      code: fetchError.status === 401 ? ErrorCode.UNAUTHORIZED :
            fetchError.status === 403 ? ErrorCode.FORBIDDEN :
            fetchError.status === 404 ? ErrorCode.NOT_FOUND :
            fetchError.status === 408 ? ErrorCode.TIMEOUT_ERROR :
            fetchError.status >= 500 ? ErrorCode.SERVICE_UNAVAILABLE :
            ErrorCode.API_ERROR,
      message: `HTTP ${fetchError.status || 'Unknown'} error`,
      userMessage: getUserFriendlyMessage(fetchError),
      details: {
        ...context,
        status: fetchError.status,
        statusText: fetchError.response?.statusText,
      },
      timestamp,
      retryable: fetchError.status ? fetchError.status >= 500 : false,
    };
  }

  // Fallback for unknown errors
  return {
    code: ErrorCode.UNKNOWN_ERROR,
    message: 'An unknown error occurred',
    userMessage: 'Something went wrong. Please try again.',
    details: {
      ...context,
      rawError: String(error),
    },
    timestamp,
    retryable: false,
  };
}

/**
 * Extracts error code from error
 */
function extractErrorCode(error: Error): ErrorCode {
  const message = error.message.toLowerCase();
  
  if (message.includes('network') || message.includes('fetch')) {
    return ErrorCode.NETWORK_ERROR;
  }
  if (message.includes('timeout')) {
    return ErrorCode.TIMEOUT_ERROR;
  }
  if (message.includes('websocket') || message.includes('ws')) {
    return ErrorCode.WEBSOCKET_ERROR;
  }
  if (message.includes('unauthorized') || message.includes('401')) {
    return ErrorCode.UNAUTHORIZED;
  }
  if (message.includes('forbidden') || message.includes('403')) {
    return ErrorCode.FORBIDDEN;
  }
  if (message.includes('not found') || message.includes('404')) {
    return ErrorCode.NOT_FOUND;
  }
  
  return ErrorCode.UNKNOWN_ERROR;
}

/**
 * Converts error to user-friendly message
 */
function getUserFriendlyMessage(error: unknown): string {
  if (typeof error === 'string') {
    return error;
  }

  if (error instanceof Error) {
    // Check for specific error messages
    const msg = error.message.toLowerCase();
    
    if (msg.includes('network') || msg.includes('fetch')) {
      return 'Unable to connect to server. Please check your internet connection.';
    }
    if (msg.includes('timeout')) {
      return 'Request timed out. Please try again.';
    }
    if (msg.includes('websocket')) {
      return 'Connection lost. Attempting to reconnect...';
    }
    if (msg.includes('unauthorized') || msg.includes('401')) {
      return 'You are not authorized to perform this action.';
    }
    if (msg.includes('forbidden') || msg.includes('403')) {
      return 'Access denied. You do not have permission for this action.';
    }
    if (msg.includes('not found') || msg.includes('404')) {
      return 'The requested resource was not found.';
    }
    
    // Return original message if it's user-friendly
    if (error.message.length < 100 && !error.message.includes('Error:') && !error.message.includes('TypeError')) {
      return error.message;
    }
  }

  // Handle Supabase errors
  if (error && typeof error === 'object' && 'code' in error) {
    const supabaseError = error as { code?: string; message?: string };
    if (supabaseError.code === 'PGRST116') {
      return 'Resource not found.';
    }
    if (supabaseError.code === '23505') {
      return 'This record already exists.';
    }
    if (supabaseError.message) {
      return supabaseError.message;
    }
  }

  // Handle HTTP errors
  if (error && typeof error === 'object' && 'status' in error) {
    const httpError = error as { status?: number };
    if (httpError.status === 401) {
      return 'Please log in to continue.';
    }
    if (httpError.status === 403) {
      return 'You do not have permission for this action.';
    }
    if (httpError.status === 404) {
      return 'Resource not found.';
    }
    if (httpError.status === 500) {
      return 'Server error. Please try again later.';
    }
    if (httpError.status === 503) {
      return 'Service temporarily unavailable. Please try again later.';
    }
  }

  return 'An unexpected error occurred. Please try again.';
}

/**
 * Determines if error is retryable
 */
function isRetryableError(error: Error): boolean {
  const message = error.message.toLowerCase();
  const retryablePatterns = [
    'network',
    'timeout',
    'connection',
    'econnreset',
    'econnrefused',
    'etimedout',
    'enotfound',
    '503',
    '502',
    '504',
  ];
  
  return retryablePatterns.some(pattern => message.includes(pattern));
}

/**
 * Determines if Supabase error is retryable
 */
function isRetryableSupabaseError(code?: string): boolean {
  if (!code) return false;
  
  // Retryable Supabase error codes
  const retryableCodes = ['PGRST301', 'PGRST302', 'PGRST500'];
  return retryableCodes.includes(code);
}

/**
 * Retry function with exponential backoff
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    backoffMultiplier = 2,
    retryableErrors = [],
  } = options;

  let lastError: unknown;
  let delay = initialDelay;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      // Don't retry if it's the last attempt
      if (attempt === maxRetries) {
        break;
      }

      // Check if error is retryable
      const transformedError = transformError(error);
      if (!transformedError.retryable && retryableErrors.length > 0) {
        const errorCode = transformedError.code;
        if (!retryableErrors.includes(errorCode)) {
          break;
        }
      }

      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, delay));
      
      // Increase delay for next attempt (exponential backoff)
      delay = Math.min(delay * backoffMultiplier, maxDelay);
    }
  }

  throw lastError;
}

/**
 * Safe async wrapper that catches and transforms errors
 */
export async function safeExecute<T>(
  fn: () => Promise<T>,
  context?: Record<string, any>
): Promise<{ data?: T; error?: ServiceError }> {
  try {
    const data = await fn();
    return { data };
  } catch (error) {
    const transformedError = transformError(error, context);
    
    // Log error
    if (import.meta.env.DEV) {
      console.error('Service error:', transformedError);
    }
    
    return { error: transformedError };
  }
}

/**
 * Safe synchronous wrapper
 */
export function safeExecuteSync<T>(
  fn: () => T,
  context?: Record<string, any>
): { data?: T; error?: ServiceError } {
  try {
    const data = fn();
    return { data };
  } catch (error) {
    const transformedError = transformError(error, context);
    
    // Log error
    if (import.meta.env.DEV) {
      console.error('Service error:', transformedError);
    }
    
    return { error: transformedError };
  }
}

/**
 * Creates a standardized service method wrapper
 */
export function createServiceMethod<T extends (...args: any[]) => Promise<any>>(
  method: T,
  methodName: string
): T {
  return (async (...args: Parameters<T>) => {
    try {
      return await method(...args);
    } catch (error) {
      const transformedError = transformError(error, {
        method: methodName,
        args: import.meta.env.DEV ? args : undefined,
      });
      
      // Log error
      console.error(`[${methodName}] Error:`, transformedError);
      
      // Re-throw as ServiceError
      throw transformedError;
    }
  }) as T;
}






