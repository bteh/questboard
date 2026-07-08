import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../cx';

export interface SageButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  big?: boolean;
}

export function SageButton({ big = false, className, type = 'button', ...rest }: SageButtonProps) {
  return <button type={type} className={cx('qb-btn-sage', big && 'qb-lbig', className)} {...rest} />;
}
