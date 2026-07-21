import { DollarSign } from 'lucide-react';
import { ColorBadge } from './color-badge';
import { formatSalary, toSalaryPeriod } from '@/utils/format';

interface SalaryBadgeProps {
  min: number | null;
  max: number | null;
  /** 'reported' | 'parsed_from_description' — parsed values are marked as estimates. */
  source?: string | null;
  /** ISO code from salary_currency ('USD', 'EUR', ...); absent keeps "$". */
  currency?: string | null;
  /** salary_period from the record; 'hourly' renders with /hr, uncompacted. */
  period?: string | null;
}

export function SalaryBadge({ min, max, source, currency, period }: SalaryBadgeProps) {
  const text = formatSalary(min, max, currency, toSalaryPeriod(period));
  if (!text) return null;
  const estimated = source === 'parsed_from_description';
  return (
    <ColorBadge bg="#E3EDE7" text="#3F6B54" darkBg="#25382E" darkText="#8FC2A4">
      <DollarSign className="h-3 w-3" />
      <span title={estimated ? 'Estimated from the job description text, not employer-reported.' : undefined}>
        {text}
        {estimated && <span className="ml-1 font-normal opacity-75">(est.)</span>}
      </span>
    </ColorBadge>
  );
}
