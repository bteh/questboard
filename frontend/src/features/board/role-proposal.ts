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
