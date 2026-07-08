import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Stamp } from './Stamp';
import { colors } from '../tokens';

describe('Stamp', () => {
  it('references the vertical stamp def and takes the vertical hue', () => {
    const { container } = render(<Stamp vertical="career" />);
    const svg = container.querySelector('svg.qb-stamp');
    expect(svg).not.toBeNull();
    expect(svg!.querySelector('use')!.getAttribute('href')).toBe('#qb-stamp-career');
    expect((svg as SVGElement).style.color).toBe('rgb(63, 107, 84)');
    expect(colors.sage).toBe('#3F6B54');
  });

  it('sizes via the size prop', () => {
    const { container } = render(<Stamp vertical="study" size={16} />);
    const svg = container.querySelector('svg') as SVGElement;
    expect(svg.style.width).toBe('16px');
    expect(svg.style.height).toBe('16px');
  });

  it('leaves color to the parent when inheritColor is set', () => {
    const { container } = render(<Stamp vertical="party" inheritColor />);
    const svg = container.querySelector('svg') as SVGElement;
    expect(svg.style.color).toBe('');
  });
});
