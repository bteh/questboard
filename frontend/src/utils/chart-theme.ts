/**
 * Chart chrome in the trade-paper grammar: hairline grid and axis lines,
 * muted ink axis text, a paper tooltip with a hairline border and no
 * shadow. Reads the committed tokens off the document root so the charts
 * stay in step with tokens.css; the fallbacks are the same canon values.
 */
export function getChartTheme() {
  const style = getComputedStyle(document.documentElement);
  const get = (prop: string) => style.getPropertyValue(prop).trim();

  return {
    grid: get('--hair') || '#E4DED1',
    axis: get('--mute') || 'rgba(28, 27, 23, .66)',
    axisLine: get('--hair') || '#E4DED1',
    tooltipBg: get('--paper') || '#FFFFFF',
    tooltipBorder: get('--hair') || '#E4DED1',
    tooltipText: get('--ink') || '#1C1B17',
  };
}

export function tooltipStyle() {
  const t = getChartTheme();
  return {
    borderRadius: 4,
    border: `1px solid ${t.tooltipBorder}`,
    fontSize: 13,
    backgroundColor: t.tooltipBg,
    color: t.tooltipText,
  };
}
