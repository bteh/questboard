/* Which pay floor is actually in force, said out loud.

   The board carried two pay numbers that looked like one. The run receipt
   states the saved search floor ("$190K+ base"), and the filter row has its
   own "min listed pay" box. That box's placeholder used to read "150k", so an
   empty filter looked like a filter set to a number that contradicted the
   receipt. This clause names the one doing the work: your typed minimum when
   you set one, the saved floor otherwise. The saved floor applies on every
   view, source chips included; chips narrow the saved lane, they never
   browse past it. */

export function payScopeNote({
  savedFloor,
  typedFloor,
}: {
  savedFloor: number | null | undefined;
  typedFloor: number | null;
}): string | null {
  // The box shows its own number when you type one; repeating it would just
  // be a third figure on screen.
  if (typedFloor) return null;
  if (!savedFloor || savedFloor <= 0) return null;
  const amount = `$${Math.round(savedFloor / 1000)}K`;
  return `${amount}+ base from your search`;
}
