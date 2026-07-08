import { useMemo, type ReactNode } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useTheme } from '@/contexts/theme-context';
import { getChartTheme, tooltipStyle } from '@/utils/chart-theme';
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

/* Ink and the canon hues: sage for strong, ochre for apply, clay for maybe,
   warm ink-gray for the rest. Same buckets as the recommendation thresholds. */
function barColor(label: string): string {
  const rangeStart = parseInt(label, 10);
  if (isNaN(rangeStart)) return '#3F6B54';
  if (rangeStart >= 70) return '#3F6B54';   // sage
  if (rangeStart >= 55) return '#8A6A1F';   // ochre
  if (rangeStart >= 40) return '#A6522E';   // clay
  return '#82817D';                          // muted ink
}

interface ScoreDistributionChartProps {
  data: ChartDataPoint[];
}

export function ScoreDistributionChart({ data }: ScoreDistributionChartProps) {
  const { resolved } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- resolved triggers re-read of CSS variables
  const theme = useMemo(() => getChartTheme(), [resolved]);
  const coloredData = useMemo(
    () => data.map((d) => ({ ...d, fill: barColor(d.label) })),
    [data],
  );

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={coloredData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 12, fill: theme.axis }} axisLine={{ stroke: theme.axisLine }} />
        <YAxis tick={{ fontSize: 12, fill: theme.axis }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={tooltipStyle()}
          formatter={(value: number | string | ReadonlyArray<number | string> | undefined) => [`${toNumericValue(value).toLocaleString()} jobs`, 'Count']}
          labelFormatter={(label: ReactNode) => `Score range: ${String(label ?? '')}`}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {coloredData.map((entry, i) => (
            <Cell key={i} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
