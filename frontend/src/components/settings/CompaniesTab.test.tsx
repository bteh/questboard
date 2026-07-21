// @vitest-environment jsdom
/* Companies tab data flow: list the watched companies with their ATS info,
   add one by name (the backend does the ATS discovery), remove one, and
   keep the empty and error states to one plain line each. The api module
   is mocked with a small in-memory watchlist so react-query's
   invalidate-and-refetch cycle runs for real. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { WatchlistCompany } from '@/api/watchlist';

vi.mock('@/contexts/profile-context', () => ({
  useProfile: () => ({ profile: 'default', setProfile: vi.fn() }),
}));

vi.mock('@/api/watchlist', () => ({
  getWatchlist: vi.fn(),
  addWatchlistCompany: vi.fn(),
  removeWatchlistCompany: vi.fn(),
}));

import { getWatchlist, addWatchlistCompany, removeWatchlistCompany } from '@/api/watchlist';
import { CompaniesTab } from './CompaniesTab';

const mockGet = vi.mocked(getWatchlist);
const mockAdd = vi.mocked(addWatchlistCompany);
const mockRemove = vi.mocked(removeWatchlistCompany);

let serverCompanies: WatchlistCompany[];

function company(overrides: Partial<WatchlistCompany> = {}): WatchlistCompany {
  return {
    name: 'Alo Yoga',
    slug: 'aloyoga',
    ats: 'greenhouse',
    job_count: 12,
    careers_url: 'https://boards.greenhouse.io/aloyoga',
    ...overrides,
  };
}

function respond() {
  return Promise.resolve({ profile: 'default', companies: [...serverCompanies] });
}

function renderTab() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <CompaniesTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  serverCompanies = [];
  mockGet.mockImplementation(() => respond());
  mockAdd.mockImplementation((_profile, name) => {
    serverCompanies.push(company({ name, slug: '', ats: '', job_count: 0, careers_url: '' }));
    return respond();
  });
  mockRemove.mockImplementation((_profile, name) => {
    serverCompanies = serverCompanies.filter((c) => c.name !== name);
    return respond();
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('CompaniesTab', () => {
  it('lists watched companies with their ATS info', async () => {
    serverCompanies = [company()];
    renderTab();

    expect(await screen.findByText('Alo Yoga')).toBeDefined();
    // ATS name and open-role count come straight from the API row.
    expect(screen.getByText(/Greenhouse/)).toBeDefined();
    expect(screen.getByText(/12 open roles/)).toBeDefined();
  });

  it('shows a one-line invite when the list is empty', async () => {
    renderTab();

    expect(
      await screen.findByText('No companies yet. Add one and its job board gets checked on every refresh.'),
    ).toBeDefined();
  });

  it('adds a company by name and clears the input', async () => {
    renderTab();
    await screen.findByText(/No companies yet/);

    const input = screen.getByLabelText('Company name') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Netflix' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(mockAdd).toHaveBeenCalledWith('default', 'Netflix'));
    expect(await screen.findByText('Netflix')).toBeDefined();
    await waitFor(() => expect(input.value).toBe(''));
  });

  it('disables the add button while the add is in flight', async () => {
    let release: () => void = () => {};
    mockAdd.mockImplementation(
      (_profile, name) =>
        new Promise((resolve) => {
          release = () => {
            serverCompanies.push(company({ name, ats: '', job_count: 0, careers_url: '' }));
            respond().then(resolve);
          };
        }),
    );
    renderTab();
    await screen.findByText(/No companies yet/);

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Netflix' } });
    const button = screen.getByRole('button', { name: 'Add' });
    fireEvent.click(button);

    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(true));
    release();
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  });

  it('removes a company from the list', async () => {
    serverCompanies = [company()];
    renderTab();
    await screen.findByText('Alo Yoga');

    fireEvent.click(screen.getByRole('button', { name: 'Remove Alo Yoga' }));

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('default', 'Alo Yoga'));
    await waitFor(() => expect(screen.queryByText('Alo Yoga')).toBeNull());
  });

  it('shows a plain line when the list cannot load', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    renderTab();

    expect(
      await screen.findByText('Could not load your companies. Try again in a moment.'),
    ).toBeDefined();
  });

  it('shows a plain line when an add fails', async () => {
    mockAdd.mockRejectedValue(new Error('boom'));
    renderTab();
    await screen.findByText(/No companies yet/);

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Netflix' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText('Could not add that company. Check the name and try again.'),
    ).toBeDefined();
  });
});
