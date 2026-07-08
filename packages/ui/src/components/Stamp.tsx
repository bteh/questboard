import type { CSSProperties } from 'react';
import { verticals, type Vertical } from '../tokens';
import { cx } from '../cx';

export interface StampProps {
  vertical: Vertical;
  /* pixel size; the CSS default is 34 */
  size?: number;
  /* take color from the parent (bands, chips) instead of the vertical hue */
  inheritColor?: boolean;
  className?: string;
}

export function Stamp({ vertical, size, inheritColor = false, className }: StampProps) {
  const style: CSSProperties = {};
  if (!inheritColor) style.color = verticals[vertical].hue;
  if (size !== undefined) {
    style.width = size;
    style.height = size;
  }
  return (
    <svg className={cx('qb-stamp', className)} viewBox="0 0 28 28" style={style} aria-hidden="true">
      <use href={`#qb-stamp-${vertical}`} stroke="currentColor" />
    </svg>
  );
}
