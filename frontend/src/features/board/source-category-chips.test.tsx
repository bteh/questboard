// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SourceCategoryChips } from './source-category-chips';

afterEach(cleanup);

describe('SourceCategoryChips', () => {
  it('keeps Founding with the board filters even before source counts load', () => {
    render(
      <SourceCategoryChips
        counts={undefined}
        selected={null}
        onSelect={() => {}}
        foundingOnly={false}
        onFoundingToggle={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: 'Founding' }).getAttribute('aria-pressed')).toBe(
      'false',
    );
  });

  it('lets Founding compose with a selected source category', () => {
    const onFoundingToggle = vi.fn();
    render(
      <SourceCategoryChips
        counts={{ vc: 12, crypto: 4 }}
        selected="vc"
        onSelect={() => {}}
        foundingOnly
        onFoundingToggle={onFoundingToggle}
      />,
    );

    expect(screen.getByRole('button', { name: 'Founding' }).getAttribute('aria-pressed')).toBe(
      'true',
    );
    expect(
      screen.getByRole('button', { name: /VC portfolios/ }).getAttribute('aria-pressed'),
    ).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Founding' }));
    expect(onFoundingToggle).toHaveBeenCalledOnce();
  });

  it('clears a selected source when its chip is clicked again', () => {
    const onSelect = vi.fn();
    render(
      <SourceCategoryChips
        counts={{ remote: 9 }}
        selected="remote"
        onSelect={onSelect}
        foundingOnly={false}
        onFoundingToggle={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Remote/ }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('labels startup as an employer and founding-seat shelf', () => {
    render(
      <SourceCategoryChips
        counts={{ startup: 7 }}
        selected={null}
        onSelect={() => {}}
        foundingOnly={false}
        onFoundingToggle={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: 'Startups & founding 7' })).toBeTruthy();
  });
});
