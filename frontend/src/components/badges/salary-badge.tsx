import { DollarSign } from 'lucide-react';
import { ColorBadge } from './color-badge';
import { formatSalary } from '@/utils/format';

interface SalaryBadgeProps {
  min: number | null;
  max: number | null;
}

export function SalaryBadge({ min, max }: SalaryBadgeProps) {
  const text = formatSalary(min, max);
  if (!text) return null;
  return (
    <ColorBadge bg="#D1FAE5" text="#065F46" darkBg="#064E3B" darkText="#6EE7B7">
      <DollarSign className="h-3 w-3" />
      {text}
    </ColorBadge>
  );
}
