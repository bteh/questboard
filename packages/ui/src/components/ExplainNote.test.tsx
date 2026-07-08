import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Sheet } from './Sheet';
import { ConsentCard, ExplainNote } from './ExplainNote';
import { PlainButton } from './PlainButton';
import { SageButton } from './SageButton';

describe('ExplainNote', () => {
  it('renders the serif header, the body, and the method line', () => {
    const { container } = render(
      <ExplainNote body="Pays $19 an hour. Remote." method="Pulled from the posting's own words." />,
    );
    expect(container.querySelector('.qb-xhead')).toHaveTextContent('In plain words');
    expect(container.querySelector('.qb-note')).toHaveTextContent('Pays $19 an hour. Remote.');
    expect(container.querySelector('.qb-xmethod')).toHaveTextContent(
      "Pulled from the posting's own words.",
    );
  });

  it('stays one block: an upgrade swaps in place, never stacks a second answer', () => {
    const { container, rerender } = render(
      <ExplainNote body="quick read" method="Pulled from the posting's own words." swap={0} />,
    );
    expect(container.querySelector('.qb-xswap')).toBeNull();
    rerender(<ExplainNote body="full read" method="Read from the whole posting." swap={1} />);
    expect(container.querySelectorAll('.qb-note')).toHaveLength(1);
    expect(container.querySelector('.qb-note')).toHaveTextContent('full read');
    expect(container.querySelector('.qb-note')).not.toHaveTextContent('quick read');
    expect(container.querySelector('.qb-xswap')).not.toBeNull();
  });
});

describe('ConsentCard', () => {
  it('renders title, body, actions, and foot', () => {
    const onStart = vi.fn();
    const onLater = vi.fn();
    render(
      <ConsentCard
        title="First time only."
        body="One download first."
        actions={
          <>
            <SageButton onClick={onStart}>Start the download</SageButton>
            <PlainButton onClick={onLater}>Not now</PlainButton>
          </>
        }
        foot="Remove it any time in Settings."
      />,
    );
    expect(screen.getByText('First time only.')).toBeInTheDocument();
    expect(screen.getByText('Remove it any time in Settings.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Start the download' }));
    expect(onStart).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(onLater).toHaveBeenCalledOnce();
  });
});

describe('the explain sheet grammar inside the existing Sheet', () => {
  it('reuses Sheet with the answer above the consent card', () => {
    render(
      <Sheet
        open
        onClose={() => {}}
        label="Explain this quest"
        title="Game show contestant, casting"
        meta="tvcasting, taping Jul 14, Atlanta"
      >
        <ExplainNote body="Pays $500 max." method="Pulled from the posting's own words." />
        <ConsentCard title="First time only." body="One download first." />
      </Sheet>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Explain this quest' });
    expect(dialog).toHaveTextContent('Game show contestant, casting');
    expect(dialog).toHaveTextContent('In plain words');
    expect(dialog).toHaveTextContent('First time only.');
    /* the consent card sits under the already-delivered answer */
    const html = dialog.innerHTML;
    expect(html.indexOf('In plain words')).toBeLessThan(html.indexOf('First time only.'));
  });
});
