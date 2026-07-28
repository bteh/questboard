import { describe, expect, it } from 'vitest';

import { roleProposalChanges } from './role-proposal';

describe('roleProposalChanges', () => {
  it('returns no card data when the role lists are identical', () => {
    expect(roleProposalChanges(['Product designer', 'UX researcher'], ['UX researcher', 'Product designer'])).toBeNull();
  });

  it('reports roles that were added', () => {
    expect(roleProposalChanges(['Product designer'], ['Product designer', 'Design lead'])).toEqual({
      added: { roles: ['Design lead'], moreLabel: null },
      dropped: { roles: [], moreLabel: null },
    });
  });

  it('reports roles that were dropped', () => {
    expect(roleProposalChanges(['Product designer', 'UX researcher'], ['Product designer'])).toEqual({
      added: { roles: [], moreLabel: null },
      dropped: { roles: ['UX researcher'], moreLabel: null },
    });
  });

  it('reports added and dropped roles together', () => {
    expect(
      roleProposalChanges(
        ['Product designer', 'UX researcher'],
        ['Product designer', 'Design lead'],
      ),
    ).toEqual({
      added: { roles: ['Design lead'], moreLabel: null },
      dropped: { roles: ['UX researcher'], moreLabel: null },
    });
  });

  it('caps each role list at five and reports the hidden count', () => {
    const baseRoles = ['Keep', ...Array.from({ length: 7 }, (_, index) => `Dropped ${index + 1}`)];
    const proposedRoles = ['Keep', ...Array.from({ length: 8 }, (_, index) => `Added ${index + 1}`)];

    expect(roleProposalChanges(baseRoles, proposedRoles)).toEqual({
      added: {
        roles: ['Added 1', 'Added 2', 'Added 3', 'Added 4', 'Added 5'],
        moreLabel: '+3 more',
      },
      dropped: {
        roles: ['Dropped 1', 'Dropped 2', 'Dropped 3', 'Dropped 4', 'Dropped 5'],
        moreLabel: '+2 more',
      },
    });
  });
});
