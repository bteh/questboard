import { Fragment, useEffect, useRef, useState } from 'react';
import { cx } from '@questboard/ui';

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia !== 'function' ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/* The credo line, ink coming into register as it scrolls into view: the
   page's one scroll-sharpened motion, per the mock. Reduced motion renders
   the final, fully sharp state and never moves. */
export function CredoLine({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const words = text.split(' ');
  /* reduced motion starts, and stays, fully sharp */
  const [lit, setLit] = useState(() => (prefersReducedMotion() ? text.split(' ').length : 0));

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let pending = false;
    const update = () => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight;
      const p = Math.max(0, Math.min(1, (vh * 0.92 - rect.top) / (vh * 0.38)));
      /* words only sharpen, never blur back: read once, stay read */
      setLit((prev) => Math.max(prev, Math.round(p * words.length)));
    };
    const onScroll = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        update();
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
    /* the sentence is fixed copy; re-splitting on every render would reset it */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* the space lives BETWEEN the inline-block spans; inside one it collapses */
  return (
    <p ref={ref} className="qb-credo" aria-label={text}>
      {words.map((word, i) => (
        <Fragment key={i}>
          <span aria-hidden="true" className={cx('qb-w', i < lit && 'qb-on')}>
            {word}
          </span>
          {i < words.length - 1 ? ' ' : null}
        </Fragment>
      ))}
    </p>
  );
}
