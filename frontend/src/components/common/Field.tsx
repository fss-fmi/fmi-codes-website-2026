import { cloneElement, isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';

interface Props {
  id: string;
  label: string;
  error?: string | null;
  hint?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}

interface InjectedProps {
  id?: string;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string;
  'aria-required'?: boolean;
}

export default function Field({ id, label, error, hint, required, children, className = '' }: Props) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;

  let control: ReactNode = children;
  if (isValidElement(children)) {
    const injected: InjectedProps = {
      id,
      'aria-invalid': error ? true : undefined,
      'aria-describedby': describedBy,
      'aria-required': required || undefined,
    };
    control = cloneElement(children as ReactElement<InjectedProps>, injected);
  }

  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <label htmlFor={id} className="px-label">
        {label}
        {required ? <span style={{ color: 'var(--px-salmon)', marginLeft: '4px' }}>*</span> : null}
      </label>
      {control}
      {error ? (
        <p
          id={`${id}-error`}
          role="alert"
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.8rem',
            color: 'var(--px-danger)',
            margin: 0,
          }}
        >
          {error}
        </p>
      ) : hint ? (
        <p
          id={`${id}-hint`}
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.75rem',
            color: 'var(--px-muted)',
            margin: 0,
          }}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}
