import type { ReactNode } from 'react';
import { useTheme } from '@/contexts/theme-context';

interface ColorBadgeProps {
  bg: string;
  text: string;
  darkBg?: string;
  darkText?: string;
  children: ReactNode;
  className?: string;
}

/** Reusable colored pill badge — shared base for all badge components. */
export function ColorBadge({ bg, text, darkBg, darkText, children, className }: ColorBadgeProps) {
  const { resolved } = useTheme();
  const isDark = resolved === 'dark';

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${className || ''}`}
      style={{
        backgroundColor: isDark && darkBg ? darkBg : bg,
        color: isDark && darkText ? darkText : text,
      }}
    >
      {children}
    </span>
  );
}
