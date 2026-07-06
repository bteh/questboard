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
    bg = isDark ? '#25382E' : '#E3EDE7';
    text = isDark ? '#8FC2A4' : '#3F6B54';
    dotColor = isDark ? '#7FB393' : '#3F6B54';
    label = llm.label || 'Connected';
  } else if (llm.configured) {
    bg = isDark ? '#3A211E' : '#F6DFDC';
    text = isDark ? '#E9A69E' : '#A23A30';
    dotColor = isDark ? '#E27A6F' : '#C4443A';
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
