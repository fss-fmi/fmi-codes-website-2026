interface Props {
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}

export default function GradientText({ children, style, className = '' }: Props) {
  return (
    <span
      className={`gradient-text ${className}`}
      style={style}
    >
      {children}
    </span>
  );
}
