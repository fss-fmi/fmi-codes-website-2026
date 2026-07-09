import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export type ToastKind = 'success' | 'warning' | 'danger' | 'info';

export interface ToastPayload {
  kind?: ToastKind;
  message: string;
  duration?: number;
}

interface ToastEntry extends Required<Pick<ToastPayload, 'kind' | 'message'>> {
  id: number;
  duration: number;
  leaving: boolean;
}

interface ToastCtx {
  showToast: (t: ToastPayload) => void;
}

const Ctx = createContext<ToastCtx | null>(null);

const DURATION_DEFAULTS: Record<ToastKind, number> = {
  success: 4000,
  info: 4000,
  warning: 6000,
  danger: 8000,
};

const BORDER_COLORS: Record<ToastKind, string> = {
  success: 'var(--px-green)',
  info: 'var(--px-teal)',
  warning: 'var(--px-amber)',
  danger: 'var(--px-danger)',
};

let idCounter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>[]>>(new Map());

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timers = timersRef.current.get(id);
    if (timers) {
      timers.forEach(clearTimeout);
      timersRef.current.delete(id);
    }
  }, []);

  const beginLeave = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
  }, []);

  const showToast = useCallback(
    ({ kind = 'info', message, duration }: ToastPayload) => {
      const id = ++idCounter;
      const finalDuration = duration ?? DURATION_DEFAULTS[kind];
      setToasts((prev) => [...prev, { id, kind, message, duration: finalDuration, leaving: false }]);
      const leaveTimer = setTimeout(() => beginLeave(id), Math.max(0, finalDuration - 220));
      const removeTimer = setTimeout(() => remove(id), finalDuration);
      timersRef.current.set(id, [leaveTimer, removeTimer]);
    },
    [beginLeave, remove],
  );

  useEffect(() => {
    const currentTimers = timersRef.current;
    return () => {
      currentTimers.forEach((timers) => timers.forEach(clearTimeout));
      currentTimers.clear();
    };
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          pointerEvents: 'none',
        }}
      >
        {toasts.map((t) => {
          const isAlert = t.kind === 'warning' || t.kind === 'danger';
          return (
            <div
              key={t.id}
              role={isAlert ? 'alert' : 'status'}
              aria-live={isAlert ? 'assertive' : 'polite'}
              style={{
                background: 'var(--px-bg-panel)',
                borderTop: '1px solid var(--px-teal-dim)',
                borderRight: '1px solid var(--px-teal-dim)',
                borderBottom: '1px solid var(--px-teal-dim)',
                borderLeft: `2px solid ${BORDER_COLORS[t.kind]}`,
                borderRadius: 0,
                padding: '16px 20px',
                color: 'var(--px-white)',
                fontFamily: 'var(--px-mono)',
                fontSize: '0.85rem',
                lineHeight: 1.5,
                maxWidth: '360px',
                pointerEvents: 'auto',
                animation: `${t.leaving ? 'toastOut' : 'toastIn'} 220ms var(--px-ease) both`,
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
              }}
            >
              <span style={{ flex: 1 }}>{t.message}</span>
              <button
                onClick={() => remove(t.id)}
                aria-label="Dismiss notification"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--px-muted-strong)',
                  fontFamily: 'var(--px-font)',
                  fontSize: '0.55rem',
                  cursor: 'pointer',
                  padding: '2px 6px',
                }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastCtx {
  const ctx = useContext(Ctx);
  if (!ctx) {
    // Graceful fallback — allows components to render outside a provider without crashing.
    return {
      showToast: ({ message }) => {
        if (typeof console !== 'undefined') {
          console.warn('[useToast] no provider mounted; message dropped:', message);
        }
      },
    };
  }
  return ctx;
}
