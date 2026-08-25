// @vitest-environment jsdom
/* The quest restock door must actually restock quests: it posts to the
   quest refresh endpoint with quest verticals only, never the career
   pipeline, and reports pending and done in plain words. */

import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

afterEach(cleanup);

vi.mock('@/lib/api-client', () => ({ apiPost: vi.fn() }));
vi.mock('@questboard/ui', () => ({
  SageButton: (props: Record<string, unknown>) => <button type="button" {...props} />,
}));

import { apiPost } from '@/lib/api-client';
import { QuestRestockButton } from './quest-restock';
import { questRestockDoneLine } from './quest-restock-logic';

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const summary = {
  verticals: ['think'],
  found: 3,
  saved: 2,
  deduped: 1,
  skipped_stale: 0,
  expired: 0,
  sources: {},
};

describe('the quest restock button', () => {
  beforeEach(() => {
    (apiPost as Mock).mockReset();
  });

  it('posts quest verticals to the refresh endpoint, never career', async () => {
    (apiPost as Mock).mockResolvedValue(summary);
    renderWithClient(<QuestRestockButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(await screen.findByText('2 new quests pinned.')).toBeTruthy();

    expect(apiPost).toHaveBeenCalledTimes(1);
    const [path, body] = (apiPost as Mock).mock.calls[0] as [string, { verticals: string[] }];
    expect(path).toBe('/quests/refresh');
    expect(body.verticals).toContain('think');
    expect(body.verticals).not.toContain('career');
    expect(body.verticals).not.toContain('work');
  });

  it('says it is checking while the sweep runs', async () => {
    let resolve: (value: typeof summary) => void = () => {};
    (apiPost as Mock).mockReturnValue(new Promise((r) => { resolve = r; }));
    renderWithClient(<QuestRestockButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(await screen.findByText('Checking the quest sources.')).toBeTruthy();

    resolve(summary);
    expect(await screen.findByText('2 new quests pinned.')).toBeTruthy();
  });

  it('shows the server sentence when the check is refused', async () => {
    (apiPost as Mock).mockRejectedValue(
      new Error('The board restocks itself here; fresh quests land on their own.'),
    );
    renderWithClient(<QuestRestockButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(
      await screen.findByText('The board restocks itself here; fresh quests land on their own.'),
    ).toBeTruthy();
  });

  /* The audit case: a failed check replaced the button with its own error
     and the reader had no way to try again without a remount. The trigger
     stays; the message lands beside it. */
  it('keeps the door open for a retry after a failed check', async () => {
    (apiPost as Mock).mockRejectedValueOnce(new Error('The sources timed out.'));
    renderWithClient(<QuestRestockButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(await screen.findByText('The sources timed out.')).toBeTruthy();

    (apiPost as Mock).mockResolvedValueOnce(summary);
    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(await screen.findByText('2 new quests pinned.')).toBeTruthy();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it('keeps the button through a success so another check stays one tap away', async () => {
    (apiPost as Mock).mockResolvedValue(summary);
    renderWithClient(<QuestRestockButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Check for new quests' }));
    expect(await screen.findByText('2 new quests pinned.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Check for new quests' })).toBeTruthy();
  });
});

describe('the done line', () => {
  it('counts plainly and never celebrates', () => {
    expect(questRestockDoneLine(0)).toBe('Checked. Nothing new right now.');
    expect(questRestockDoneLine(1)).toBe('1 new quest pinned.');
    expect(questRestockDoneLine(12)).toBe('12 new quests pinned.');
  });
});
