/**
 * The quest mark: a pinned notice reduced to the sign every player knows,
 * the "!" that means a quest is waiting. Bar and pin head render in
 * currentColor (cream on the sage tile); the pin center stays clay.
 * Legible down to 14px. Masters live at frontend/public/brand/.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <g transform="rotate(-4 8 6.3)">
        <rect x="6.6" y="2.8" width="2.8" height="6.7" rx="1.4" fill="currentColor" />
      </g>
      <circle cx="8" cy="12" r="1.7" fill="currentColor" />
      <circle cx="8" cy="12" r="0.75" fill="#A6522E" />
    </svg>
  );
}
