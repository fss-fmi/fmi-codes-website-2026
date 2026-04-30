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
      className="glass-card"
      style={{ padding: '20px 24px' }}
    >
      {title && (
        <p
          style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            color: 'var(--muted)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: '12px',
          }}
        >
          {title}
        </p>
      )}
      <ResponsiveContainer
        width="100%"
        height={200}
      >
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
              <Cell
                key={i}
                fill={d.color}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: 'rgba(15,23,42,0.9)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px',
              color: '#e2e8f0',
            }}
            formatter={(val: number, name: string) => [val, name]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          marginTop: '8px',
          justifyContent: 'center',
        }}
      >
        {data.map((d, i) => (
          <span
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '0.75rem',
              color: 'var(--muted)',
            }}
          >
            <span
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '3px',
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
