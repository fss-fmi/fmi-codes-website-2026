import type { ReactNode, CSSProperties, ElementType } from 'react';

interface Props {
  title?: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: ElementType;
}

export default function Panel({ title, children, className = '', style, as: Tag = 'section' }: Props) {
  const Component = Tag;
  return (
    <Component
      className={`px-panel-outer ${className}`.trim()}
      style={style}
    >
      {title ? <h2 className="px-prompt-heading">{title}</h2> : null}
      {children}
    </Component>
  );
}
