// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ getRunStatus: vi.fn() }));

vi.mock('@/api/search', () => ({ getRunStatus: mocks.getRunStatus }));
vi.mock('@/contexts/workspace-context', () => ({ useWorkspace: () => ({ hostedMode: false }) }));

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static last: FakeEventSource | null = null;
  readyState = FakeEventSource.OPEN;
  onerror: (() => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }
  addEventListener() {}
  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
}

import { SearchProvider, useSearchContext } from './search-context';

function setup() {
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, createElement(SearchProvider, null, children));
  return renderHook(() => useSearchContext(), { wrapper });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('EventSource', FakeEventSource);
  mocks.getRunStatus.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('SearchProvider when the progress stream drops', () => {
  // Nov 11 2026: minimizing the desktop window let macOS drop the progress
  // stream. The provider then polled the run for ~90s and declared "Lost
  // contact", but a pull takes 3 to 6 minutes, so a healthy run read as
  // stopped. All 15 of Brian's pulls since Nov 6 completed server-side.
  it('keeps following a pull that is still running past 90 seconds', async () => {
    let calls = 0;
    mocks.getRunStatus.mockImplementation(async () => {
      calls += 1;
      return calls < 80
        ? { status: 'running' }
        : { status: 'completed', jobs_found: 12, new_jobs: 3, jobs_scored: 0 };
    });
    const rendered = setup();

    act(() => rendered.result.current.activate('run1', 'search_only', null as never));
    const es = FakeEventSource.last!;
    act(() => {
      es.readyState = FakeEventSource.CLOSED;
      es.onerror?.();
    });

    for (let i = 0; i < 90 && rendered.result.current.state === 'running'; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
    }

    expect(rendered.result.current.state).toBe('completed');
    expect(rendered.result.current.error).toBeNull();
  });
  it('stops polling the run once the provider unmounts', async () => {
    mocks.getRunStatus.mockResolvedValue({ status: 'running' });
    const rendered = setup();

    act(() => rendered.result.current.activate('run1', 'search_only', null as never));
    const es = FakeEventSource.last!;
    act(() => {
      es.readyState = FakeEventSource.CLOSED;
      es.onerror?.();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    rendered.unmount();
    const calls = mocks.getRunStatus.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(mocks.getRunStatus).toHaveBeenCalledTimes(calls);
  });

  it('checks the run as soon as the window is visible again', async () => {
    mocks.getRunStatus.mockResolvedValue({ status: 'completed', jobs_found: 4, new_jobs: 1, jobs_scored: 0 });
    const rendered = setup();

    act(() => rendered.result.current.activate('run1', 'search_only', null as never));
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(rendered.result.current.state).toBe('completed');
    expect(rendered.result.current.result?.jobs_found).toBe(4);
  });
});
