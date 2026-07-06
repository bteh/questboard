// Warm-varied avatar set (sages, olives, ambers, clays, muted teal). No pure
// blue/indigo/violet so avatars sit inside the warm operator palette.
const AVATAR_COLORS = [
  '#3F6B54', '#4C8A63', '#5E7C4F', '#6E8B4E', '#8FA054',
  '#A98B3C', '#B4701C', '#E0872F', '#C06A3C', '#A64B2A',
  '#4E8A8F', '#3D7068', '#7FB393', '#8A6D3B',
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
  if (level === 'high') return '#3F6B54';       // sage
  if (level === 'mid-high') return '#7F9B4E';   // olive
  if (level === 'mid') return '#E0872F';        // amber
  return '#C4443A';                              // warm red
}
