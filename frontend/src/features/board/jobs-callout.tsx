import { Link } from '@tanstack/react-router';
import { useOnboardingState } from '@/hooks/use-workspace';

/* The Work lane retrieves target-role candidates locally. Resume-fit judgment
   belongs to the user's connected agent, never an invisible server score. */
export function JobsSetupStrip({
  profileConfigured,
  jurisdictionConfigured,
}: {
  profileConfigured?: boolean;
  jurisdictionConfigured?: boolean;
}) {
  const { data: onboarding } = useOnboardingState();
  if (!onboarding) return null;
  const needsResume = onboarding.resume?.exists !== true;
  return (
    <div className="qb-jobs-setup">
      {needsResume && (
        <span>
          <b>Add your resume</b> so your agent can compare finalists with your experience.{' '}
          <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta">
            Add it →
          </Link>
        </span>
      )}
      {profileConfigured === false && (
        <span>
          <b>No target roles saved.</b>{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-jobs-cta">
            Choose roles →
          </Link>
        </span>
      )}
      {profileConfigured !== false && (
        <span>
          <b>Profile radar on.</b> These titles match your target roles; use Codex or Claude for resume evidence.
        </span>
      )}
      {jurisdictionConfigured === false && (
        <span>
          <b>Remote has no country attached.</b>{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-jobs-cta">
            Add a city or country →
          </Link>
        </span>
      )}
    </div>
  );
}
