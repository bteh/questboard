// @vitest-environment jsdom
/* The Clip bug, end to end at the mutation level: the Find Work board reads
   ['profile-work', filters] caches (board.tsx careerLane), so useUpdateStatus
   must optimistically patch those rows, invalidate the family on settle, and
   roll the same rows back when the request fails. */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, act } from '@testing-library/react';
import type { ApplicationListResponse, ApplicationResponse } from '@/types/application';

vi.mock('@/api/applications', () => ({
  getApplications: vi.fn(),
  getApplication: vi.fn(),
  createApplication: vi.fn(),
  updateApplication: vi.fn(),
  updateApplicationStatus: vi.fn(),
  updateApplicationFeedback: vi.fn(),
  deleteApplication: vi.fn(),
  deduplicateApplications: vi.fn(),
}));

import { updateApplicationStatus } from '@/api/applications';
import { useUpdateStatus } from './use-applications';

function row(id: number, status: string): ApplicationResponse {
  return {
    id,
    job_title: `Job ${id}`,
    company: '',
    location: '',
    job_url: '',
    source: 'greenhouse',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
    status,
  } as unknown as ApplicationResponse;
}

function list(items: ApplicationResponse[]): ApplicationListResponse {
  return { items, total: items.length, page: 1, page_size: 100 };
}

const APPS_KEY = ['applications', { status: 'clipped,shelved', page: 1 }];
const WORK_KEY = ['profile-work', { sort_by: 'rank', page: 1 }];

function setup() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  qc.setQueryData(APPS_KEY, list([row(7, 'found')]));
  qc.setQueryData(WORK_KEY, list([row(7, 'found'), row(8, 'found')]));
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  const rendered = renderHook(() => useUpdateStatus(), { wrapper });
  return { qc, rendered };
}

beforeEach(() => {
  vi.mocked(updateApplicationStatus).mockReset();
});

describe('useUpdateStatus and the Find Work board cache', () => {
  it('clipping flips the profile-work row and invalidates the family', async () => {
    vi.mocked(updateApplicationStatus).mockResolvedValue(row(7, 'clipped'));
    const { qc, rendered } = setup();

    await act(async () => {
      await rendered.result.current.mutateAsync({ id: 7, data: { status: 'clipped' } });
    });

    const work = qc.getQueryData<ApplicationListResponse>(WORK_KEY)!;
    expect(work.items.find((i) => i.id === 7)?.status).toBe('clipped');
    expect(work.items.find((i) => i.id === 8)?.status).toBe('found');
    expect(qc.getQueryData<ApplicationListResponse>(APPS_KEY)!.items[0].status).toBe('clipped');
    /* settle must mark the board's queries stale so the server truth refetches */
    expect(qc.getQueryState(WORK_KEY)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(APPS_KEY)?.isInvalidated).toBe(true);
  });

  it('a failed request rolls both cache families back', async () => {
    vi.mocked(updateApplicationStatus).mockRejectedValue(new Error('500'));
    const { qc, rendered } = setup();

    await act(async () => {
      await expect(
        rendered.result.current.mutateAsync({ id: 7, data: { status: 'clipped' } }),
      ).rejects.toThrow('500');
    });

    expect(qc.getQueryData<ApplicationListResponse>(WORK_KEY)!.items[0].status).toBe('found');
    expect(qc.getQueryData<ApplicationListResponse>(APPS_KEY)!.items[0].status).toBe('found');
  });
});
