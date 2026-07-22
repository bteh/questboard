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

describe('PosterWall fit grouping', () => {
  const withFit = (
    id: number,
    verdict: 'strong' | 'good' | 'reach' | 'skip',
    rank: number | null,
  ) =>
    app({
      id,
      vertical: 'career',
      job_title: `Job ${id}`,
      company: 'Stripe',
      agent_fit: { rank, verdict, why: '', caveat: '' },
    });

  it('renders the digest, labeled group rules, and the skip fold', () => {
    render(
      <PosterWall
        items={[withFit(3, 'skip', null), withFit(1, 'strong', 1), withFit(2, 'good', 2)]}
        labels={{}}
        fitGrouped
        onOpenSheet={() => {}}
        onExplain={() => {}}
      />,
    );
    expect(screen.getByText('Your assistant ranked 2 jobs: 1 strong, 1 good.')).toBeTruthy();
    expect(screen.getByText('Strong fit (1)')).toBeTruthy();
    expect(screen.getByText('Good fit (1)')).toBeTruthy();
    /* an empty group renders nothing */
    expect(screen.queryByText(/Worth a reach/)).toBeNull();
    /* the skipped row lives inside the native fold, not the open wall */
    const summary = screen.getByText('Skipped by your assistant (1)');
    const fold = summary.closest('details');
    expect(fold).toBeTruthy();
    expect(fold!.textContent).toContain('Job 3');
  });

  it('keeps the plain wall exactly as today when fit grouping is off', () => {
    render(
      <PosterWall
        items={[withFit(1, 'strong', 1)]}
        labels={{}}
        onOpenSheet={() => {}}
        onExplain={() => {}}
      />,
    );
    expect(screen.queryByText(/Strong fit \(/)).toBeNull();
    expect(screen.queryByText(/Your assistant ranked/)).toBeNull();
    expect(screen.queryByText(/Skipped by your assistant/)).toBeNull();
  });
});

/* WebKit repaints multicol fragments around column-span elements on every
   hover of a transformed child, which flickered the desktop app. The wall
   therefore renders one .qb-wall columns block per segment, with digest,
   rules, and the skip fold BETWEEN blocks, never inside one. */
describe('wall segments avoid column spanners', () => {
  const ranked = [
    app({ id: 1, vertical: 'career', agent_fit: { verdict: 'strong', rank: 1, why: 'w', caveat: '' } }),
    app({ id: 2, vertical: 'career', agent_fit: { verdict: 'reach', rank: 2, why: 'w', caveat: '' } }),
    app({ id: 3, vertical: 'career', agent_fit: { verdict: 'skip', why: 'w', caveat: '', rank: null } }),
  ] as ApplicationResponse[];

  afterEach(cleanup);

  it('fit-grouped: rules and digest sit between walls, posters inside walls', () => {
    const { container } = render(
      <PosterWall items={ranked} labels={{}} onOpenSheet={() => {}} onExplain={() => {}} fitGrouped />,
    );
    const walls = container.querySelectorAll('.qb-wall');
    expect(walls.length).toBeGreaterThanOrEqual(2);
    for (const cls of ['.qb-fit-digest', '.qb-fit-rule', '.qb-skip-fold']) {
      for (const el of container.querySelectorAll(cls)) {
        expect(el.closest('.qb-wall')).toBeNull();
      }
    }
    for (const poster of container.querySelectorAll('.qb-poster')) {
      expect(poster.closest('.qb-wall, .qb-skip-posters')).not.toBeNull();
    }
  });

  it('plain wall: posters render inside a single .qb-wall block', () => {
    const { container } = render(<PosterWall items={[app()]} labels={{}} onOpenSheet={() => {}} onExplain={() => {}} />);
    expect(container.querySelectorAll('.qb-wall').length).toBe(1);
    expect(container.querySelector('.qb-wall .qb-poster')).not.toBeNull();
  });
});
