const ROLE_DISPLAY_LIMIT = 5;

export interface CappedRoleList {
  roles: string[];
  moreLabel: string | null;
}

export interface RoleProposalChanges {
  added: CappedRoleList;
  dropped: CappedRoleList;
}

function capRoles(roles: string[]): CappedRoleList {
  const hiddenCount = Math.max(0, roles.length - ROLE_DISPLAY_LIMIT);
  return {
    roles: roles.slice(0, ROLE_DISPLAY_LIMIT),
    moreLabel: hiddenCount > 0 ? `+${hiddenCount} more` : null,
  };
}

export function roleProposalChanges(
  baseRoles: string[],
  proposedRoles: string[],
): RoleProposalChanges | null {
  const base = new Set(baseRoles);
  const proposed = new Set(proposedRoles);
  const added = proposedRoles.filter((role) => !base.has(role));
  const dropped = baseRoles.filter((role) => !proposed.has(role));

  if (added.length === 0 && dropped.length === 0) return null;

  return {
    added: capRoles(added),
    dropped: capRoles(dropped),
  };
}

/* Past this, the card clamps the rationale to two lines with a toggle; a
   sentence or two renders whole so the toggle never wastes a tap. Roughly
   two lines of the card's 12.5px text at its 720px max width. */
const RATIONALE_CLAMP_CHARS = 180;

export function rationaleIsLong(text: string): boolean {
  return text.trim().length > RATIONALE_CLAMP_CHARS;
}
