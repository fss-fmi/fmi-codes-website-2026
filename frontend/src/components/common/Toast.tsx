import { useEffect, useState } from 'react';

interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  onClose: () => void;
  duration?: number;
}

export default function Toast({ message, type = 'success', onClose, duration = 3500 }: ToastProps) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setLeaving(true), duration - 400);
    const t2 = setTimeout(onClose, duration);
    return () => {
      clearTimeout(t);
      clearTimeout(t2);
    };
  }, [duration, onClose]);

  const colors: Record<string, string> = {
    success: 'rgba(52,211,153,0.15)',
    error: 'rgba(239,68,68,0.15)',
    info: 'rgba(96,165,250,0.15)',
  };
  const borders: Record<string, string> = {
    success: 'rgba(52,211,153,0.35)',
    error: 'rgba(239,68,68,0.35)',
    info: 'rgba(96,165,250,0.35)',
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 9999,
        background: colors[type],
        border: `1px solid ${borders[type]}`,
        borderRadius: '12px',
        padding: '14px 20px',
        color: 'var(--text)',
        fontSize: '0.9rem',
        fontWeight: 500,
        maxWidth: '360px',
        backdropFilter: 'blur(12px)',
        animation: `${leaving ? 'toastOut' : 'toastIn'} 0.35s ease both`,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      {message}
    </div>
  );
}

// Hook for managing toasts
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const [toast, setToast] = useState<{
    message: string;
    type?: 'success' | 'error' | 'info';
  } | null>(null);

  function showToast(message: string, type: 'success' | 'error' | 'info' = 'success') {
    setToast({ message, type });
  }

  function clearToast() {
    setToast(null);
  }

  return { toast, showToast, clearToast };
}
