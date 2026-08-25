import { useEffect, useState } from 'react';
import { Link, useNavigate } from '@tanstack/react-router';
import { SageButton } from '@questboard/ui';
import { PlacePicker } from '@/features/board/place-picker';
import { World } from '@/components/landing/world';
import { useOnboardingState, useSaveWorkspacePreferences } from '@/hooks/use-workspace';
import { markEntered, markOnboarded } from '@/lib/entry';
import { buildDefaultWorkspacePreferences } from '@/lib/profile-preferences';
import { markFirstRunPending } from './first-run';
import { firstRunPreferences, persistFirstRun } from './start-page-logic';
import './start.css';

/* The whole first run: one question. Where are you? A place tunes the board
   to quests near the reader; remote stays on by default so the board is
   never empty. No resume, no account, no gate. Skipping is one tap and
   never asked again. */
export function StartPage() {
  const navigate = useNavigate();
  const { data: onboarding } = useOnboardingState();
  const savePreferences = useSaveWorkspacePreferences();
  const [place, setPlace] = useState('');
  const [includeRemote, setIncludeRemote] = useState(true);

  useEffect(() => {
    document.title = 'Questboard, set your place';
  }, []);

  /* The door never waits on the network. The flags land first and the
     board opens on the URL alone, while the preference write retries in
     the background. A lost write costs the saved place, never the app. */
  const go = (withPlace: boolean) => {
    const chosen = withPlace ? place.trim() : '';
    const current = onboarding?.preferences ?? buildDefaultWorkspacePreferences();
    markOnboarded();
    markFirstRunPending();
    markEntered();
    void persistFirstRun(
      (prefs) => savePreferences.mutateAsync(prefs),
      firstRunPreferences(current, chosen, includeRemote),
    );
    void navigate({
      to: '/board',
      search: {
        place: chosen || undefined,
        near: chosen && !includeRemote ? '1' : undefined,
      },
    });
  };

  return (
    <div className="qb-start">
      <World />
      <div className="qb-start-card">
        <div className="qb-start-brand">
          <span className="qb-start-tile">
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <g transform="rotate(-4 8 5.8)">
                <rect x="6.35" y="1.9" width="3.3" height="7.8" rx="1.65" fill="#FFFDF8" />
              </g>
              <circle cx="8" cy="12.5" r="1.95" fill="#FFFDF8" />
              <circle cx="8" cy="12.5" r="0.85" fill="#A6522E" />
            </svg>
          </span>
          <b>Questboard</b>
        </div>

        <h1 className="qb-start-title">Where are you?</h1>
        <p className="qb-start-sub">
          So the board opens with quests near you. Remote ones show wherever you are.
        </p>

        <form
          className="qb-start-form"
          onSubmit={(e) => {
            e.preventDefault();
            go(true);
          }}
        >
          <PlacePicker
            value={place}
            onChange={setPlace}
            placeholder="Your city, region, or country"
            ariaLabel="Your city, region, or country"
            className="qb-start-field"
            suggestionScope="global"
          />

          <label className="qb-start-remote">
            <input
              type="checkbox"
              checked={includeRemote}
              onChange={(e) => setIncludeRemote(e.target.checked)}
            />
            <span>Include remote quests too</span>
          </label>

          <SageButton big type="submit">
            See my board →
          </SageButton>
        </form>

        <button type="button" className="qb-start-skip" onClick={() => go(false)}>
          Skip, show me everything
        </button>

        {/* The wizard's only other door is a small link in Settings, which
            a new user never finds. This one stays a text link: /start keeps
            its one question. Taking it counts as finishing here, so /start
            never asks again. */}
        <p className="qb-start-guided">
          Or take the{' '}
          <Link
            to="/settings"
            search={{ tab: undefined }}
            onClick={() => {
              markOnboarded();
              markEntered();
            }}
          >
            guided setup
          </Link>
          , which adds your resume and target roles.
        </p>
      </div>
    </div>
  );
}
