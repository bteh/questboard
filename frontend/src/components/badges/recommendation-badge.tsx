import { ColorBadge } from './color-badge';
import { RECOMMENDATION_COLORS, RECOMMENDATION_LABELS } from '@/utils/constants';
import type { Recommendation } from '@/utils/constants';

interface RecommendationBadgeProps {
  recommendation: Recommendation | string;
  /** Which scale scored the row. Keyword-scored rows are rough guesses on a
      lenient scale, so they get a muted note instead of the stamp; 'ai',
      null, or absent keeps the stamp exactly as before. */
  scoreSource?: 'ai' | 'keyword' | null;
}

export function RecommendationBadge({ recommendation, scoreSource }: RecommendationBadgeProps) {
  if (!recommendation) return null;
  if (scoreSource === 'keyword') {
    return (
      <span
        title="Scored offline by keyword matching, no AI. Treat it as a rough guess, this is a looser scale than AI-scored jobs."
        className="font-mono text-[11px] text-text-muted"
      >
        rough keyword match
      </span>
    );
  }
  const c = RECOMMENDATION_COLORS[recommendation] || { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' };
  return (
    <ColorBadge bg={c.bg} text={c.text} darkBg={c.darkBg} darkText={c.darkText} className="font-semibold">
      {RECOMMENDATION_LABELS[recommendation] || recommendation.replace(/_/g, ' ').replace(/\b\w+/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())}
    </ColorBadge>
  );
}
