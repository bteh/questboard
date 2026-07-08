import type { ReactNode } from 'react';

/* The old shell's content container, kept so pre-redesign pages hold
   their width inside the trade-paper shell until each one is rebuilt. */
export function LegacyFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      {children}
    </div>
  );
}
