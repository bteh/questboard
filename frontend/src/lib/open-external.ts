import { isDesktopApp } from '@/lib/platform';

/**
 * Open an external URL.
 *
 * In desktop mode, Tauri's WKWebView doesn't follow target="_blank"
 * links — they either do nothing or trap the user in the app. We have
 * to explicitly call the shell plugin to open the URL in the system
 * browser.
 *
 * In web mode, just use window.open which works everywhere.
 */
export async function openExternal(url: string): Promise<void> {
  if (isDesktopApp()) {
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
      return;
    } catch (err) {
      console.warn('shell.open failed, falling back to window.open', err);
    }
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

/**
 * React onClick handler that opens an external URL. Use as:
 *
 *   <a href={url} onClick={openExternalClick(url)}>...</a>
 *
 * The href keeps native tooltips (hover shows URL) while the onClick
 * intercepts the click in desktop mode.
 */
export function openExternalClick(url: string) {
  return (e: React.MouseEvent) => {
    e.preventDefault();
    openExternal(url);
  };
}
