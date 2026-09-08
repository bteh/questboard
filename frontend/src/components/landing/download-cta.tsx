import { useState } from 'react';
import { SageButton } from '@questboard/ui';
import { openExternal } from '@/lib/open-external';

/* The download call-to-action, in three honest states driven by build-time
 * env. It never renders a button that points at nothing:
 *
 *   1. VITE_DOWNLOAD_URL set  -> a real "Download for Mac" button.
 *   2. VITE_NOTIFY_ENDPOINT set (and no download yet) -> an inline email
 *      form that POSTs {email} to that endpoint.
 *   3. neither set (today)    -> a mailto button; the visitor emails us to
 *      be notified. Zero infrastructure, no PII stored on our side.
 *
 * Flipping to a real download at release time is a one-line env change. */

const DOWNLOAD_URL = import.meta.env.VITE_DOWNLOAD_URL as string | undefined;
const NOTIFY_ENDPOINT = import.meta.env.VITE_NOTIFY_ENDPOINT as string | undefined;
// No default address: a made-up one would route strangers' mail to whoever
// owns that domain. Without one, the fallback is the GitHub releases page.
const NOTIFY_EMAIL = import.meta.env.VITE_NOTIFY_EMAIL as string | undefined;
const RELEASES_URL = 'https://github.com/bteh/questboard/releases';

const NOT_OUT_YET = 'The signed Mac build isn’t out yet. One email when it lands, nothing else.';

export function DownloadOrNotify({ big = false }: { big?: boolean }) {
  if (DOWNLOAD_URL) {
    return (
      <div className="qb-cta-stack">
        <SageButton big={big} onClick={() => void openExternal(DOWNLOAD_URL)}>
          Download for Mac
        </SageButton>
        <span className="qb-lnote">Free. Apple Silicon, macOS 12 or newer. No account.</span>
        <span className="qb-lnote">Signed and notarized, so it opens like any other app.</span>
      </div>
    );
  }
  return <NotifyMe big={big} />;
}

function NotifyMe({ big }: { big: boolean }) {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');

  if (!NOTIFY_ENDPOINT && !NOTIFY_EMAIL) {
    return (
      <div className="qb-cta-stack">
        <SageButton big={big} onClick={() => void openExternal(RELEASES_URL)}>
          Get the Mac build on GitHub
        </SageButton>
        <span className="qb-lnote">Every release is signed and notarized. Apple Silicon, macOS 12 or newer.</span>
      </div>
    );
  }

  if (!NOTIFY_ENDPOINT) {
    const href =
      `mailto:${NOTIFY_EMAIL}` +
      `?subject=${encodeURIComponent('Notify me: Questboard for Mac')}` +
      `&body=${encodeURIComponent('Email me when the Mac build is ready.')}`;
    return (
      <div className="qb-cta-stack">
        <SageButton
          big={big}
          onClick={() => {
            window.location.href = href;
          }}
        >
          Email me when the Mac build is ready
        </SageButton>
        <span className="qb-lnote">{NOT_OUT_YET}</span>
        <span className="qb-lnote">
          No mail app? Write to <span className="qb-lnote-email">{NOTIFY_EMAIL}</span>
        </span>
      </div>
    );
  }

  if (state === 'done') {
    return (
      <div className="qb-cta-stack">
        <p className="qb-cta-done">You’re on the list. One email when the Mac build ships.</p>
        <span className="qb-lnote">No list, no spam, no account.</span>
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState('sending');
    try {
      const res = await fetch(NOTIFY_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ email }),
      });
      setState(res.ok ? 'done' : 'error');
    } catch {
      setState('error');
    }
  };

  return (
    <form className="qb-notify-form" onSubmit={submit}>
      <div className="qb-notify-row">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          aria-label="Email me when the Mac build is ready"
          className="qb-notify-input"
          disabled={state === 'sending'}
        />
        <SageButton big={big} type="submit" disabled={state === 'sending' || !email}>
          {state === 'sending' ? 'Sending…' : 'Notify me'}
        </SageButton>
      </div>
      {state === 'error' ? (
        <span className="qb-lnote qb-lnote-warn">
          That didn’t send. Email {NOTIFY_EMAIL} and I’ll add you.
        </span>
      ) : (
        <span className="qb-lnote">{NOT_OUT_YET}</span>
      )}
    </form>
  );
}
