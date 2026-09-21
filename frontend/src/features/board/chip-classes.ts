/* One chip look for every filter row on the work lane, so the source and
   level rows read as one control. */

export const chipClass =
  'focus-ring min-h-11 rounded-full border px-3 py-1 text-xs transition-colors md:min-h-0';
export const chipInactiveClass = 'border-border-default text-text-secondary hover:text-text-primary';
export const chipActiveClass = 'border-brand bg-brand/10 font-medium text-brand';
export const chipCountClass = 'font-mono text-text-secondary tabular-nums';
/* the row's name, so the level row never reads as more source chips */
export const chipRowLabelClass = 'mr-1 font-mono text-[10px] uppercase tracking-[.06em] text-text-muted';
