import { useMemo } from 'react';
import type { ChartDataPoint } from '@/types/analytics';

const STAGE_CONFIG: Record<string, { color: string; label: string }> = {
  found:        { color: '#6366F1', label: 'Found' },
  reviewed:     { color: '#818CF8', label: 'Reviewed' },
  applying:     { color: '#F59E0B', label: 'Applying' },
  applied:      { color: '#3B82F6', label: 'Applied' },
  interviewing: { color: '#10B981', label: 'Interviewing' },
  offer:        { color: '#059669', label: 'Offer' },
};

interface FunnelChartProps {
  data: ChartDataPoint[];
}

export function FunnelChart({ data }: FunnelChartProps) {
  const stages = useMemo(() => {
    const maxValue = Math.max(...data.map((d) => d.value), 1);
    return data.map((d, i) => {
      const config = STAGE_CONFIG[d.label] || { color: '#94A3B8', label: d.label };
      const prevValue = i > 0 ? data[i - 1].value : null;
      const conversionRate = prevValue && prevValue > 0
        ? Math.round((d.value / prevValue) * 100)
        : null;
      const widthPct = Math.max((d.value / maxValue) * 100, d.value > 0 ? 3 : 0);
      return { ...d, ...config, conversionRate, widthPct };
    });
  }, [data]);

  return (
    <div className="space-y-2 py-2">
      {stages.map((stage) => (
        <div key={stage.label} className="flex items-center gap-3">
          <div className="w-[90px] shrink-0 text-right">
            <span className="text-xs font-medium text-text-secondary">{STAGE_CONFIG[stage.label]?.label || stage.label}</span>
          </div>
          <div className="flex-1 flex items-center gap-2">
            <div className="flex-1 h-7 rounded-md bg-bg-muted overflow-hidden">
              <div
                className="h-full rounded-md transition-all duration-500 flex items-center px-2"
                style={{ width: `${stage.widthPct}%`, backgroundColor: stage.color }}
              >
                {stage.value > 0 && (
                  <span className="text-[11px] font-semibold text-white tabular-nums whitespace-nowrap">
                    {stage.value.toLocaleString()}
                  </span>
                )}
              </div>
            </div>
            {stage.conversionRate !== null && (
              <span className="text-[10px] text-text-muted tabular-nums w-10 shrink-0">
                {stage.conversionRate}%
              </span>
            )}
          </div>
        </div>
      ))}
      {stages.length >= 2 && stages[stages.length - 1].conversionRate !== null && (
        <p className="text-[11px] text-text-muted text-center pt-2">
          Percentages show stage-to-stage conversion rates
        </p>
      )}
    </div>
  );
}
