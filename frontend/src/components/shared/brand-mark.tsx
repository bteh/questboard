/**
 * Launchboard mark: a rising arrow launching from an origin dot.
 * Reads as "launch / upward trajectory", on-brand with the warm growth theme
 * and legible down to 14px. Renders in currentColor (white on the sage tile).
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <circle cx="4" cy="12" r="1.5" fill="currentColor" />
      <path d="M5.2 10.8 10.8 5.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M7.4 5H11V8.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
