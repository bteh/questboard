// @vitest-environment jsdom
/* The download CTA must never be a dead or fake button. With no release URL
   and no notify endpoint configured (the state today), it falls back to an
   honest mailto action, and it says plainly that the build isn't out yet. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { DownloadOrNotify } from './download-cta';

afterEach(cleanup);

describe('DownloadOrNotify (no env configured)', () => {
  it('offers a real notify action, never a dead email field', () => {
    render(<DownloadOrNotify big />);
    // A clickable action exists...
    expect(screen.getByRole('button', { name: /mac build is ready/i })).toBeTruthy();
    // ...and it is NOT a bare form input that goes nowhere.
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('states honestly that the signed build is not out yet', () => {
    render(<DownloadOrNotify />);
    expect(screen.getByText(/isn.t out yet/i)).toBeTruthy();
  });

  it('does not render a Download button when no release URL is set', () => {
    render(<DownloadOrNotify />);
    expect(screen.queryByRole('button', { name: /^download/i })).toBeNull();
  });
});

describe('DownloadOrNotify (release URL configured)', () => {
  it('renders a real Download button and no Gatekeeper warning', async () => {
    // import.meta.env is read at module load, so stub it and re-import.
    vi.stubEnv('VITE_DOWNLOAD_URL', 'https://example.test/Questboard.dmg');
    vi.resetModules();
    const { DownloadOrNotify: Configured } = await import('./download-cta');
    render(<Configured big />);
    expect(screen.getByRole('button', { name: /download for mac/i })).toBeTruthy();
    expect(screen.queryByText(/isn.t out yet/i)).toBeNull();
    // The build is signed and notarized now; a warning note would be a lie.
    expect(screen.queryByText(/privacy|warns/i)).toBeNull();
    vi.unstubAllEnvs();
    vi.resetModules();
  });
});
