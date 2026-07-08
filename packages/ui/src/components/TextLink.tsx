import type { ReactNode, MouseEventHandler } from 'react';
import { cx } from '../cx';

export interface TextLinkProps {
  /* with an href it renders an anchor, otherwise a button */
  href?: string;
  onClick?: MouseEventHandler;
  className?: string;
  children: ReactNode;
}

export function TextLink({ href, onClick, className, children }: TextLinkProps) {
  if (href !== undefined) {
    return (
      <a className={cx('qb-textlink', className)} href={href} onClick={onClick}>
        {children}
      </a>
    );
  }
  return (
    <button type="button" className={cx('qb-textlink', className)} onClick={onClick}>
      {children}
    </button>
  );
}
