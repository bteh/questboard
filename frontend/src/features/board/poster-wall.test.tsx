// @vitest-environment jsdom
/* The wall wires the poster's clipped stamp to the log: a clipped row's
   stamp says where it went and clicking it navigates to /log. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ApplicationResponse } from '@/types/application';

const navigate = vi.fn();
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}));
vi.mock('@/hooks/use-scrapers', () => ({
  resolveSourceLabel: (source: string) => source,
}));
vi.mock('@/hooks/use-applications', () => ({
  useUpdateStatus: () => ({ mutate: vi.fn() }),
}));

import { PosterWall } from './poster-wall';

function app(overrides: Partial<ApplicationResponse> = {}): ApplicationResponse {
  return {
    id: 7,
    job_title: 'Snack focus group',
    company: 'Fieldwork',
    location: 'Chicago',
    job_url: 'https://example.com/q',
    source: 'focusgroups_org',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
    salary_currency: '',
    salary_period: '',
    overall_score: null,
    recommendation: '',
    status: 'found',
    vertical: 'study',
    first_quest_ok: false,
    ...overrides,
  } as ApplicationResponse;
}

afterEach(() => {
  cleanup();
  navigate.mockClear();
});

describe('PosterWall clipped stamp', () => {
  it('sends the clipped stamp to the log', () => {
    render(
      <PosterWall
        items={[app({ status: 'clipped', updated_at: '2026-07-06T10:00:00' })]}
        labels={{}}
        onOpenSheet={() => {}}
        onExplain={() => {}}
      />,
    );
    const stamp = screen.getByRole('button', { name: /in your log/ });
    fireEvent.click(stamp);
    expect(navigate).toHaveBeenCalledWith({ to: '/log' });
  });

  it('leaves an unclipped poster with its plain Clip button', () => {
    render(
      <PosterWall
        items={[app()]}
        labels={{}}
        onOpenSheet={() => {}}
        onExplain={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: 'Clip' })).toBeTruthy();
    expect(screen.queryByText(/in your log/)).toBeNull();
  });
});
