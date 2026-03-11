import { ColorBadge } from './color-badge';
import { COMPANY_TYPE_COLORS, COMPANY_TYPE_DESCRIPTIONS } from '@/utils/constants';
import type { CompanyType } from '@/utils/constants';

interface CompanyTypeBadgeProps {
  companyType: CompanyType | string;
}

export function CompanyTypeBadge({ companyType }: CompanyTypeBadgeProps) {
  if (!companyType || companyType === 'Unknown') return null;
  const colors = COMPANY_TYPE_COLORS[companyType] || { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' };
  const description = COMPANY_TYPE_DESCRIPTIONS[companyType];
  return (
    <span title={description}>
      <ColorBadge bg={colors.bg} text={colors.text} darkBg={colors.darkBg} darkText={colors.darkText}>{companyType}</ColorBadge>
    </span>
  );
}
