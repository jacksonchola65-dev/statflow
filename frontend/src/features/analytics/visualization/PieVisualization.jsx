import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Legend } from 'recharts'

const COLORS = ['#6366f1', '#818cf8', '#34d399', '#f59e0b', '#fb7185', '#38bdf8']

export default function PieVisualization({ data, legendVisible = true }) {
  return (
    <div className="h-[360px] w-full overflow-hidden rounded-2xl border border-white/10 bg-slate-950/40 p-3">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={110}
            innerRadius={70}
            label
          >
            {data.map((entry, index) => (
              <Cell key={`${entry.name}-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.10)', borderRadius: 10, color: '#f1f5f9' }} />
          {legendVisible && <Legend />}
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
