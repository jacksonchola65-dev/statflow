import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const COLORS = ['#6366f1', '#818cf8', '#34d399', '#f59e0b', '#fb7185']

export default function AreaVisualization({ data, legendVisible = true, stacked = false }) {
  return (
    <div className="h-[360px] w-full overflow-hidden rounded-2xl border border-white/10 bg-slate-950/40 p-3">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="#ffffff0a" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#ffffff12" />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#ffffff12" />
          <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.10)', borderRadius: 10, color: '#f1f5f9' }} />
          {legendVisible && <Legend />}
          {Object.keys(data[0] || {}).filter((key) => key !== 'name').map((key, index) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[index % COLORS.length]}
              fill={COLORS[index % COLORS.length]}
              fillOpacity={0.25}
              stackId={stacked ? 'series' : undefined}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
