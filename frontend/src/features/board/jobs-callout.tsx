import { Link } from '@tanstack/react-router';
import { useOnboardingState } from '@/hooks/use-workspace';
import { pickSetupStep } from '@/features/board/jobs-setup';

/* The Work lane retrieves target-role candidates locally. Resume-fit judgment
   belongs to the user's connected agent, never an invisible server score.
   Setup shows ONE prompt at a time (pickSetupStep): a single sentence leading
   with the verb, plus one link. Complete setup shows nothing here. */
export function JobsSetupStrip({
  profileConfigured,
  jurisdictionConfigured,
}: {
  profileConfigured?: boolean;
  jurisdictionConfigured?: boolean;
}) {
  const { data: onboarding } = useOnboardingState();
  if (!onboarding) return null;
  const step = pickSetupStep({
    resumeExists: onboarding.resume?.exists === true,
    profileConfigured,
    jurisdictionConfigured,
  });
  if (step === null) return null;
  return (
    <div className="qb-jobs-setup">
      {step === 'resume' && (
        <span>
          <b>Add your resume</b> (optional) so your assistant can compare finalists against your
          experience.{' '}
          <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta">
            Add it →
          </Link>
        </span>
      )}
      {step === 'roles' && (
        <span>
          <b>Choose your target roles</b> to pull matching jobs.{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-jobs-cta">
            Choose roles →
          </Link>
        </span>
      )}
      {step === 'country' && (
        <span>
          <b>Add a country</b> so remote jobs match where you can work.{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-jobs-cta">
            Add it →
          </Link>
        </span>
      )}
    </div>
  );
}
