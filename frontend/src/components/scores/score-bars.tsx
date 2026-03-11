import { SCORE_DIMENSIONS } from '@/utils/constants';
import { scoreColor, scoreColorHex } from '@/utils/colors';
import type { ApplicationResponse } from '@/types/application';

interface ScoreBarsProps {
  app: ApplicationResponse;
}

const GRADIENT_MAP: Record<ReturnType<typeof scoreColor>, string> = {
  high: 'linear-gradient(90deg, #34D399, #10B981)',
  'mid-high': 'linear-gradient(90deg, #93C5FD, #3B82F6)',
  mid: 'linear-gradient(90deg, #FCD34D, #F59E0B)',
  low: 'linear-gradient(90deg, #FCA5A5, #EF4444)',
};

export function ScoreBars({ app }: ScoreBarsProps) {
  return (
    <div className="space-y-2.5">
      {SCORE_DIMENSIONS.map(({ key, label, tooltip, weight }, index) => {
        const value = (app as unknown as Record<string, unknown>)[key] as number | null;
        const pct = value != null ? Math.min(value, 100) : 0;
        const level = scoreColor(value);
        return (
          <div key={key} className="flex items-center gap-3">
            <div className="w-[140px] shrink-0 text-xs text-text-secondary" title={tooltip}>
              {label}
              <span className="text-text-muted ml-1 text-[10px]">{Math.round(weight * 100)}%</span>
            </div>
            <div className="flex-1 h-2.5 rounded-full bg-bg-muted overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${pct}%`,
                  background: GRADIENT_MAP[level],
                  transition: `width 700ms cubic-bezier(0.4,0,0.2,1) ${index * 50}ms`,
                }}
              />
            </div>
            <div
              className="w-8 text-right text-xs font-semibold tabular-nums"
              style={{ color: scoreColorHex(value) }}
            >
              {value != null ? Math.round(value) : '—'}
            </div>
          </div>
        );
      })}
    </div>
  );
}
