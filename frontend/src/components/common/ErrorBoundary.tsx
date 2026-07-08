import { Component, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

interface Props {
  children: ReactNode;
  resetKey: string;
}
interface State {
  hasError: boolean;
}

class ErrorBoundaryInner extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: Props) {
    // Reset when the route changes so navigating away always shows the new page
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            gap: 16,
            padding: 24,
          }}
        >
          <h2 className="px-prompt-heading">SOMETHING WENT WRONG</h2>
          <p className="px-body" style={{ color: 'var(--px-muted-strong)' }}>
            &gt; Try refreshing the page or navigate away.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            className="px-btn-primary"
          >
            TRY AGAIN
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/** Wraps children in an error boundary that auto-resets on route change. */
export default function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundaryInner resetKey={location.pathname}>{children}</ErrorBoundaryInner>;
}
