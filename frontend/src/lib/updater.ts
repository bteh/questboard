import type { Update } from '@tauri-apps/plugin-updater';

import { isDesktopApp } from '@/lib/platform';
import { downloadPercent, type UpdateState } from '@/lib/updater-logic';

const LAST_CHECK_KEY = 'questboard.updater.lastCheckedAt';

/* Only the Update object that ran download() may install; a fresh check()
   hands back a new one that throws on install(). So the downloaded object
   lives here until it is installed or a check finds nothing. */
let staged: Update | null = null;

export function readLastCheckedAt(): number | null {
  try {
    const raw = window.localStorage.getItem(LAST_CHECK_KEY);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastCheckedAt(at: number): void {
  try {
    window.localStorage.setItem(LAST_CHECK_KEY, String(at));
  } catch {
    // A locked-down webview must not break the update path.
  }
}

/**
 * Look for an update and download it if there is one.
 *
 * Every failure here is silent by design: no endpoint, no network, an
 * unsigned payload, a half-published release. None of that is something
 * the user asked for or can act on, so it degrades to "no update".
 */
export async function fetchAndStageUpdate(
  onState: (state: UpdateState) => void,
): Promise<void> {
  if (!isDesktopApp()) return;

  try {
    onState({ kind: 'checking' });
    const { check } = await import('@tauri-apps/plugin-updater');
    const update = await check();
    if (!update) {
      staged = null;
      onState({ kind: 'up_to_date' });
      return;
    }

    await downloadAndStage(update, onState);
    onState({ kind: 'ready', version: update.version });
  } catch (err) {
    console.warn('update check failed', err);
    onState({ kind: 'failed' });
  }
}

async function downloadAndStage(
  update: Update,
  onState: (state: UpdateState) => void,
): Promise<void> {
  let downloaded = 0;
  let total: number | null = null;
  onState({ kind: 'downloading', percent: 0 });

  await update.download((event) => {
    if (event.event === 'Started') {
      total = event.data.contentLength ?? null;
    } else if (event.event === 'Progress') {
      downloaded += event.data.chunkLength;
      onState({ kind: 'downloading', percent: downloadPercent(downloaded, total) });
    }
  });

  staged = update;
}

/**
 * Install the staged update, then shut the backend down, then relaunch.
 *
 * Install comes first so a failed install leaves a working app: the user
 * sees "Couldn't install" and can try again or keep working. The backend
 * is shut down only once the new bundle is on disk. It owns the SQLite
 * file and the port, and letting it die on its own during the relaunch
 * races the new instance for both.
 *
 * With nothing staged (a fresh window, a cleared store) this downloads
 * first. With nothing to download it says "up to date" and touches nothing.
 * Never rejects: the hook fires this and forgets, so a thrown error would
 * vanish and the pill would sit there saying "Restart".
 */
export async function installAndRestart(
  onState: (state: UpdateState) => void,
): Promise<void> {
  if (!staged) await fetchAndStageUpdate(onState);
  const update = staged;
  if (!update) return;

  onState({ kind: 'installing', version: update.version });
  try {
    await update.install();
  } catch (err) {
    console.warn('update install failed', err);
    onState({ kind: 'install_failed', version: update.version });
    return;
  }
  staged = null;

  const { invoke } = await import('@tauri-apps/api/core');
  const { relaunch } = await import('@tauri-apps/plugin-process');
  await invoke('shutdown_runtime_for_update');
  await relaunch();
}

/** The version this build carries, for the Settings row. */
export async function currentAppVersion(): Promise<string> {
  if (!isDesktopApp()) return '';
  try {
    const { getVersion } = await import('@tauri-apps/api/app');
    return await getVersion();
  } catch {
    return '';
  }
}
