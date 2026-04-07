import { Zap } from 'lucide-react';
import { useTheme } from '@/contexts/theme-context';
import type { LLMStatus } from '@/types/settings';

interface ConnectionBadgeProps {
  llm: LLMStatus | undefined;
}

export function ConnectionBadge({ llm }: ConnectionBadgeProps) {
  const { resolved } = useTheme();
  if (!llm) return null;
  const isDark = resolved === 'dark';

  let bg: string, text: string, dotColor: string, label: string;
  if (llm.available) {
    bg = isDark ? '#064E3B' : '#DCFCE7';
    text = isDark ? '#6EE7B7' : '#166534';
    dotColor = '#10B981';
    label = llm.label || 'Connected';
  } else if (llm.configured) {
    bg = isDark ? '#7F1D1D' : '#FEE2E2';
    text = isDark ? '#FCA5A5' : '#991B1B';
    dotColor = '#EF4444';
    label = 'Disconnected';
  } else {
    bg = isDark ? '#27272A' : '#F1F5F9';
    text = isDark ? '#A1A1AA' : '#64748B';
    dotColor = isDark ? '#71717A' : '#94A3B8';
    label = 'AI optional';
  }

  return (
    <div
      className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium"
      style={{ backgroundColor: bg, color: text }}
    >
      <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: dotColor }} />
      <Zap className="h-3 w-3" />
      {label}
    </div>
  );
}
