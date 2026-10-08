// @vitest-environment jsdom
/* Real case (Oct 8 2026): a seeker who lost an IT job wanted "analyst, IT,
   etc" and had to type every title by hand. One click adds a whole set. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { StarterRoleButtons } from './starter-role-buttons';
import { addStarterRoles, ROLES_CAP, STARTER_ROLE_SETS } from './starter-roles';

afterEach(cleanup);

const itSupport = STARTER_ROLE_SETS.find((set) => set.id === 'it-support')!;
const analyst = STARTER_ROLE_SETS.find((set) => set.id === 'analyst')!;

describe('starter role sets', () => {
  it('holds the IT support and Analyst titles', () => {
    expect(itSupport.roles).toContain('Help Desk Technician');
    expect(itSupport.roles).toContain('Junior Systems Administrator');
    expect(analyst.roles).toContain('Business Systems Analyst');
    expect(itSupport.roles).toHaveLength(7);
    expect(analyst.roles).toHaveLength(7);
  });

  it('adds only the missing titles, keeping saved ones first', () => {
    expect(addStarterRoles(['help desk technician', 'Nurse'], itSupport)).toEqual([
      'help desk technician',
      'Nurse',
      'IT Support Specialist',
      'Desktop Support Technician',
      'IT Technician',
      'Service Desk Analyst',
      'Junior Systems Administrator',
      'Network Technician',
    ]);
  });

  it('stops at the saved-role cap', () => {
    const current = Array.from({ length: ROLES_CAP - 2 }, (_, i) => `Role ${i}`);
    expect(addStarterRoles(current, analyst)).toHaveLength(ROLES_CAP);
  });
});

describe('StarterRoleButtons', () => {
  it('adds a set in one click', () => {
    const onChange = vi.fn();
    render(<StarterRoleButtons roles={['Data Analyst']} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /\+ IT support 7/ }));
    expect(onChange).toHaveBeenCalledWith(['Data Analyst', ...itSupport.roles]);
  });

  it('shows how many titles a set still adds and disables a set already added', () => {
    render(<StarterRoleButtons roles={[...analyst.roles]} onChange={() => {}} />);
    const added = screen.getByRole('button', { name: /Analyst added/ });
    expect(added.hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: /\+ IT support 7/ }).hasAttribute('disabled')).toBe(false);
  });
});
