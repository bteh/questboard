/* Where the bank-bonus bridge line may show, pinned by bridge-line.test.ts.
   Two lanes only: work (a new paycheck is the moment) and house (the bank
   bonuses live there). On every other lane it is a tangent and stays off. */

import type { KindKey } from '@/features/board/kind-params';

export function showBankBonusBridge(kind: KindKey): boolean {
  return kind === 'work' || kind === 'house';
}
