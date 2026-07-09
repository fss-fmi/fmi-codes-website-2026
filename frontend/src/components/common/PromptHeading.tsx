import type { ReactNode, CSSProperties } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: 'h1' | 'h2' | 'h3' | 'h4';
}

export default function PromptHeading({ children, className = '', style, as: Tag = 'h2' }: Props) {
  return (
    <Tag
      className={`px-prompt-heading ${className}`.trim()}
      style={style}
    >
      {children}
    </Tag>
  );
}

export function PageTitle({ children, className = '', style }: Omit<Props, 'as'>) {
  return (
    <h1
      className={`px-page-title ${className}`.trim()}
      style={style}
    >
      {children}
    </h1>
  );
}
