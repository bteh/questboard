/* The Jobs lane setup strip shows ONE prompt at a time, in priority order:
   resume first, then target roles, then the remote country. A reader never
   faces two setup asks at once, and unknown state never prompts. */

import { describe, expect, it } from 'vitest';
import { pickSetupStep } from './jobs-setup';

describe('the setup step picker', () => {
  it('asks for the resume first, before anything else', () => {
    expect(
      pickSetupStep({ resumeExists: false, profileConfigured: false, jurisdictionConfigured: false }),
    ).toBe('resume');
    expect(pickSetupStep({ resumeExists: false })).toBe('resume');
  });

  it('asks for roles once the resume is in', () => {
    expect(
      pickSetupStep({ resumeExists: true, profileConfigured: false, jurisdictionConfigured: false }),
    ).toBe('roles');
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
