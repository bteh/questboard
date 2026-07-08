import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../cx';

export type PlainButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function PlainButton({ className, type = 'button', ...rest }: PlainButtonProps) {
  return <button type={type} className={cx('qb-plainbtn', className)} {...rest} />;
}
