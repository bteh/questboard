import { scoreColorHex } from '@/utils/colors';

interface ScoreCircleProps {
  score: number | null;
  size?: 'sm' | 'md' | 'lg';
}

const SIZE_CONFIG = {
  sm: { px: 32, stroke: 3, font: 'text-[10px]' },
  md: { px: 40, stroke: 3.5, font: 'text-xs' },
  lg: { px: 56, stroke: 4, font: 'text-base' },
};

export function ScoreCircle({ score, size = 'md' }: ScoreCircleProps) {
  if (score === null || score === undefined) return null;
  const color = scoreColorHex(score);
  const { px, stroke, font } = SIZE_CONFIG[size];
  const radius = (px - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(Math.max(score, 0), 100);
  const offset = circumference * (1 - pct / 100);

  const label = pct >= 70 ? 'Strong match — high resume fit' : pct >= 55 ? 'Good match — moderate resume fit' : pct >= 40 ? 'Moderate match — worth reviewing' : 'Low match — limited resume overlap';

  return (
    <div className="relative shrink-0" style={{ width: px, height: px }} title={`Match score: ${Math.round(score)} / 100 — ${label}`}>
      <svg width={px} height={px} className="-rotate-90">
        {/* Background track */}
        <circle
          cx={px / 2}
          cy={px / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-bg-muted"
        />
        {/* Score arc */}
        <circle
          cx={px / 2}
          cy={px / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <span
        className={`absolute inset-0 flex items-center justify-center font-bold ${font}`}
        style={{ color }}
      >
        {Math.round(score)}
      </span>
    </div>
  );
}
