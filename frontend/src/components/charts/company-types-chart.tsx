import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { getChartTheme, tooltipStyle } from '@/utils/chart-theme';
import type { ChartDataPoint } from '@/types/analytics';

const TYPE_COLORS: Record<string, string> = {
  'FAANG+': '#E0872F',
  'Big Tech': '#C06A3C',
  'Elite Startup': '#4E8A8F',
  'Growth Stage': '#4C8A63',
  'Early Startup': '#8FA054',
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
            <Cell key={entry.label} fill={entry.color || TYPE_COLORS[entry.label] || '#3F6B54'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
