import { useEffect, useState } from 'react';
import { cx } from '../cx';

export interface SplitFlapProps {
  /* the digits to land on, one flap cell per character */
  value: string;
  caption?: string;
  /* screen-reader sentence for the whole group */
  srLabel?: string;
}

interface Cell {
  char: string;
  tick: number;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* The load-once flap row: each cell flips through random digits a few more
   times than the one before it, then settles on its target. */
export function SplitFlap({ value, caption, srLabel }: SplitFlapProps) {
  const [cells, setCells] = useState<Cell[]>(() => value.split('').map(() => ({ char: '', tick: 0 })));

  useEffect(() => {
    const chars = value.split('');
    if (prefersReducedMotion()) {
      setCells(chars.map((char) => ({ char, tick: 0 })));
      return;
    }
    const timers: number[] = [];
    const setCell = (i: number, patch: Partial<Cell>) => {
      setCells((prev) => prev.map((c, j) => (j === i ? { ...c, ...patch } : c)));
    };
    chars.forEach((target, i) => {
      const ticks = 5 + i * 2;
      let n = 0;
      setCell(i, { char: String(Math.floor(Math.random() * 10)) });
      const iv = window.setInterval(() => {
        n++;
        const done = n >= ticks;
        setCell(i, { tick: n });
        /* the digit swaps mid-flip, behind the fold */
        timers.push(
          window.setTimeout(() => {
            setCell(i, { char: done ? target : String(Math.floor(Math.random() * 10)) });
          }, 52),
        );
        if (done) window.clearInterval(iv);
      }, 95);
      timers.push(iv);
    });
    return () => {
      timers.forEach((t) => {
        window.clearInterval(t);
        window.clearTimeout(t);
      });
    };
    // load-once by design
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <span className="qb-fgroup">
      {srLabel && <span className="qb-sr">{srLabel}</span>}
      <span className="qb-fcells" aria-hidden="true">
        {cells.map((c, i) => (
          <span key={`${i}-${c.tick}`} className={cx('qb-flap', c.tick > 0 && 'qb-tick')}>
            {c.char}
          </span>
        ))}
      </span>
      {caption && (
        <span className="qb-fcap" aria-hidden="true">
          {caption}
        </span>
      )}
    </span>
  );
}
