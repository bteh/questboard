import { verticals, type Vertical } from '../tokens';
import { cx } from '../cx';

export interface PostmarkStampProps {
  vertical: Vertical;
  /* run the press animation on mount; remount (change key) to replay */
  press?: boolean;
  className?: string;
}

export function PostmarkStamp({ vertical, press = false, className }: PostmarkStampProps) {
  return (
    <svg
      className={cx('qb-postmark', press && 'qb-press', className)}
      viewBox="0 0 28 28"
      style={{ color: verticals[vertical].hue }}
      aria-hidden="true"
    >
      <use href={`#qb-stamp-${vertical}`} stroke="currentColor" />
    </svg>
  );
}
