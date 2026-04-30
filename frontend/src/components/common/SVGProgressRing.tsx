interface Props {
  size?: number;
  value: number; // 0–1
  strokeColor?: string;
  trackColor?: string;
  strokeWidth?: number;
}

export default function SVGProgressRing({
  size = 60,
  value,
  strokeColor = '#60a5fa',
  trackColor = 'rgba(96,165,250,0.15)',
  strokeWidth = 5,
}: Props) {
  const r = (size - strokeWidth * 2) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(1, Math.max(0, value)));
  const cx = size / 2;

  return (
    <svg
      width={size}
      height={size}
      style={{ transform: 'rotate(-90deg)' }}
    >
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeWidth}
      />
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
    </svg>
  );
}
