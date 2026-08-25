// @vitest-environment jsdom
/* /start is the whole first run, so it must never trap anyone. Pinned by
   the audit case: skip with a dead backend left the user stuck on /start
   forever, because the marks and the navigate sat behind the network
   write. The door opens on local state alone; the write is background. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const navigateMock = vi.fn().mockResolvedValue(undefined);
const mutateAsyncMock = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  Link: ({
    children,
    className,
    onClick,
  }: {
    children: ReactNode;
    className?: string;
    onClick?: () => void;
    to?: unknown;
    search?: unknown;
  }) => (
    <a className={className} onClick={onClick}>
      {children}
    </a>
  ),
}));
vi.mock('@questboard/ui', () => ({
  SageButton: ({
    big: _big,
    children,
    ...rest
  }: Record<string, unknown> & { children?: ReactNode }) => (
    <button {...rest}>{children}</button>
  ),
}));
vi.mock('@/features/board/place-picker', () => ({
  PlacePicker: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string;
    onChange: (next: string) => void;
    ariaLabel?: string;
  }) => (
    <input aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock('@/components/landing/world', () => ({ World: () => null }));
vi.mock('@/hooks/use-workspace', () => ({
  useOnboardingState: () => ({ data: undefined }),
  useSaveWorkspacePreferences: () => ({ mutateAsync: mutateAsyncMock, isPending: false }),
}));

import { StartPage } from './start-page';

describe('the start page door', () => {
  beforeEach(() => {
    window.localStorage.clear();
    navigateMock.mockClear();
    mutateAsyncMock.mockReset();
  });
  afterEach(cleanup);

  it('skip opens the board even when the preference write fails', async () => {
    mutateAsyncMock.mockRejectedValueOnce(new Error('backend down')).mockResolvedValue(undefined);
    render(<StartPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Skip, show me everything' }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalled());
    expect(navigateMock.mock.calls[0][0]).toMatchObject({ to: '/board' });
    expect(window.localStorage.getItem('questboard:onboarded')).toBe('1');
  });

  it('marks the first-run pull pending so the work lane fills itself', async () => {
    mutateAsyncMock.mockResolvedValue(undefined);
    render(<StartPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Skip, show me everything' }));

    await waitFor(() =>
      expect(window.localStorage.getItem('questboard:first-run-pending')).toBe('1'),
    );
  });

  it('answering the place question still opens the board on a dead backend', async () => {
    mutateAsyncMock.mockRejectedValueOnce(new Error('backend down')).mockResolvedValue(undefined);
    render(<StartPage />);

    fireEvent.change(screen.getByLabelText('Your city, region, or country'), {
      target: { value: 'Austin, TX' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'See my board →' }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalled());
    expect(navigateMock.mock.calls[0][0]).toMatchObject({
      to: '/board',
      search: { place: 'Austin, TX' },
    });
    expect(window.localStorage.getItem('questboard:onboarded')).toBe('1');
  });

  it('offers the guided setup as a quiet second door', () => {
    mutateAsyncMock.mockResolvedValue(undefined);
    render(<StartPage />);

    expect(screen.getByText('guided setup')).toBeTruthy();
  });
});
