// @vitest-environment jsdom
/* Places I'd work at: list watched careers pages, add one by link (the
   backend reads it once and says what it found), add a starter suggestion
   in one click, show a failed read as a plain line, remove one. The api
   module is mocked with a small in-memory store. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { WatchedPage, WatchedPageSuggestion } from '@/api/watched-pages';

vi.mock('@/api/watched-pages', () => ({
  getWatchedPages: vi.fn(),
  addWatchedPage: vi.fn(),
  removeWatchedPage: vi.fn(),
}));

import { addWatchedPage, getWatchedPages, removeWatchedPage } from '@/api/watched-pages';
import { WatchedPagesSection } from './WatchedPagesSection';

const mockGet = vi.mocked(getWatchedPages);
const mockAdd = vi.mocked(addWatchedPage);
const mockRemove = vi.mocked(removeWatchedPage);

const ELOREA = 'https://elorea.com/pages/career-opportunities';
const STARTERS: WatchedPageSuggestion[] = [
  {
    name: 'ELOREA',
    url: ELOREA,
    area: 'Koreatown, LA',
    hosting: 'Shopify page, Smoothie job app',
    note: 'Fragrance shop and cafe.',
  },
];

let serverPages: WatchedPage[];

function page(overrides: Partial<WatchedPage> = {}): WatchedPage {
  return {
    id: 1,
    url: ELOREA,
    name: 'ELOREA',
    added_at: '2026-10-08T00:00:00',
    last_checked_at: '2026-10-08T00:00:00',
    last_found: 2,
    last_error: '',
    ...overrides,
  };
}

function respond(message = '') {
  const watched = new Set(serverPages.map((p) => p.url));
  return Promise.resolve({
    pages: [...serverPages],
    suggestions: STARTERS.filter((s) => !watched.has(s.url)),
    message,
  });
}

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WatchedPagesSection />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  serverPages = [];
  mockGet.mockImplementation(() => respond());
  mockAdd.mockImplementation((url) => {
    serverPages.push(page({ id: serverPages.length + 1, url, name: 'ELOREA' }));
    return respond('2 part-time openings near you. They land on the board at the next refresh.');
  });
  mockRemove.mockImplementation((id) => {
    serverPages = serverPages.filter((p) => p.id !== id);
    return respond();
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('WatchedPagesSection', () => {
  it('shows the empty line and the starter suggestion', async () => {
    renderSection();
    expect(await screen.findByText('No places yet.')).toBeDefined();
    expect(screen.getByText('Places to try')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Add ELOREA' })).toBeDefined();
  });

  it('adds a pasted link and shows what the page held', async () => {
    renderSection();
    await screen.findByText('No places yet.');

    const input = screen.getByLabelText('Careers page link') as HTMLInputElement;
    fireEvent.change(input, { target: { value: ' https://shop.com/careers ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(mockAdd).toHaveBeenCalledWith('https://shop.com/careers'));
    expect(await screen.findByText(/2 part-time openings near you\. They land/)).toBeDefined();
    await waitFor(() => expect(input.value).toBe(''));
  });

  it('adds a suggestion in one click and drops it from the list', async () => {
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: 'Add ELOREA' }));

    await waitFor(() => expect(mockAdd).toHaveBeenCalledWith(ELOREA));
    expect(await screen.findByRole('button', { name: 'Remove ELOREA' })).toBeDefined();
    expect(screen.queryByText('Places to try')).toBeNull();
  });

  it('shows the plain reason when a page cannot be read', async () => {
    mockAdd.mockImplementation(() =>
      Promise.reject(new Error("That site's robots.txt asks tools not to read this page.")),
    );
    renderSection();
    await screen.findByText('No places yet.');

    fireEvent.change(screen.getByLabelText('Careers page link'), {
      target: { value: 'https://blocked.example.com/jobs' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(await screen.findByText(/robots\.txt asks tools not to read/)).toBeDefined();
  });

  it('lists a watched page with its last check and removes it', async () => {
    serverPages = [page(), page({ id: 2, url: 'https://gone.example.com/jobs', name: 'Gone', last_found: 0, last_error: 'Could not reach that page.' })];
    renderSection();

    expect(await screen.findByText(/2 part-time openings near you/)).toBeDefined();
    expect(screen.getByText(/Last check failed\. Could not reach that page\./)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Remove Gone' }));
    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith(2));
    await waitFor(() => expect(screen.queryByText('Gone')).toBeNull());
  });
});
