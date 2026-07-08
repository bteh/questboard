import { useEffect, type ReactNode } from 'react';
import { cx } from '../cx';

export interface ScrimProps {
  open: boolean;
  onClose: () => void;
  children?: ReactNode;
}

export function Scrim({ open, onClose, children }: ScrimProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <div
      className={cx('qb-scrim', open && 'qb-on')}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {children}
    </div>
  );
}

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  label: string;
  title?: string;
  meta?: string;
  children?: ReactNode;
}

export function Sheet({ open, onClose, label, title, meta, children }: SheetProps) {
  return (
    <Scrim open={open} onClose={onClose}>
      <div className="qb-sheet" role="dialog" aria-label={label}>
        {title && <h3>{title}</h3>}
        {meta && <div className="qb-smeta">{meta}</div>}
        {children}
      </div>
    </Scrim>
  );
}
