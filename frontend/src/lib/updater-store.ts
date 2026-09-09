import { useSyncExternalStore } from 'react';

import type { UpdateState } from '@/lib/updater-logic';

/* One update state for the whole app. The topbar pill and the Settings row
   both read it, so a download the pill started is what Settings reports. */

let current: UpdateState = { kind: 'idle' };
const listeners = new Set<() => void>();

export function setUpdateState(next: UpdateState): void {
  current = next;
  listeners.forEach((listener) => listener());
}

export function readUpdateState(): UpdateState {
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useUpdateState(): UpdateState {
  return useSyncExternalStore(subscribe, readUpdateState, readUpdateState);
}
