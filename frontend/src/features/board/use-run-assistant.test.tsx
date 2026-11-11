// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  activate: vi.fn(),
}));

vi.mock('@/contexts/search-context', () => ({
  useSearchContext: () => ({ activate: mocks.activate, state: 'idle' }),
}));

vi.mock('sonner', () => ({
  toast: { success: mocks.success, error: mocks.error },
}));

vi.mock('@/hooks/use-agent-clients', () => ({
  useRunAgent: () => ({ mutate: mocks.mutate, isPending: false }),
}));

import { useRunAssistant } from './use-run-assistant';

interface RunCallbacks {
  onSuccess: (data: {
    ok: boolean;
    result?: string;
    error?: string;
    pull_run_id?: string | null;
  }) => void;
  onError: (error: Error) => void;
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, rendered: renderHook(() => useRunAssistant(), { wrapper }) };
}

beforeEach(() => {
  mocks.mutate.mockReset();
  mocks.success.mockReset();
  mocks.error.mockReset();
  mocks.activate.mockReset();
});

describe('useRunAssistant', () => {
  it('refreshes the board without exposing the assistant summary as a toast', () => {
    const { queryClient, rendered } = setup();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    act(() => rendered.result.current.start());
    const callbacks = mocks.mutate.mock.calls[0][1] as RunCallbacks;
    act(() =>
      callbacks.onSuccess({
        ok: true,
        result: 'Proposed adding several roles; two jobs needed review.',
      }),
    );

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['profile-work'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['applications'] });
    for (const call of mocks.success.mock.calls) {
      expect(String(call[0])).not.toContain('Proposed adding');
    }
  });

  // Nov 5 2026: Brian could not tell when an assistant run had finished; the
  // success path reloaded the board silently, so the board before and after
  // looked the same. A plain pull toasts on completion; so must this run.
  it('says the board was updated when the run succeeds', () => {
    const { rendered } = setup();

    act(() => rendered.result.current.start());
    const callbacks = mocks.mutate.mock.calls[0][1] as RunCallbacks;
    act(() => callbacks.onSuccess({ ok: true, result: 'internal notes' }));

    expect(mocks.success).toHaveBeenCalledTimes(1);
    expect(String(mocks.success.mock.calls[0][0])).toMatch(/board updated/i);
  });

  // Nov 11 2026: the run ranked and returned at 17:49 while the pull it
  // started kept going until 17:51. "Board updated" fired two minutes before
  // the new jobs landed. A pull still in flight goes to the shared search
  // runner, whose completion toast names the real finish and new-job count.
  it('hands an unfinished pull to the search runner instead of saying done', () => {
    const { rendered } = setup();

    act(() => rendered.result.current.start());
    const callbacks = mocks.mutate.mock.calls[0][1] as RunCallbacks;
    act(() => callbacks.onSuccess({ ok: true, result: 'ranked', pull_run_id: 'pull1' }));

    expect(mocks.activate.mock.calls[0]?.slice(0, 2)).toEqual(['pull1', 'search_only']);
    for (const call of mocks.success.mock.calls) {
      expect(String(call[0])).not.toMatch(/board updated/i);
    }
  });

  it('still reports a failed run', () => {
    const { rendered } = setup();

    act(() => rendered.result.current.start());
    const callbacks = mocks.mutate.mock.calls[0][1] as RunCallbacks;
    act(() => callbacks.onSuccess({ ok: false, error: 'Assistant stopped early' }));

    expect(mocks.error).toHaveBeenCalledWith('Assistant stopped early');
  });
});
