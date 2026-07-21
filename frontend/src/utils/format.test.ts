import { describe, expect, it } from 'vitest';
import { formatSalary } from './format';

/* Salary display honesty: the formatter must not stamp "$" on money that
   was stated in another currency, and hourly pay must read as hourly
   ("$50 - $90/hr"), never compacted like an annual figure. */

describe('formatSalary', () => {
  it('keeps the legacy dollar rendering when no currency is given', () => {
    expect(formatSalary(90000, 110000)).toBe('$90K - $110K');
    expect(formatSalary(90000, null)).toBe('$90K+');
    expect(formatSalary(null, 90000)).toBe('Up to $90K');
    expect(formatSalary(null, null)).toBe('');
  });

  it('null currency keeps the dollar sign', () => {
    expect(formatSalary(90000, 110000, null)).toBe('$90K - $110K');
  });

  it('maps known ISO codes to their symbol', () => {
    expect(formatSalary(90000, 110000, 'USD')).toBe('$90K - $110K');
    expect(formatSalary(90000, 110000, 'EUR')).toBe('€90K - €110K');
    expect(formatSalary(90000, null, 'GBP')).toBe('£90K+');
    expect(formatSalary(90000, null, 'CAD')).toBe('C$90K+');
    expect(formatSalary(null, 90000, 'AUD')).toBe('Up to A$90K');
  });

  it('prefixes an unknown code instead of guessing a symbol', () => {
    expect(formatSalary(90000, null, 'CHF')).toBe('CHF 90K+');
    expect(formatSalary(90000, 110000, 'SEK')).toBe('SEK 90K - SEK 110K');
  });

  it('renders hourly pay with /hr and never compacts it to K', () => {
    expect(formatSalary(50, 90, 'USD', 'hourly')).toBe('$50 - $90/hr');
    expect(formatSalary(50, null, null, 'hourly')).toBe('$50+/hr');
    expect(formatSalary(null, 90, null, 'hourly')).toBe('Up to $90/hr');
    /* a four-digit hourly figure stays exact */
    expect(formatSalary(1000, null, null, 'hourly')).toBe('$1000+/hr');
  });

  it('annual pay keeps the K compaction', () => {
    expect(formatSalary(90000, 110000, 'USD', 'annual')).toBe('$90K - $110K');
  });
});
