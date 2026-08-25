import { isDesktopApp } from '@/lib/platform';

/* One sentence for a dead backend, honest per surface and pinned by
   backend-down.test.ts. The dev browser can run `make dev`; the packaged
   app's reader has no terminal, only the app itself to restart. */
export function backendDownLine(desktop: boolean = isDesktopApp()): string {
  return desktop
    ? "The board's background service stopped. Quit and reopen the app."
    : 'The board could not reach the backend. Start it with make dev and reload.';
}
