import type { ReactNode, CSSProperties } from 'react';

interface Props {
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  accentColor?: string;
}

export default function GlassCard({ children, style, className = '', accentColor }: Props) {
  return (
    <div
      className={`glass-card ${className}`}
      style={accentColor ? ({ '--card-accent': accentColor, ...style } as CSSProperties) : style}
    >
      {children}
    </div>
  );
}
