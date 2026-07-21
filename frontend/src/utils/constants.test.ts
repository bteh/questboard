import { describe, expect, it } from 'vitest';
import { STATUS_COLORS, STATUS_LABELS, STATUS_OPTIONS } from './constants';

/* The backend StatusUpdate enum (backend/app/schemas/application.py) has 14
   statuses. The frontend must offer all of them: 'booked' and 'expired' are
   written by the booking flow and the expiry pipeline, and a status the UI
   cannot select or filter is a status the user cannot see. */

const BACKEND_STATUSES = [
  'found', 'reviewed', 'clipped', 'applying', 'applied', 'interviewing',
  'offer', 'rejected', 'withdrawn', 'shelved',
  'booked', 'attended', 'paid_out', 'expired',
];

describe('status constants', () => {
  it('offers every backend status', () => {
    expect([...STATUS_OPTIONS].sort()).toEqual([...BACKEND_STATUSES].sort());
  });

  it('labels every backend status', () => {
    for (const status of BACKEND_STATUSES) {
      expect(STATUS_LABELS[status], `label for ${status}`).toBeTruthy();
    }
  });

  it('colors every backend status', () => {
    for (const status of BACKEND_STATUSES) {
      expect(STATUS_COLORS[status], `colors for ${status}`).toBeTruthy();
    }
  });
});
