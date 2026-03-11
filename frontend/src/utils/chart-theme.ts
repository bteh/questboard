/**
 * Chart theme configuration that adapts to dark mode.
 * Uses CSS custom properties so charts update automatically when the theme toggles.
 */
export function getChartTheme() {
  const style = getComputedStyle(document.documentElement);
  const get = (prop: string) => style.getPropertyValue(prop).trim();

  return {
    grid: get('--lb-border-default') || '#E2E8F0',
    axis: get('--lb-text-tertiary') || '#94A3B8',
    axisLine: get('--lb-border-default') || '#E2E8F0',
    tooltipBg: get('--lb-bg-card') || '#FFFFFF',
    tooltipBorder: get('--lb-border-default') || '#E2E8F0',
    tooltipText: get('--lb-text-primary') || '#0F172A',
  };
}

export function tooltipStyle() {
  const t = getChartTheme();
  return {
    borderRadius: 8,
    border: `1px solid ${t.tooltipBorder}`,
    fontSize: 13,
    backgroundColor: t.tooltipBg,
    color: t.tooltipText,
    boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
  };
}
