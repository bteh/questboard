/* The Jobs lane setup strip shows ONE prompt at a time, in priority order:
   target roles first, then resume, then the remote country. Roles drive
   retrieval; the resume is optional (fit ranking only), so a new user is
   never told to upload a resume before the board can work. A reader never
   faces two setup asks at once, and unknown state never prompts. */

import { describe, expect, it } from 'vitest';
import { pickSetupStep } from './jobs-setup';

describe('the setup step picker', () => {
  it('asks for roles first: they drive retrieval, the resume does not', () => {
    expect(
      pickSetupStep({ resumeExists: false, profileConfigured: false, jurisdictionConfigured: false }),
    ).toBe('roles');
  });

  it('asks for the resume once roles are set', () => {
    expect(
      pickSetupStep({ resumeExists: false, profileConfigured: true, jurisdictionConfigured: false }),
    ).toBe('resume');
    expect(pickSetupStep({ resumeExists: false })).toBe('resume');
  });

  it('asks for the country only when resume and roles are set', () => {
    expect(
      pickSetupStep({ resumeExists: true, profileConfigured: true, jurisdictionConfigured: false }),
    ).toBe('country');
  });

  it('shows nothing when setup is complete', () => {
    expect(
      pickSetupStep({ resumeExists: true, profileConfigured: true, jurisdictionConfigured: true }),
    ).toBeNull();
  });

  it('never prompts on unknown state: undefined means still loading, not missing', () => {
    expect(pickSetupStep({ resumeExists: true })).toBeNull();
    expect(pickSetupStep({ resumeExists: true, profileConfigured: undefined })).toBeNull();
    expect(
      pickSetupStep({ resumeExists: true, profileConfigured: true, jurisdictionConfigured: undefined }),
    ).toBeNull();
  });
});
