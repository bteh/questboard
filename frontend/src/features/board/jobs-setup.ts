/* The Jobs lane setup picker, pinned by jobs-setup.test.ts. One prompt at
   a time, in priority order: target roles, then resume, then the remote
   country. Roles come first because they drive retrieval; the resume is
   optional and only powers fit ranking. Undefined means the state is still
   loading, and loading never prompts; only a known-false answer asks. */

export type SetupStep = 'resume' | 'roles' | 'country';

export function pickSetupStep(state: {
  resumeExists: boolean;
  profileConfigured?: boolean;
  jurisdictionConfigured?: boolean;
}): SetupStep | null {
  if (state.profileConfigured === false) return 'roles';
  if (!state.resumeExists) return 'resume';
  if (state.jurisdictionConfigured === false) return 'country';
  return null;
}
