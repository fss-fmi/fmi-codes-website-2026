import { useEffect, useRef } from 'react';

interface Props {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  dangerous?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'CONFIRM',
  cancelLabel = 'CANCEL',
  dangerous = false,
  onConfirm,
  onCancel,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      try {
        dialog.showModal();
      } catch {
        /* jsdom / older browsers */
      }
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const handleCancel = (e: Event) => {
      e.preventDefault();
      onCancel();
    };
    dialog.addEventListener('cancel', handleCancel);
    return () => dialog.removeEventListener('cancel', handleCancel);
  }, [onCancel]);

  return (
    <dialog
      ref={dialogRef}
      onClick={(e) => {
        if (e.target === dialogRef.current) onCancel();
      }}
      style={{
        background: 'var(--px-bg-panel)',
        border: '2px solid var(--px-teal-border)',
        borderRadius: 0,
        padding: 0,
        color: 'var(--px-white)',
        maxWidth: '480px',
        width: 'calc(100% - 32px)',
      }}
    >
      <div style={{ padding: '24px' }}>
        <h2 className="px-prompt-heading" style={{ marginBottom: '12px' }}>
          {title}
        </h2>
        {description ? (
          <p className="px-body-sm" style={{ margin: '0 0 24px 0' }}>
            {description}
          </p>
        ) : null}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="px-btn-ghost"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          {dangerous ? (
            <button
              type="button"
              className="px-btn-danger"
              onClick={onConfirm}
              autoFocus
            >
              {confirmLabel}
            </button>
          ) : (
            <button
              type="button"
              className="px-btn-primary"
              onClick={onConfirm}
              autoFocus
            >
              {confirmLabel}
            </button>
          )}
        </div>
      </div>
    </dialog>
  );
}
