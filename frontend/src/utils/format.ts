export function formatDate(dateStr: string | null, style: 'short' | 'relative' | 'full' = 'short'): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '';

  if (style === 'relative') {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  if (style === 'full') {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** ISO codes the UI renders as a bare symbol. Anything else keeps its code
    as a prefix ("CHF 90K") so we never guess at a symbol. */
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  CAD: 'C$',
  AUD: 'A$',
};

/** '$' when no currency is stated (legacy rows), the symbol for known
    codes, "CHF " (code plus space) for the rest. */
export function salaryCurrencyPrefix(currency?: string | null): string {
  const code = (currency || '').trim().toUpperCase();
  if (!code) return '$';
  return CURRENCY_SYMBOLS[code] ?? `${code} `;
}

export type SalaryPeriod = 'hourly' | 'annual';

/** The API's salary_period narrowed to what the formatter distinguishes.
    'yearly' appears on rows saved before the values settled. */
export function toSalaryPeriod(raw?: string | null): SalaryPeriod | null {
  if (raw === 'hourly') return 'hourly';
  if (raw === 'annual' || raw === 'yearly') return 'annual';
  return null;
}

export function formatSalary(
  min: number | null,
  max: number | null,
  currency?: string | null,
  period?: SalaryPeriod | null,
): string {
  if (!min && !max) return '';
  const prefix = salaryCurrencyPrefix(currency);
  const hourly = period === 'hourly';
  const fmt = (n: number) => {
    // Hourly rates stay exact; only annual-scale figures compact to K.
    if (!hourly && n >= 1000) return `${prefix}${Math.round(n / 1000)}K`;
    return `${prefix}${n}`;
  };
  const suffix = hourly ? '/hr' : '';
  if (min && max) return `${fmt(min)} - ${fmt(max)}${suffix}`;
  if (min) return `${fmt(min)}+${suffix}`;
  return `Up to ${fmt(max!)}${suffix}`;
}

/**
 * Strip markdown artifacts and HTML tags from job descriptions.
 * Handles: \-, **, ***, ###, \\n, escaped chars, bullet markers, etc.
 */
export function cleanDescription(text: string): string {
  if (!text) return '';
  return text
    // Remove HTML tags
    .replace(/<[^>]*>/g, '')
    // Fix escaped markdown characters: \- \* \# \[ \] \( \) \+
    .replace(/\\([*\-+#[\]()_~`>|.])/g, '$1')
    // Force newlines before inline markdown headers (e.g. "USA.### Minimum")
    .replace(/([.!?;,])\s*#{1,6}\s+/g, '$1\n')
    // Convert markdown headers at start of line to plain text on new line
    .replace(/^#{1,6}\s+/gm, '\n')
    // Remove bold/italic markers but keep the text: ***, **, *
    .replace(/\*{1,3}([^*]*?)\*{1,3}/g, '$1')
    // Remove markdown links: [text](url) -> text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    // Convert horizontal rules (---, ===, ___) to empty lines
    .replace(/^[-—–=_]{3,}\s*$/gm, '')
    // Normalize unicode bullets and markers to clean dashes
    .replace(/^\s*[•●▪▸►◆◇○■□➤→»›]\s*/gm, '- ')
    // Convert markdown bullets to clean bullets
    .replace(/^\s*[*+]\s+/gm, '- ')
    // Clean up excessive whitespace
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+/g, ' ')
    .trim();
}

export function truncateDescription(text: string, maxLength = 150): string {
  if (!text) return '';
  // Clean first, then truncate
  const cleaned = cleanDescription(text).replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLength) return cleaned;
  return cleaned.slice(0, maxLength).replace(/\s+\S*$/, '') + '...';
}
