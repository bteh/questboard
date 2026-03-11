import { TrendingUp } from 'lucide-react';
import { ColorBadge } from './color-badge';
import type { ApplicationResponse } from '@/types/application';

interface FundingBadgeProps {
  app: ApplicationResponse;
}

function isUseful(val: string | null | undefined): val is string {
  if (!val) return false;
  const lower = val.trim().toLowerCase();
  return lower !== '' && lower !== 'unknown' && lower !== 'n/a' && lower !== 'none';
}

export function FundingBadge({ app }: FundingBadgeProps) {
  const parts: string[] = [];
  if (isUseful(app.funding_stage)) {
    // Truncate overly verbose funding descriptions
    const stage = app.funding_stage.length > 30
      ? app.funding_stage.slice(0, 30).replace(/\s+\S*$/, '') + '...'
      : app.funding_stage;
    parts.push(stage);
  }
  if (isUseful(app.total_funding)) {
    const funding = app.total_funding.length > 20
      ? app.total_funding.slice(0, 20).replace(/\s+\S*$/, '') + '...'
      : app.total_funding;
    parts.push(funding);
  }
  if (parts.length === 0) return null;
  return (
    <ColorBadge bg="#F3E8FF" text="#6B21A8" darkBg="#581C87" darkText="#D8B4FE" className="max-w-[280px] truncate">
      <TrendingUp className="h-3 w-3 shrink-0" />
      <span className="truncate">{parts.join(' · ')}</span>
    </ColorBadge>
  );
}
