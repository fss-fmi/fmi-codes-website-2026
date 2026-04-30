import { useEffect, useRef } from 'react';

/**
 * Tracks mouse position and updates --mx / --my CSS vars on the spotlight div.
 */
export function useSpotlight(spotlightRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = spotlightRef.current;
    if (!el) return;

    let rafId: number;
    const onMouseMove = (e: MouseEvent) => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        el.style.setProperty('--mx', `${e.clientX}px`);
        el.style.setProperty('--my', `${e.clientY}px`);
      });
    };

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      cancelAnimationFrame(rafId);
    };
  }, [spotlightRef]);
}

/**
 * Observes elements with the given selector and adds .visible class
 * when they enter the viewport.
 */
export function useScrollReveal(selector: string = '.reveal') {
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>(selector);
    if (!targets.length) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observerRef.current?.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 },
    );

    targets.forEach((el) => observerRef.current!.observe(el));

    return () => observerRef.current?.disconnect();
  }, [selector]);
}
