import { Link } from '@tanstack/react-router';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState } from '@/hooks/use-workspace';
import { useWorkspace } from '@/contexts/workspace-context';

/* The Jobs lane's setup, folded to a compact strip that only renders while
   something is missing: the resume (jobs rank against it) and, off the
   hosted app, the AI connection. Hosted AI runs on the server key, so it is
   never a user step. Complete setup shows nothing at all; running a search
   lives on the toolbar now. */
export function JobsSetupStrip() {
  const { data: llm } = useLLMStatus();
  const { data: onboarding } = useOnboardingState();
  const { hostedMode } = useWorkspace();
  /* say nothing until the state has actually loaded */
  if (!onboarding || (!hostedMode && !llm)) return null;
  const needsResume = onboarding.resume?.exists !== true;
  const needsAi = !hostedMode && llm?.available !== true;
  if (!needsResume && !needsAi) return null;
  return (
    <div className="qb-jobs-setup">
      {needsResume && (
        <span>
          <b>Add your resume</b> so each job can be scored to your actual experience.{' '}
          <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta">
            Add it →
          </Link>
        </span>
      )}
      {needsAi && (
        <span>
          <b>AI is disconnected</b>, so jobs show unranked.{' '}
          <Link to="/settings" search={{ tab: 'ai' }} className="qb-jobs-cta">
            Reconnect →
          </Link>
        </span>
      )}
    </div>
  );
}
