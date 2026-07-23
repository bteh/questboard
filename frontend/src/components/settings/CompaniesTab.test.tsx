// @vitest-environment jsdom
/* Companies tab data flow: list the watched companies with their ATS info,
   add one by name or careers link (the backend resolves the board), remove
   one, and keep the empty and error states to one plain line each. Entries
   without a confirmed board render as unfinished, with an inline input to
   paste the careers link. It talks to the WORKSPACE companies store (the one
   the pull reads), so the api module is mocked with a small in-memory list and
   react-query's invalidate-and-refetch cycle runs for real. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { WatchlistAddPayload, WatchlistCompany } from '@/api/watchlist';

vi.mock('@/api/workspace-companies', () => ({
  getWorkspaceCompanies: vi.fn(),
  addWorkspaceCompany: vi.fn(),
  removeWorkspaceCompany: vi.fn(),
}));

import {
  getWorkspaceCompanies,
  addWorkspaceCompany,
  removeWorkspaceCompany,
} from '@/api/workspace-companies';
import { CompaniesTab } from './CompaniesTab';

const mockGet = vi.mocked(getWorkspaceCompanies);
const mockAdd = vi.mocked(addWorkspaceCompany);
const mockRemove = vi.mocked(removeWorkspaceCompany);

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

function unknownCompany(name = 'Umbra'): WatchlistCompany {
  return company({ name, slug: '', ats: 'unknown', job_count: 0, careers_url: '' });
}

function respond(message = '') {
  return Promise.resolve({ profile: 'workspace', companies: [...serverCompanies], message });
}

function applyAdd(payload: WatchlistAddPayload): WatchlistCompany {
  // Mimic the backend: a URL resolves to a lever board, a bare name
  // stays unresolved until "discovery" (the default mock resolves it).
  const name = payload.name || 'Umbra';
  const resolved = payload.url
    ? company({ name, slug: 'umbra-hq', ats: 'lever', job_count: 4, careers_url: payload.url })
    : company({ name });
  const index = serverCompanies.findIndex((c) => c.name === name);
  if (index >= 0) serverCompanies[index] = resolved;
  else serverCompanies.push(resolved);
  return resolved;
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
  mockAdd.mockImplementation((payload) => {
    applyAdd(payload);
    return respond();
  });
  mockRemove.mockImplementation((name) => {
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
      await screen.findByText('No companies yet. Add one to check its job board on every refresh.'),
    ).toBeDefined();
  });

  it('adds a company by name and clears the input', async () => {
    renderTab();
    await screen.findByText(/No companies yet/);

    const input = screen.getByLabelText('Company name or careers link') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Netflix' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(mockAdd).toHaveBeenCalledWith({ name: 'Netflix' }));
    expect(await screen.findByText('Netflix')).toBeDefined();
    await waitFor(() => expect(input.value).toBe(''));
  });

  it('sends a pasted careers link as a url, not a name', async () => {
    renderTab();
    await screen.findByText(/No companies yet/);

    const input = screen.getByLabelText('Company name or careers link') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'https://jobs.lever.co/umbra-hq' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith({ url: 'https://jobs.lever.co/umbra-hq' }),
    );
    expect(await screen.findByText('Umbra')).toBeDefined();
  });

  it('renders an unknown entry as unfinished with a paste input', async () => {
    serverCompanies = [unknownCompany()];
    renderTab();

    expect(await screen.findByText('Umbra')).toBeDefined();
    expect(screen.getByText(/Job board not found yet/)).toBeDefined();
    expect(screen.getByLabelText('Careers link for Umbra')).toBeDefined();
    // An unfinished row never renders as a healthy board line.
    expect(screen.queryByText(/open roles/)).toBeNull();
  });

  it('completes an unknown entry from its pasted careers link', async () => {
    serverCompanies = [unknownCompany()];
    renderTab();
    await screen.findByText(/Job board not found yet/);

    const input = screen.getByLabelText('Careers link for Umbra');
    fireEvent.change(input, { target: { value: 'https://jobs.lever.co/umbra-hq' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save link for Umbra' }));

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith({
        name: 'Umbra',
        url: 'https://jobs.lever.co/umbra-hq',
      }),
    );
    expect(await screen.findByText(/Lever board/)).toBeDefined();
    await waitFor(() => expect(screen.queryByText(/Job board not found yet/)).toBeNull());
  });

  it('surfaces the add response message when discovery fails', async () => {
    mockAdd.mockImplementation((payload) => {
      serverCompanies.push(unknownCompany(payload.name ?? ''));
      return respond('Could not find a job board for Umbra. Paste its careers page link to finish setup.');
    });
    renderTab();
    await screen.findByText(/No companies yet/);

    fireEvent.change(screen.getByLabelText('Company name or careers link'), {
      target: { value: 'Umbra' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText(
        'Could not find a job board for Umbra. Paste its careers page link to finish setup.',
      ),
    ).toBeDefined();
    expect(await screen.findByText(/Job board not found yet/)).toBeDefined();
  });

  it('shows the server message when a pasted link is rejected', async () => {
    const rejection = Object.assign(
      new Error(
        'Paste a careers link from Greenhouse, Lever, Ashby, or Workday. Other job boards are not supported yet.',
      ),
      { status: 422 },
    );
    mockAdd.mockRejectedValue(rejection);
    renderTab();
    await screen.findByText(/No companies yet/);

    fireEvent.change(screen.getByLabelText('Company name or careers link'), {
      target: { value: 'https://example.com/careers' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText(
        'Paste a careers link from Greenhouse, Lever, Ashby, or Workday. Other job boards are not supported yet.',
      ),
    ).toBeDefined();
  });

  it('disables the add button while the add is in flight', async () => {
    let release: () => void = () => {};
    mockAdd.mockImplementation(
      (payload) =>
        new Promise((resolve) => {
          release = () => {
            applyAdd(payload);
            respond().then(resolve);
          };
        }),
    );
    renderTab();
    await screen.findByText(/No companies yet/);

    fireEvent.change(screen.getByLabelText('Company name or careers link'), {
      target: { value: 'Netflix' },
    });
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

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('Alo Yoga'));
    await waitFor(() => expect(screen.queryByText('Alo Yoga')).toBeNull());
  });

  it('still removes an entry whose board was never found', async () => {
    serverCompanies = [unknownCompany()];
    renderTab();
    await screen.findByText('Umbra');

    fireEvent.click(screen.getByRole('button', { name: 'Remove Umbra' }));

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('Umbra'));
    await waitFor(() => expect(screen.queryByText('Umbra')).toBeNull());
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

    fireEvent.change(screen.getByLabelText('Company name or careers link'), {
      target: { value: 'Netflix' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText('Could not add that company. Check the name and try again.'),
    ).toBeDefined();
  });
});
