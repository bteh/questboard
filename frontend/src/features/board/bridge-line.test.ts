/* The bank-bonus bridge line is a tangent everywhere except the two lanes
   it belongs to: the work lane (a new paycheck) and the house lane (the
   bank bonuses themselves). Everywhere else it stays off. */

import { describe, expect, it } from 'vitest';
import { showBankBonusBridge } from './bridge-line';

describe('the bank-bonus bridge line', () => {
  it('shows on the work lane', () => {
    expect(showBankBonusBridge('work')).toBe(true);
  });

  it('shows on the house lane', () => {
    expect(showBankBonusBridge('house')).toBe(true);
  });

  it('stays off every other lane', () => {
    expect(showBankBonusBridge('all')).toBe(false);
    expect(showBankBonusBridge('think')).toBe(false);
    expect(showBankBonusBridge('skill')).toBe(false);
    expect(showBankBonusBridge('flip')).toBe(false);
    expect(showBankBonusBridge('odd')).toBe(false);
  });
});
