// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: mocks.success, error: mocks.error },
}));

vi.mock('@/hooks/use-agent-clients', () => ({
  useRunAgent: () => ({ mutate: mocks.mutate, isPending: false }),
}));

import { useRunAssistant } from './use-run-assistant';

interface RunCallbacks {
  onSuccess: (data: { ok: boolean; result?: string; error?: string }) => void;
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
    expect(mocks.success).not.toHaveBeenCalled();
  });

  it('still reports a failed run', () => {
    const { rendered } = setup();

    act(() => rendered.result.current.start());
    const callbacks = mocks.mutate.mock.calls[0][1] as RunCallbacks;
    act(() => callbacks.onSuccess({ ok: false, error: 'Assistant stopped early' }));

    expect(mocks.error).toHaveBeenCalledWith('Assistant stopped early');
  });
});
