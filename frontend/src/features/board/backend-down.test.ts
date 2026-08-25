/* One sentence for a dead backend, honest per surface. The audit found the
   packaged desktop app telling readers to run `make dev`, a command that
   means nothing outside a dev checkout. */

import { describe, expect, it } from 'vitest';
import { backendDownLine } from './backend-down';

describe('the backend-down line', () => {
  it('tells the packaged app reader to restart the app, never to run make dev', () => {
    const line = backendDownLine(true);
    expect(line).toBe("The board's background service stopped. Quit and reopen the app.");
    expect(line).not.toContain('make dev');
  });

  it('keeps the make dev line for the dev browser', () => {
    expect(backendDownLine(false)).toBe(
      'The board could not reach the backend. Start it with make dev and reload.',
    );
  });
});
