import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { NotFoundPage } from './not-found';

describe('NotFoundPage', () => {
  it('renders the line and the one door back in', () => {
    const html = renderToStaticMarkup(<NotFoundPage />);
    expect(html).toContain('That page is not on the board.');
    expect(html).toContain('Go to the board');
    expect(html).toContain('href="/board"');
  });
});
