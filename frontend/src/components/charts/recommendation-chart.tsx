import { useMemo } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useTheme } from '@/contexts/theme-context';
import { tooltipStyle } from '@/utils/chart-theme';
import type { ChartDataPoint } from '@/types/analytics';

function toNumericValue(value: number | string | ReadonlyArray<number | string> | undefined): number {
  if (Array.isArray(value)) return toNumericValue(value[0]);
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

const COLORS: Record<string, string> = {
  STRONG_APPLY: '#3F6B54',
  APPLY: '#7FB393',
  MAYBE: '#E0872F',
  SKIP: '#9CA3AF',
};

const LABELS: Record<string, string> = {
  STRONG_APPLY: 'Strong Apply',
  APPLY: 'Apply',
  MAYBE: 'Maybe',
  SKIP: 'Skip',
};

interface RecommendationChartProps {
  data: ChartDataPoint[];
}

export function RecommendationChart({ data }: RecommendationChartProps) {
  const { resolved } = useTheme();
  const chartData = useMemo(
    () => data.map((d) => ({ ...d, name: LABELS[d.label] || d.label })),
    [data],
  );
  const total = useMemo(() => data.reduce((sum, d) => sum + d.value, 0), [data]);
  const legendColor = resolved === 'dark' ? '#D4D4D8' : '#334155';
  const centerColor = resolved === 'dark' ? '#FAFAFA' : '#0F172A';
  const centerSubColor = resolved === 'dark' ? '#A1A1AA' : '#94A3B8';

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={65}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          stroke="none"
        >
          {chartData.map((entry) => (
            // Warm palette wins over any stale color carried on the data point.
            <Cell key={entry.label} fill={COLORS[entry.label] || entry.color || '#3F6B54'} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={tooltipStyle()}
          formatter={(value: number | string | ReadonlyArray<number | string> | undefined, name: number | string | undefined) => {
            const numericValue = toNumericValue(value);
            return [
              `${numericValue} (${total > 0 ? Math.round((numericValue / total) * 100) : 0}%)`,
              String(name ?? ''),
            ];
          }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value: string) => <span style={{ color: legendColor, fontSize: 12 }}>{value}</span>}
        />
        <text x="50%" y="46%" textAnchor="middle" dominantBaseline="central" style={{ fontSize: 22, fontWeight: 700, fill: centerColor }}>
          {total}
        </text>
        <text x="50%" y="58%" textAnchor="middle" dominantBaseline="central" style={{ fontSize: 11, fill: centerSubColor }}>
          scored
        </text>
      </PieChart>
    </ResponsiveContainer>
  );
}
