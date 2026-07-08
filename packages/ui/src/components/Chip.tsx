import { verticals, type Vertical } from '../tokens';
import { cx } from '../cx';
import { Stamp } from './Stamp';

export interface ChipProps {
  label: string;
  /* live count of quests behind the chip */
  count?: number;
  active?: boolean;
  dim?: boolean;
  /* vertical chips carry a stamp and take the hue when active;
     plain chips are the preset grammar with a count */
  vertical?: Vertical | 'all';
  onClick?: () => void;
}

export function Chip({ label, count, active = false, dim = false, vertical, onClick }: ChipProps) {
  if (vertical !== undefined) {
    const hueClass = vertical === 'all' ? 'qb-all' : `qb-c-${verticals[vertical].bandClass}`;
    return (
      <button type="button" className={cx('qb-chip', hueClass, active && 'qb-active')} onClick={onClick}>
        {vertical !== 'all' && <Stamp vertical={vertical} size={16} inheritColor />}
        {label}
        {count !== undefined && <span className="qb-n">{count}</span>}
      </button>
    );
  }
  return (
    <button
      type="button"
      className={cx('qb-pchip', active && 'qb-active', dim && 'qb-dim')}
      onClick={onClick}
    >
      {label}
      {count !== undefined && <span className="qb-n">{count}</span>}
    </button>
  );
}
