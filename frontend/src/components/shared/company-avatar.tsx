import { useState } from 'react';
import { avatarColor } from '@/utils/colors';
import { getCompanyLogoUrl, getCompanyLogoFallbackUrl } from '@/utils/company-domains';

interface CompanyAvatarProps {
  company: string;
  size?: number;
}

export function CompanyAvatar({ company, size = 40 }: CompanyAvatarProps) {
  const [imgStage, setImgStage] = useState<'primary' | 'fallback' | 'letter'>('primary');
  const logoUrl = getCompanyLogoUrl(company, size >= 64 ? 128 : 64);
  const fallbackUrl = getCompanyLogoFallbackUrl(company, size >= 64 ? 128 : 64);
  const bg = avatarColor(company);
  const initial = company ? company[0].toUpperCase() : '?';

  const currentUrl = imgStage === 'primary' ? logoUrl
    : imgStage === 'fallback' ? fallbackUrl
    : null;

  if (currentUrl) {
    return (
      <div
        className="flex items-center justify-center rounded-lg bg-bg-card border border-border-default overflow-hidden shrink-0"
        style={{ width: size, height: size }}
      >
        <img
          src={currentUrl}
          alt={`${company} logo`}
          width={Math.round(size * 0.7)}
          height={Math.round(size * 0.7)}
          className="object-contain"
          loading="lazy"
          onError={() => {
            if (imgStage === 'primary' && fallbackUrl) {
              setImgStage('fallback');
            } else {
              setImgStage('letter');
            }
          }}
        />
      </div>
    );
  }

  return (
    <div
      className="flex items-center justify-center rounded-lg text-white font-semibold shrink-0"
      style={{
        width: size,
        height: size,
        backgroundColor: bg,
        fontSize: size * 0.4,
      }}
    >
      {initial}
    </div>
  );
}
