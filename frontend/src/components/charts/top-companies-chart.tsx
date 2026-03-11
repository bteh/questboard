import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { getChartTheme, tooltipStyle } from '@/utils/chart-theme';
import type { ChartDataPoint } from '@/types/analytics';

interface TopCompaniesChartProps {
  data: ChartDataPoint[];
}

export function TopCompaniesChart({ data }: TopCompaniesChartProps) {
  const theme = getChartTheme();
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 100, bottom: 5 }}>
        <XAxis type="number" tick={{ fontSize: 12, fill: theme.axis }} />
        <YAxis dataKey="label" type="category" tick={{ fontSize: 12, fill: theme.axis }} width={95} />
        <Tooltip contentStyle={tooltipStyle()} />
        <Bar dataKey="value" fill="#10B981" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
