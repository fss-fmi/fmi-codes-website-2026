import { useRef, type ReactNode } from 'react';
import { useSpotlight } from '@/hooks/useVisuals';

export default function Layout({ children }: { children: ReactNode }) {
  const spotlightRef = useRef<HTMLDivElement>(null);
  useSpotlight(spotlightRef);

  return (
    <>
      {/* Background layers */}
      <div
        className="dot-grid"
        aria-hidden="true"
      />
      <div
        className="spotlight"
        ref={spotlightRef}
        aria-hidden="true"
      />
      <div
        className="blobs"
        aria-hidden="true"
      >
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>
      <div
        className="noise"
        aria-hidden="true"
      />

      {/* Page content */}
      <div className="page-wrap">{children}</div>
    </>
  );
}
