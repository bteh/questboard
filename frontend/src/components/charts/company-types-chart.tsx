import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { getChartTheme, tooltipStyle } from '@/utils/chart-theme';
import type { ChartDataPoint } from '@/types/analytics';

const TYPE_COLORS: Record<string, string> = {
  'FAANG+': '#F59E0B',
  'Big Tech': '#3B82F6',
  'Elite Startup': '#6366F1',
  'Growth Stage': '#10B981',
  'Early Startup': '#34D399',
  'Midsize': '#94A3B8',
  'Enterprise': '#64748B',
  'Unknown': '#CBD5E1',
};

interface CompanyTypesChartProps {
  data: ChartDataPoint[];
}

export function CompanyTypesChart({ data }: CompanyTypesChartProps) {
  const theme = getChartTheme();
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 100, bottom: 5 }}>
        <XAxis type="number" tick={{ fontSize: 12, fill: theme.axis }} />
        <YAxis dataKey="label" type="category" tick={{ fontSize: 12, fill: theme.axis }} width={95} />
        <Tooltip contentStyle={tooltipStyle()} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((entry) => (
            <Cell key={entry.label} fill={entry.color || TYPE_COLORS[entry.label] || '#4F46E5'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
