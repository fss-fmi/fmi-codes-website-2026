import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

interface DataItem {
  name: string;
  value: number;
  color: string;
}

interface Props {
  data: DataItem[];
  title?: string;
}

export default function DonutChart({ data, title }: Props) {
  return (
    <div
      style={{
        background: 'var(--px-bg-panel)',
        border: '2px solid var(--px-teal-border)',
        padding: '24px',
      }}
    >
      {title && <p className="px-prompt-heading" style={{ marginBottom: '16px' }}>{title}</p>}
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            dataKey="value"
            paddingAngle={3}
          >
            {data.map((d, i) => (
              <Cell key={i} fill={d.color} stroke="var(--px-bg-panel)" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: 'var(--px-bg)',
              border: '1px solid var(--px-teal-border)',
              borderRadius: 0,
              color: 'var(--px-white)',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.8rem',
            }}
            formatter={(val: number, name: string) => [val, name]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '10px',
          marginTop: '12px',
          justifyContent: 'center',
        }}
      >
        {data.map((d, i) => (
          <span
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.75rem',
              color: 'var(--px-muted-strong)',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: '10px',
                height: '10px',
                background: d.color,
                flexShrink: 0,
              }}
            />
            {d.name}: {d.value}
          </span>
        ))}
      </div>
    </div>
  );
}
