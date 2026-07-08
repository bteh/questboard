import { describe, expect, it } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { patchApplicationLists } from './use-applications';
import type { ApplicationListResponse, ApplicationResponse } from '@/types/application';

/* The shared-cache proof for the log trio: /log, /log/ledger, and the board
   all cache under ['applications', filters] in one QueryClient. A status
   edit made on the log page must land in every cached list at once, so the
   Done ledger below and the full ledger page reflect it instantly. */

function row(id: number, status: string): ApplicationResponse {
  return {
    id,
    job_title: `Quest ${id}`,
    company: '',
    location: '',
    job_url: '',
    source: 'user',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
    salary_currency: '',
    salary_period: '',
    salary_min_annualized: null,
    salary_max_annualized: null,
    status,
  } as unknown as ApplicationResponse;
}

function list(items: ApplicationResponse[]): ApplicationListResponse {
  return { items, total: items.length, page: 1, page_size: 100 };
}

const LOG_KEY = ['applications', { vertical: 'career,camera,study,lens,party,personal', status: 'clipped,shelved' }];
const LEDGER_KEY = ['applications', { sort_by: 'overall_score', page: 1 }];

describe('patchApplicationLists', () => {
  it('writes one edit into every cached applications list at once', () => {
    const qc = new QueryClient();
    qc.setQueryData(LOG_KEY, list([row(7, 'clipped'), row(8, 'clipped')]));
    qc.setQueryData(LEDGER_KEY, list([row(7, 'clipped')]));

    patchApplicationLists(qc, 7, {
      status: 'paid_out',
      quest: { paid_out: 45 },
    });

    const log = qc.getQueryData<ApplicationListResponse>(LOG_KEY)!;
    const ledger = qc.getQueryData<ApplicationListResponse>(LEDGER_KEY)!;
    expect(log.items.find((i) => i.id === 7)?.status).toBe('paid_out');
    expect(log.items.find((i) => i.id === 7)?.quest).toEqual({ paid_out: 45 });
    expect(ledger.items[0].status).toBe('paid_out');
    /* the untouched row stays untouched */
    expect(log.items.find((i) => i.id === 8)?.status).toBe('clipped');
  });

  it('returns the previous entries so a failed mutation can roll back', () => {
    const qc = new QueryClient();
    qc.setQueryData(LOG_KEY, list([row(7, 'clipped')]));

    const previous = patchApplicationLists(qc, 7, { status: 'shelved' });
    expect(qc.getQueryData<ApplicationListResponse>(LOG_KEY)!.items[0].status).toBe('shelved');

    previous.forEach(([key, data]) => qc.setQueryData(key, data));
    expect(qc.getQueryData<ApplicationListResponse>(LOG_KEY)!.items[0].status).toBe('clipped');
  });

  it('leaves non-list caches (detail queries) alone', () => {
    const qc = new QueryClient();
    qc.setQueryData(['applications', 7], row(7, 'clipped'));
    patchApplicationLists(qc, 7, { status: 'paid_out' });
    expect(qc.getQueryData<ApplicationResponse>(['applications', 7])?.status).toBe('clipped');
  });
});
