import { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useTheme } from '@/contexts/theme-context';
import { getChartTheme, tooltipStyle } from '@/utils/chart-theme';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import type { ChartDataPoint } from '@/types/analytics';

const BAR_COLORS = [
  '#6366F1', '#818CF8', '#3B82F6', '#06B6D4', '#10B981',
  '#F59E0B', '#EF4444', '#EC4899', '#8B5CF6', '#14B8A6',
  '#F97316', '#64748B', '#A855F7', '#059669', '#4F46E5',
];

interface SourceChartProps {
  data: ChartDataPoint[];
}

export function SourceChart({ data }: SourceChartProps) {
  const { resolved } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- resolved triggers re-read of CSS variables
  const theme = useMemo(() => getChartTheme(), [resolved]);
  const labels = useSourceLabels();

  const chartData = useMemo(
    () =>
      [...data]
        .sort((a, b) => b.value - a.value)
        .map((d) => ({
          ...d,
          name: resolveSourceLabel(d.label, labels),
        })),
    [data, labels],
  );

  const dynamicHeight = Math.max(280, chartData.length * 34);

  return (
    <ResponsiveContainer width="100%" height={dynamicHeight}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <XAxis type="number" tick={{ fontSize: 12, fill: theme.axis }} />
        <YAxis
          dataKey="name"
          type="category"
          tick={{ fontSize: 12, fill: theme.axis }}
          width={100}
        />
        <Tooltip
          contentStyle={tooltipStyle()}
          formatter={(value: number) => [`${value.toLocaleString()} jobs`, 'Count']}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
          {chartData.map((_, index) => (
            <Cell key={index} fill={BAR_COLORS[index % BAR_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
