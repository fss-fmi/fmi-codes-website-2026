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
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            gap: 16,
          }}
        >
          <h2 style={{ color: 'var(--text)', fontSize: '1.5rem', fontWeight: 700 }}>
            Something went wrong
          </h2>
          <p style={{ color: 'var(--muted)' }}>Try refreshing the page or navigate away.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="btn btn-primary"
          >
            Try again
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
