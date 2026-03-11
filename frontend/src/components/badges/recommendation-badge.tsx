import { ColorBadge } from './color-badge';
import { RECOMMENDATION_COLORS, RECOMMENDATION_LABELS } from '@/utils/constants';
import type { Recommendation } from '@/utils/constants';

interface RecommendationBadgeProps {
  recommendation: Recommendation | string;
}

export function RecommendationBadge({ recommendation }: RecommendationBadgeProps) {
  if (!recommendation) return null;
  const c = RECOMMENDATION_COLORS[recommendation] || { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' };
  return (
    <ColorBadge bg={c.bg} text={c.text} darkBg={c.darkBg} darkText={c.darkText} className="font-semibold">
      {RECOMMENDATION_LABELS[recommendation] || recommendation.replace(/_/g, ' ').replace(/\b\w+/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())}
    </ColorBadge>
  );
}
