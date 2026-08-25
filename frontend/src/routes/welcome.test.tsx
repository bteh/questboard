// @vitest-environment jsdom
/* Settings -> "See the front page" opens /welcome inside the desktop app.
   There the landing's download CTA ("Email me when the Mac build is
   ready") is nonsense: the build is already running. The route wraps the
   landing with a back bar and hides the download states, without touching
   any landing file. The last describe pins the CSS selectors the wrapper
   relies on against the real download-cta markup. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

let desktop = false;

vi.mock('@/lib/platform', () => ({ isDesktopApp: () => desktop }));
vi.mock('./__root', () => ({ Route: {} }));
vi.mock('@tanstack/react-router', () => ({
  createRoute: (options: unknown) => options,
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={String(to)} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/components/landing/landing-page', () => ({
  LandingPage: () => (
    <div data-testid="landing">
      <div className="qb-cta-stack">Email me when the Mac build is ready</div>
    </div>
  ),
}));

import { WelcomeFrontPage } from './welcome';

beforeEach(() => {
  desktop = false;
});

afterEach(() => {
  cleanup();
});

describe('/welcome on the web', () => {
  it('renders the landing bare, with no back bar', () => {
    render(<WelcomeFrontPage />);
    expect(screen.getByTestId('landing')).toBeTruthy();
    expect(screen.queryByText('Back to the board')).toBeNull();
    expect(document.querySelector('.qb-welcome-in-app')).toBeNull();
  });
});

describe('/welcome inside the desktop app', () => {
  it('offers Back to the board instead of the download states', () => {
    desktop = true;
    const { container } = render(<WelcomeFrontPage />);

    const back = screen.getByText('Back to the board').closest('a');
    expect(back?.getAttribute('href')).toBe('/board');
    expect(container.querySelector('.qb-welcome-in-app')).toBeTruthy();

    const css = container.querySelector('style')?.textContent ?? '';
    expect(css).toContain('.qb-welcome-in-app .qb-cta-stack');
    expect(css).toContain('.qb-welcome-in-app .qb-notify-form');
    expect(css).toContain('display: none');
  });
});

describe('the selectors the wrapper hides', () => {
  it('match the real mailto CTA markup', async () => {
    vi.resetModules();
    const { DownloadOrNotify } = await import('@/components/landing/download-cta');
    const { container } = render(<DownloadOrNotify />);
    expect(container.querySelector('.qb-cta-stack')).toBeTruthy();
  });

  it('match the real notify-form markup', async () => {
    vi.stubEnv('VITE_NOTIFY_ENDPOINT', 'https://notify.example/subscribe');
    vi.resetModules();
    try {
      const { DownloadOrNotify } = await import('@/components/landing/download-cta');
      const { container } = render(<DownloadOrNotify />);
      expect(container.querySelector('.qb-notify-form')).toBeTruthy();
    } finally {
      vi.unstubAllEnvs();
    }
  });
});
