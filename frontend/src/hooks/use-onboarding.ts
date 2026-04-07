import { useWorkspace } from '@/contexts/workspace-context';
import { useOnboardingState } from '@/hooks/use-workspace';

export function useOnboarding() {
  const { isLoading: workspaceLoading } = useWorkspace();
  const { data, isLoading } = useOnboardingState(!workspaceLoading);

  return {
    shouldShow: !workspaceLoading && !isLoading && !!data && !data.has_started_search,
    dismiss: () => {},
    isLoading: workspaceLoading || isLoading,
  };
}
