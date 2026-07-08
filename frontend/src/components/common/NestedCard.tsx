import type { ReactNode, CSSProperties, HTMLAttributes } from 'react';

interface Props extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export default function NestedCard({ title, children, className = '', style, ...rest }: Props) {
  return (
    <div
      className={`px-card-nested ${className}`.trim()}
      style={style}
      {...rest}
    >
      {title ? <h3 className="px-prompt-heading" style={{ fontSize: '0.75rem', margin: '0 0 16px 0' }}>{title}</h3> : null}
      {children}
    </div>
  );
}
