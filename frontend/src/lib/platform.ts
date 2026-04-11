/**
 * Desktop mode detection for Tauri v2.
 *
 * Tauri injects `__TAURI_INTERNALS__` into the window object when
 * running inside its webview. This lets us branch between the desktop
 * Quick Start wizard (auto-install Ollama) and the web-mode API-key flow.
 */
export function isDesktopApp(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}
