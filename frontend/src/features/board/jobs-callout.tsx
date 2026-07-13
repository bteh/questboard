import { Link } from '@tanstack/react-router';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState } from '@/hooks/use-workspace';

/* The Jobs lane's one job a quest board can't do: rank real jobs to your
   resume with AI. This callout is the missing bridge from "I uploaded my
   resume" to a ranked search, and it says plainly why the ranking isn't
   showing (no resume yet, or AI disconnected) instead of leaving the reader
   staring at unranked postings. Only rendered in the Find work lane. */
export function JobsCallout() {
  const { data: llm } = useLLMStatus();
  const { data: onboarding } = useOnboardingState();
  const hasResume = onboarding?.resume?.exists === true;
  const aiOk = llm?.available === true;

  let body: React.ReactNode;
  if (!aiOk) {
    // the exact failure the founder hit: the proxy session expired, so
    // nothing gets ranked and nothing said why
    body = (
      <>
        <span>
          These jobs get ranked to your resume by AI, but AI looks disconnected, so they
          are showing unranked.
        </span>
        <Link to="/settings" search={{ tab: 'ai' }} className="qb-jobs-cta">
          Reconnect AI →
        </Link>
      </>
    );
  } else if (!hasResume) {
    body = (
      <>
        <span>Add your resume and every job shows how well you actually fit it.</span>
        <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta">
          Add your resume →
        </Link>
      </>
    );
  } else {
    body = (
      <>
        <span>Pull fresh jobs and rank them to your resume.</span>
        <Link to="/restock" className="qb-jobs-cta">
          Find &amp; rank jobs →
        </Link>
      </>
    );
  }

  return <div className="qb-jobs-callout">{body}</div>;
}
