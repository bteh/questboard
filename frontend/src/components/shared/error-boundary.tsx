import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** When this key changes (e.g. on route navigation), the error
   *  state resets automatically so users aren't stuck on the error
   *  screen after navigating away from a broken page. */
  resetKey?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  /** Track the resetKey that was active when the error occurred.
   *  When the prop changes, we know the user navigated away. */
  prevResetKey?: string;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, prevResetKey: props.resetKey };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    // If the resetKey changed (user navigated), clear the error
    if (props.resetKey !== state.prevResetKey) {
      return { hasError: false, error: null, prevResetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
          <div className="max-w-md text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-danger/15">
              <AlertTriangle className="h-6 w-6 text-danger" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary mb-2">Something went wrong</h2>
            <p className="text-sm text-text-secondary mb-1">
              An unexpected error occurred. This has been logged.
            </p>
            {this.state.error && (
              <p className="text-xs text-text-muted font-mono bg-bg-muted rounded-lg px-3 py-2 mb-4 break-all">
                {this.state.error.message}
              </p>
            )}
            <div className="flex justify-center gap-3">
              <Button variant="outline" size="sm" onClick={this.handleReset}>
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                Try Again
              </Button>
              <Button size="sm" onClick={() => window.location.reload()}>
                Reload Page
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
