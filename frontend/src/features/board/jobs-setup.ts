/* The Jobs lane setup picker, pinned by jobs-setup.test.ts. One prompt at
   a time, in priority order: resume, then target roles, then the remote
   country. Undefined means the state is still loading, and loading never
   prompts; only a known-false answer asks for anything. */

export type SetupStep = 'resume' | 'roles' | 'country';

export function pickSetupStep(state: {
  resumeExists: boolean;
  profileConfigured?: boolean;
  jurisdictionConfigured?: boolean;
}): SetupStep | null {
  if (!state.resumeExists) return 'resume';
  if (state.profileConfigured === false) return 'roles';
  if (state.jurisdictionConfigured === false) return 'country';
  return null;
}
