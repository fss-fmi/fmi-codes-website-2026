import { useEffect, useRef } from 'react';

/**
 * Observes elements with the given selector and adds .visible class
 * when they enter the viewport.
 * Pass `resetKey` to re-run the observer after async data loads (e.g. data.length).
 */
export function useScrollReveal(selector: string = '.reveal', resetKey?: unknown) {
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
  }, [selector, resetKey]);
}
