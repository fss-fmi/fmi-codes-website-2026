import { useState } from 'react';
import { useToast } from '@/components/common/useToast';

interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  dangerous?: boolean;
  /** The async side effect to run once the user confirms. */
  action: () => Promise<void>;
  /** Optional toast shown on success. */
  successMessage?: string;
  /** Run after the action resolves (e.g. refetch). */
  onDone?: () => void;
}

interface DialogState {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  dangerous?: boolean;
  onConfirm: () => void;
}

const CLOSED: DialogState = { open: false, title: '', onConfirm: () => {} };

/**
 * Owns a single ConfirmDialog's state plus the close → run → toast → catch
 * sequencing that every destructive team action repeated by hand. Callers
 * describe the action; the hook handles the dialog lifecycle and error toast.
 */
export function useConfirmAction() {
  const { showToast } = useToast();
  const [dialog, setDialog] = useState<DialogState>(CLOSED);

  function confirm(opts: ConfirmOptions) {
    setDialog({
      open: true,
      title: opts.title,
      description: opts.description,
      confirmLabel: opts.confirmLabel,
      dangerous: opts.dangerous,
      onConfirm: async () => {
        setDialog(CLOSED);
        try {
          await opts.action();
          if (opts.successMessage) {
            showToast({ kind: 'success', message: opts.successMessage });
          }
          opts.onDone?.();
        } catch (e) {
          showToast({ kind: 'danger', message: (e as Error).message || 'Failed.' });
        }
      },
    });
  }

  const dialogProps = {
    open: dialog.open,
    title: dialog.title,
    description: dialog.description,
    confirmLabel: dialog.confirmLabel,
    dangerous: dialog.dangerous,
    onConfirm: dialog.onConfirm,
    onCancel: () => setDialog(CLOSED),
  };

  return { confirm, dialogProps };
}
