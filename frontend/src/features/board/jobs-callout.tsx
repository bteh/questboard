import { Link } from '@tanstack/react-router';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState } from '@/hooks/use-workspace';
import { useWorkspace } from '@/contexts/workspace-context';

/* The Jobs lane's one job a quest board can't do: rank real jobs to your
   resume with AI. This is the missing bridge from "I uploaded my resume" to a
   ranked search. It shows the WHOLE process as a checklist so you always know
   what's set up, what isn't, and the one thing to do next, instead of staring
   at postings unsure whether anything is working. Only rendered in the Find
   work lane. */
export function JobsCallout() {
  const { data: llm } = useLLMStatus();
  const { data: onboarding } = useOnboardingState();
  const { hostedMode } = useWorkspace();
  const hasResume = onboarding?.resume?.exists === true;
  const resumeName = onboarding?.resume?.filename;
  const aiOk = llm?.available === true;
  // Hosted: the AI runs on the server key, so it's always on and there's
  // nothing for a user to do. Only self-host operators ever set a key, so the
  // AI step only makes sense off the hosted app.
  const searchMark = hasResume ? '→' : hostedMode ? '2' : '3';

  return (
    <div className="qb-jobs-guide">
      <p className="qb-jobs-guide-head">
        Find work ranks real jobs to how well you fit them. Your setup:
      </p>
      <ol className="qb-jobs-steps">
        {/* 1. Resume */}
        <li className={hasResume ? 'is-done' : 'is-now'}>
          <span className="qb-step-mark" aria-hidden="true">{hasResume ? '✓' : '1'}</span>
          <span className="qb-step-body">
            {hasResume ? (
              <>
                <b>Resume added.</b>{' '}
                {resumeName && <span className="qb-step-sub">{resumeName}</span>}{' '}
                <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta-quiet">
                  Replace
                </Link>
              </>
            ) : (
              <>
                <b>Add your resume</b>, so each job can be scored to your actual experience.{' '}
                <Link to="/settings" search={{ tab: 'resume' }} className="qb-jobs-cta">
                  Add it →
                </Link>
              </>
            )}
          </span>
        </li>

        {/* 2. AI status — only off the hosted app. Hosted runs on the server
            key, so it's always on and not a user step. */}
        {!hostedMode && (
          <li className={aiOk ? 'is-done' : 'is-warn'}>
            <span className="qb-step-mark" aria-hidden="true">{aiOk ? '✓' : '!'}</span>
            <span className="qb-step-body">
              {aiOk ? (
                <>
                  <b>AI ready.</b> <span className="qb-step-sub">It scores each job against your resume.</span>
                </>
              ) : (
                <>
                  <b>AI is disconnected</b>, so jobs show unranked.{' '}
                  <Link to="/settings" search={{ tab: 'ai' }} className="qb-jobs-cta">
                    Reconnect →
                  </Link>
                </>
              )}
            </span>
          </li>
        )}

        {/* Search */}
        <li className={hasResume ? 'is-now' : 'is-todo'}>
          <span className="qb-step-mark" aria-hidden="true">{searchMark}</span>
          <span className="qb-step-body">
            <b>Find &amp; rank jobs.</b> Pull fresh roles and rank them best-fit first.{' '}
            <Link to="/restock" className="qb-jobs-cta">
              Run a search →
            </Link>
          </span>
        </li>
      </ol>
    </div>
  );
}
