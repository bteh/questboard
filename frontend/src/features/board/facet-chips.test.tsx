// @vitest-environment jsdom
/* The facet chips: a kind with facets gets one quiet row of its own
   sub-filters, each chip threading the facet param into the applications
   query; kinds without facets render nothing at all. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ApplicationFilters } from '@/types/application';

const seenFilters: ApplicationFilters[] = [];
vi.mock('@/hooks/use-applications', () => ({
  useApplications: (filters: ApplicationFilters) => {
    seenFilters.push(filters);
    return { data: { items: [], total: 7, page: 1, page_size: 1 } };
  },
}));

import { FacetChips } from './facet-chips';

const countBase: ApplicationFilters = {
  vertical: 'lookafter',
  upcoming_only: true,
  scope: 'board',
  page_size: 24,
};

afterEach(() => {
  cleanup();
  seenFilters.length = 0;
});

describe('FacetChips', () => {
  it('renders the lookafter facets as chips', () => {
    render(
      <FacetChips kind="lookafter" selected={undefined} countBase={countBase} onToggle={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /pets/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /kids/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /houses/ })).toBeTruthy();
  });

  it('threads each facet id into its count query, on the board filters', () => {
    render(
      <FacetChips kind="lookafter" selected={undefined} countBase={countBase} onToggle={() => {}} />,
    );
    const facets = seenFilters.map((f) => f.facet);
    expect(facets).toEqual(['pets', 'kids', 'houses']);
    for (const filters of seenFilters) {
      expect(filters.vertical).toBe('lookafter');
      /* counts are the API's own totals: a tiny page 1 probe */
      expect(filters.page_size).toBe(1);
    }
  });

  it('shows the API total on each chip', () => {
    render(
      <FacetChips kind="lookafter" selected={undefined} countBase={countBase} onToggle={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /pets/ }).textContent).toContain('7');
  });

  it('reports the clicked facet so the route can thread ?f=', () => {
    const onToggle = vi.fn();
    render(
      <FacetChips kind="lookafter" selected={undefined} countBase={countBase} onToggle={onToggle} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /pets/ }));
    expect(onToggle).toHaveBeenCalledWith('pets');
  });

  it('marks only the selected facet active', () => {
    render(
      <FacetChips kind="lookafter" selected="pets" countBase={countBase} onToggle={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /pets/ }).className).toContain('qb-active');
    expect(screen.getByRole('button', { name: /kids/ }).className).not.toContain('qb-active');
  });

  it('renders nothing for a kind without facets', () => {
    const { container } = render(
      <FacetChips kind="odd" selected={undefined} countBase={countBase} onToggle={() => {}} />,
    );
    expect(container.innerHTML).toBe('');
  });
});
