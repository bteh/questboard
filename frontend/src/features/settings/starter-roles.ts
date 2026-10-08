/* Real case (Oct 8 2026): a seeker who lost an IT job wanted "analyst, IT,
   etc" and had to guess every title by hand. Each set adds its titles in
   one click. The cap matches ROLES_CAP in backend workspace_service. */

export interface StarterRoleSet {
  id: string;
  label: string;
  roles: readonly string[];
}

export const STARTER_ROLE_SETS: readonly StarterRoleSet[] = [
  {
    id: 'it-support',
    label: 'IT support',
    roles: [
      'IT Support Specialist',
      'Help Desk Technician',
      'Desktop Support Technician',
      'IT Technician',
      'Service Desk Analyst',
      'Junior Systems Administrator',
      'Network Technician',
    ],
  },
  {
    id: 'analyst',
    label: 'Analyst',
    roles: [
      'Data Analyst',
      'Business Analyst',
      'Reporting Analyst',
      'Operations Analyst',
      'Junior Data Analyst',
      'IT Business Analyst',
      'Business Systems Analyst',
    ],
  },
];

export const ROLES_CAP = 18;

export function missingRoles(current: readonly string[], set: StarterRoleSet): string[] {
  const have = new Set(current.map((role) => role.trim().toLowerCase()));
  return set.roles.filter((role) => !have.has(role.toLowerCase()));
}

export function addStarterRoles(current: readonly string[], set: StarterRoleSet): string[] {
  const room = Math.max(0, ROLES_CAP - current.length);
  return [...current, ...missingRoles(current, set).slice(0, room)];
}
