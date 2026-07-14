import { useState } from 'react';
import { avatarColor } from '@/utils/colors';
import { getCompanyLogoUrl } from '@/utils/company-domains';

interface CompanyAvatarProps {
  company: string;
  size?: number;
  /** The posting URL, used to resolve the employer's real domain for direct postings. */
  url?: string | null;
}

export function CompanyAvatar({ company, size = 40, url }: CompanyAvatarProps) {
  // unavatar aggregates favicon + logo providers and 404s cleanly on a miss, so
  // one lookup is enough: real logo, or fall straight to a colored initial.
  const [failed, setFailed] = useState(false);
  const logoUrl = getCompanyLogoUrl(company, size >= 64 ? 128 : 64, url);
  const bg = avatarColor(company);
  const initial = company ? company[0].toUpperCase() : '?';

  if (logoUrl && !failed) {
    return (
      <div
        className="flex items-center justify-center rounded-lg bg-bg-card border border-border-default overflow-hidden shrink-0"
        style={{ width: size, height: size }}
      >
        <img
          src={logoUrl}
          alt={`${company} logo`}
          width={Math.round(size * 0.7)}
          height={Math.round(size * 0.7)}
          className="object-contain"
          loading="lazy"
          onError={() => setFailed(true)}
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
