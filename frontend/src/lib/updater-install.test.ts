// @vitest-environment jsdom
/* Real case (Sep 9 2026): "Version 0.2.6 is ready. Restart" did nothing. The
   restart asked the updater plugin for a fresh update object and installed
   THAT one, but only the object that ran download() may install; the plugin
   throws "Update.install called before Update.download". By then the backend
   had already been shut down, so the window stayed open with no brain
   behind it. No self-update had ever completed.

   Rules pinned here:
   1. The object that downloaded is the object that installs; no second check.
   2. Order is install, then shut the backend down, then relaunch, so a failed
      install leaves a working app.
   3. A failed install is said out loud and never throws at the caller.
   4. With nothing staged, restart downloads first instead of failing. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UpdateState } from './updater-logic';

const mocks = vi.hoisted(() => {
  const calls: string[] = [];
  const flags = { installFails: false, noUpdate: false };
  class FakeUpdate {
    version = '0.2.6';
    downloaded = false;
    async download(onEvent?: (event: { event: string; data: Record<string, number> }) => void) {
      calls.push('download');
      onEvent?.({ event: 'Started', data: { contentLength: 10 } });
      onEvent?.({ event: 'Progress', data: { chunkLength: 10 } });
      this.downloaded = true;
    }
    async install() {
      calls.push('install');
      if (!this.downloaded) throw new Error('Update.install called before Update.download');
      if (flags.installFails) throw new Error('could not replace the app bundle');
    }
  }
  return {
    calls,
    flags,
    check: vi.fn(async () => (flags.noUpdate ? null : new FakeUpdate())),
    invoke: vi.fn(async (command: string) => {
      calls.push(command);
    }),
    relaunch: vi.fn(async () => {
      calls.push('relaunch');
    }),
  };
});

vi.mock('@tauri-apps/plugin-updater', () => ({ check: mocks.check }));
vi.mock('@tauri-apps/api/core', () => ({ invoke: mocks.invoke }));
vi.mock('@tauri-apps/plugin-process', () => ({ relaunch: mocks.relaunch }));
vi.mock('@/lib/platform', () => ({ isDesktopApp: () => true }));

async function freshUpdater() {
  vi.resetModules();
  return import('./updater');
}

beforeEach(() => {
  mocks.calls.length = 0;
  mocks.flags.installFails = false;
  mocks.flags.noUpdate = false;
  mocks.check.mockClear();
  mocks.invoke.mockClear();
  mocks.relaunch.mockClear();
});

describe('installAndRestart', () => {
  it('installs the very object that downloaded, then shuts the backend down, then relaunches', async () => {
    const updater = await freshUpdater();
    const states: UpdateState[] = [];
    await updater.fetchAndStageUpdate((state) => states.push(state));
    expect(states.at(-1)).toEqual({ kind: 'ready', version: '0.2.6' });

    await updater.installAndRestart((state) => states.push(state));

    expect(mocks.check).toHaveBeenCalledTimes(1);
    expect(mocks.calls).toEqual(['download', 'install', 'shutdown_runtime_for_update', 'relaunch']);
    expect(states).toContainEqual({ kind: 'installing', version: '0.2.6' });
  });

  it('leaves the backend running and says so when the install fails', async () => {
    const updater = await freshUpdater();
    const states: UpdateState[] = [];
    await updater.fetchAndStageUpdate((state) => states.push(state));
    mocks.flags.installFails = true;

    await expect(updater.installAndRestart((state) => states.push(state))).resolves.toBeUndefined();

    expect(mocks.calls).toEqual(['download', 'install']);
    expect(mocks.invoke).not.toHaveBeenCalledWith('shutdown_runtime_for_update');
    expect(mocks.relaunch).not.toHaveBeenCalled();
    expect(states.at(-1)).toEqual({ kind: 'install_failed', version: '0.2.6' });
  });

  it('downloads first when nothing is staged, instead of installing an empty update', async () => {
    const updater = await freshUpdater();
    const states: UpdateState[] = [];

    await updater.installAndRestart((state) => states.push(state));

    expect(mocks.check).toHaveBeenCalledTimes(1);
    expect(mocks.calls).toEqual(['download', 'install', 'shutdown_runtime_for_update', 'relaunch']);
  });

  it('shuts nothing down when there is no update to install', async () => {
    const updater = await freshUpdater();
    mocks.flags.noUpdate = true;
    const states: UpdateState[] = [];

    await updater.installAndRestart((state) => states.push(state));

    expect(mocks.calls).toEqual([]);
    expect(states.at(-1)).toEqual({ kind: 'up_to_date' });
  });
});
