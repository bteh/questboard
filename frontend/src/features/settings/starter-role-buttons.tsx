import { addStarterRoles, missingRoles, ROLES_CAP, STARTER_ROLE_SETS } from './starter-roles';
import { chipClass, chipCountClass, chipInactiveClass } from '@/features/board/chip-classes';

interface StarterRoleButtonsProps {
  roles: string[];
  onChange: (roles: string[]) => void;
}

export function StarterRoleButtons({ roles, onChange }: StarterRoleButtonsProps) {
  const full = roles.length >= ROLES_CAP;
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Starter role sets">
      <span className="text-xs text-text-muted">Add a starter set:</span>
      {STARTER_ROLE_SETS.map((set) => {
        const missing = missingRoles(roles, set).length;
        return (
          <button
            key={set.id}
            type="button"
            disabled={missing === 0 || full}
            onClick={() => onChange(addStarterRoles(roles, set))}
            className={`${chipClass} ${chipInactiveClass} disabled:opacity-50`}
          >
            {missing === 0 ? `${set.label} added` : `+ ${set.label}`}{' '}
            {missing > 0 ? <span className={chipCountClass}>{missing}</span> : null}
          </button>
        );
      })}
      {full ? <span className="text-xs text-text-muted">Role list is full ({ROLES_CAP}).</span> : null}
    </div>
  );
}
