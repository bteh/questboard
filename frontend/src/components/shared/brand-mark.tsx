/**
 * The quest mark: a pinned notice reduced to the sign every player knows,
 * the "!" that means a quest is waiting. Bar and pin head render in
 * currentColor (cream on the sage tile); the pin center stays clay.
 * Legible down to 14px. Masters live at frontend/public/brand/.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <g transform="rotate(-4 8 5.8)">
        <rect x="6.35" y="1.9" width="3.3" height="7.8" rx="1.65" fill="currentColor" />
      </g>
      <circle cx="8" cy="12.5" r="1.95" fill="currentColor" />
      <circle cx="8" cy="12.5" r="0.85" fill="#A6522E" />
    </svg>
  );
}
