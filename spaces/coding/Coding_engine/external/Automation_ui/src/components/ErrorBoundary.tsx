import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, Home, Bug } from 'lucide-react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  showDetails?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorId: string | null;
}

/**
 * Error Boundary Component
 * 
 * Catches JavaScript errors anywhere in the child component tree,
 * logs those errors, and displays a fallback UI instead of crashing.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Generate unique error ID for tracking
    const errorId = `error-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    return {
      hasError: true,
      error,
      errorId,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error to console for debugging
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Store error info
    this.setState({
      errorInfo,
    });

    // Log error to error service
    this.logError(error, errorInfo);

    // Call custom error handler if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  private logError = (error: Error, errorInfo: ErrorInfo) => {
    const errorData = {
      id: this.state.errorId,
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      userAgent: navigator.userAgent,
      url: window.location.href,
    };

    // Log to console in development
    if (import.meta.env.DEV) {
      console.group('🚨 Error Details');
      console.error('Error:', error);
      console.error('Error Info:', errorInfo);
      console.error('Error Data:', errorData);
      console.groupEnd();
    }

    // In production, send to error logging service
    // TODO: Integrate with error tracking service (e.g., Sentry, LogRocket)
    if (import.meta.env.PROD) {
      // Example: Send to backend API
      // fetch('/api/errors', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(errorData),
      // }).catch(console.error);
    }

    // Store in localStorage for debugging (last 5 errors)
    try {
      const storedErrors = JSON.parse(localStorage.getItem('app_errors') || '[]');
      storedErrors.unshift(errorData);
      const recentErrors = storedErrors.slice(0, 5);
      localStorage.setItem('app_errors', JSON.stringify(recentErrors));
    } catch (e) {
      console.error('Failed to store error in localStorage:', e);
    }
  };

  private handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    });
  };

  private handleReload = () => {
    window.location.reload();
  };

  private handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-destructive/10 p-2">
                  <AlertCircle className="h-6 w-6 text-destructive" />
                </div>
                <div className="flex-1">
                  <CardTitle>Something went wrong</CardTitle>
                  <CardDescription>
                    We encountered an unexpected error. Don't worry, your data is safe.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-muted rounded-lg p-4 space-y-2">
                <p className="text-sm font-medium text-foreground">
                  Error ID: <code className="text-xs bg-background px-1.5 py-0.5 rounded">{this.state.errorId}</code>
                </p>
                {this.state.error && (
                  <p className="text-sm text-muted-foreground">
                    {this.state.error.message || 'An unknown error occurred'}
                  </p>
                )}
              </div>

              {this.props.showDetails && this.state.error && (
                <details className="bg-muted rounded-lg p-4">
                  <summary className="cursor-pointer text-sm font-medium text-foreground mb-2">
                    Technical Details
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground mb-1">Error Message:</p>
                      <pre className="text-xs bg-background p-2 rounded overflow-auto max-h-32">
                        {this.state.error.message}
                      </pre>
                    </div>
                    {this.state.error.stack && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-1">Stack Trace:</p>
                        <pre className="text-xs bg-background p-2 rounded overflow-auto max-h-48">
                          {this.state.error.stack}
                        </pre>
                      </div>
                    )}
                    {this.state.errorInfo?.componentStack && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-1">Component Stack:</p>
                        <pre className="text-xs bg-background p-2 rounded overflow-auto max-h-48">
                          {this.state.errorInfo.componentStack}
                        </pre>
                      </div>
                    )}
                  </div>
                </details>
              )}

              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Bug className="h-4 w-4" />
                <span>
                  Error details have been logged. If this problem persists, please contact support with the Error ID above.
                </span>
              </div>
            </CardContent>
            <CardFooter className="flex flex-col sm:flex-row gap-2">
              <Button onClick={this.handleReset} variant="default" className="flex-1 sm:flex-none">
                <RefreshCw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
              <Button onClick={this.handleGoHome} variant="outline" className="flex-1 sm:flex-none">
                <Home className="h-4 w-4 mr-2" />
                Go Home
              </Button>
              <Button onClick={this.handleReload} variant="outline" className="flex-1 sm:flex-none">
                <RefreshCw className="h-4 w-4 mr-2" />
                Reload Page
              </Button>
            </CardFooter>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * HOC for wrapping components with ErrorBoundary
 */
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<Props, 'children'>
) {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name || 'Component'})`;

  return WrappedComponent;
}

/**
 * Hook for programmatic error logging
 */
export function useErrorLogger() {
  const logError = React.useCallback((error: Error | string, context?: Record<string, any>) => {
    const errorObj = typeof error === 'string' ? new Error(error) : error;
    
    const errorData = {
      message: errorObj.message,
      stack: errorObj.stack,
      context,
      timestamp: new Date().toISOString(),
      url: window.location.href,
    };

    console.error('Error logged:', errorData);

    // Store in localStorage for debugging
    try {
      const storedErrors = JSON.parse(localStorage.getItem('app_errors') || '[]');
      storedErrors.unshift(errorData);
      const recentErrors = storedErrors.slice(0, 5);
      localStorage.setItem('app_errors', JSON.stringify(recentErrors));
    } catch (e) {
      console.error('Failed to store error:', e);
    }

    // In production, send to error tracking service
    if (import.meta.env.PROD) {
      // TODO: Integrate with error tracking service
    }
  }, []);

  return { logError };
}

export default ErrorBoundary;






