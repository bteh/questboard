const AVATAR_COLORS = [
  '#4F46E5', '#7C3AED', '#2563EB', '#0891B2', '#059669',
  '#D97706', '#DC2626', '#DB2777', '#9333EA', '#0D9488',
  '#6366F1', '#8B5CF6', '#0284C7', '#0F766E', '#B45309',
];

export function avatarColor(name: string): string {
  const sum = Array.from(name).reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

// Thresholds match the scoring system:
// STRONG_APPLY ≥70, APPLY ≥55, MAYBE ≥40, SKIP <40
export function scoreColor(score: number | null): 'high' | 'mid-high' | 'mid' | 'low' {
  if (score === null || score === undefined) return 'low';
  if (score >= 70) return 'high';       // STRONG_APPLY
  if (score >= 55) return 'mid-high';   // APPLY
  if (score >= 40) return 'mid';        // MAYBE
  return 'low';                          // SKIP
}

export function scoreColorHex(score: number | null): string {
  const level = scoreColor(score);
  if (level === 'high') return '#10B981';      // green
  if (level === 'mid-high') return '#3B82F6';  // blue
  if (level === 'mid') return '#F59E0B';       // amber
  return '#EF4444';                             // red
}
