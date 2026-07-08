import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Sheet } from './Sheet';

describe('Sheet', () => {
  it('renders title, meta, and children when open', () => {
    render(
      <Sheet open onClose={() => {}} label="Make a party" title="Make a party" meta="Sprite ad. $1,000 /day each.">
        <p className="qb-hint">Copy the note into your group chat.</p>
      </Sheet>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Make a party' });
    expect(dialog).toHaveTextContent('Sprite ad. $1,000 /day each.');
    expect(dialog).toHaveTextContent('Copy the note into your group chat.');
  });

  it('stays hidden while closed', () => {
    const { container } = render(
      <Sheet open={false} onClose={() => {}} label="Make a party" title="Make a party" />,
    );
    expect(container.querySelector('.qb-scrim.qb-on')).toBeNull();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<Sheet open onClose={onClose} label="Explain this quest" title="Explain" />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('closes on a scrim click but not on a sheet click', () => {
    const onClose = vi.fn();
    const { container } = render(<Sheet open onClose={onClose} label="Explain this quest" title="Explain" />);
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(container.querySelector('.qb-scrim')!);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
