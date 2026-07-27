/* Which pay floor is actually in force, said out loud.

   The board carried two pay numbers that looked like one. The run receipt
   states the saved search floor ("$190K+ base"), and the filter row has its
   own "min listed pay" box. That box's placeholder used to read "150k", so an
   empty filter looked like a filter set to a number that contradicted the
   receipt. Worse, the saved floor really does apply on "My roles" and really
   does not apply on a source chip: browsing Remote surfaced 101 rows stating
   pay under the floor while the receipt still promised $190K+.

   Chips are meant to browse past your saved search, so they keep showing
   everything. This clause is how the board admits which of the two is
   currently doing the work. */

export function payScopeNote({
  browsingCategory,
  savedFloor,
  typedFloor,
}: {
  browsingCategory: boolean;
  savedFloor: number | null | undefined;
  typedFloor: number | null;
}): string | null {
  // The box shows its own number when you type one; repeating it would just
  // be a third figure on screen.
  if (typedFloor) return null;
  if (!savedFloor || savedFloor <= 0) return null;
  const amount = `$${Math.round(savedFloor / 1000)}K`;
  return browsingCategory
    ? `your ${amount} floor is off while browsing`
    : `${amount}+ base from your search`;
}
