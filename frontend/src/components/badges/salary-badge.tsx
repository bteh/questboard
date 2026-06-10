import { DollarSign } from 'lucide-react';
import { ColorBadge } from './color-badge';
import { formatSalary } from '@/utils/format';

interface SalaryBadgeProps {
  min: number | null;
  max: number | null;
  /** 'reported' | 'parsed_from_description' — parsed values are marked as estimates. */
  source?: string | null;
}

export function SalaryBadge({ min, max, source }: SalaryBadgeProps) {
  const text = formatSalary(min, max);
  if (!text) return null;
  const estimated = source === 'parsed_from_description';
  return (
    <ColorBadge bg="#D1FAE5" text="#065F46" darkBg="#064E3B" darkText="#6EE7B7">
      <DollarSign className="h-3 w-3" />
      <span title={estimated ? 'Estimated from the job description text, not employer-reported.' : undefined}>
        {text}
        {estimated && <span className="ml-1 font-normal opacity-75">(est.)</span>}
      </span>
    </ColorBadge>
  );
}
