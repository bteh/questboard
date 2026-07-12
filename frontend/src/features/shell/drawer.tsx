import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import {
  Activity01Icon,
  ArrowDown01Icon,
  Cancel01Icon,
  Home01Icon,
  Logout03Icon,
  Notebook01Icon,
  Notification03Icon,
  PinIcon,
  Settings02Icon,
  UserIcon,
} from '@hugeicons/core-free-icons';
import { useWorkspace } from '@/contexts/workspace-context';
import { useBoardSummary } from '@/hooks/use-board-summary';
import { BrandMark } from '@/components/shared/brand-mark';

/* Utility icons come from Hugeicons at the house stroke weight; the brand
   mark, kind stamps, and pushpins stay hand-drawn. */
const STROKE = 1.7;

function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/* Hosted mode shows the signed-in card with its account menu. Local mode
   states the local-first promise instead: there is no account to show. */
function ProfileCard({ onNavigate }: { onNavigate: () => void }) {
  const { hostedMode, user, currentPersona, signOut } = useWorkspace();
  const [expanded, setExpanded] = useState(false);

  if (!hostedMode) {
    const name = currentPersona?.full_name || 'Local workspace';
    return (
      <div className="qb-prof">
        <div className="qb-prof-card">
          <span className="qb-pava qb-pava-out" aria-hidden="true">
            <HugeiconsIcon icon={UserIcon} size={16} strokeWidth={STROKE} />
          </span>
          <span className="qb-pmeta">
            <b>{name}</b>
            <span className="qb-psub">everything stays on this machine</span>
          </span>
        </div>
      </div>
    );
  }

  const name = user?.full_name || currentPersona?.full_name || user?.email || 'Signed in';
  return (
    <div className="qb-prof">
      <button
        type="button"
        className="qb-prof-card"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="qb-pava qb-pava-in" aria-hidden="true">{initialsOf(name)}</span>
        <span className="qb-pmeta">
          <b>{name}</b>
          {user?.email && user.email !== name && <span className="qb-psub">{user.email}</span>}
        </span>
        <HugeiconsIcon className="qb-prof-chev" icon={ArrowDown01Icon} size={15} strokeWidth={STROKE} />
      </button>
      {expanded && (
        <div className="qb-prof-menu">
          <Link to="/settings" search={{ tab: undefined }} className="qb-pm-item" onClick={onNavigate}>
            <HugeiconsIcon icon={UserIcon} size={16} strokeWidth={STROKE} />
            Your profile
          </Link>
          <div className="qb-pm-hr" />
          <button type="button" className="qb-pm-item" onClick={() => void signOut()}>
            <HugeiconsIcon icon={Logout03Icon} size={16} strokeWidth={STROKE} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function DawnFoot() {
  return (
    <div className="qb-drawer-foot">
      <div className="qb-drawer-note">
        <span className="qb-note-pin" aria-hidden="true" />
        Every quest links to its source. Pay is only what the poster wrote.
        No one pays to be pinned here.
        <b>If it's pinned here, it's real.</b>
      </div>
      <div className="qb-dawn" aria-hidden="true">
        <svg viewBox="0 0 272 118" preserveAspectRatio="xMidYMax slice">
          <circle cx="198" cy="56" r="15" fill="#E4AE58" opacity=".8" />
          <circle cx="198" cy="56" r="24" fill="#E4AE58" opacity=".16" />
          <path d="M0 84 C40 66 82 62 122 74 C156 84 196 84 272 70 L272 118 L0 118 Z" fill="#93A390" opacity=".5" />
          <path d="M0 98 C56 84 118 90 168 98 C208 104 242 102 272 94 L272 118 L0 118 Z" fill="#5F7A66" opacity=".55" />
        </svg>
      </div>
    </div>
  );
}

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  onHome: boolean;
  onBoard: boolean;
  onLog: boolean;
  onSettings: boolean;
  onHealth: boolean;
}

export function Drawer({ open, onClose, onHome, onBoard, onLog, onSettings, onHealth }: DrawerProps) {
  const { data: summary } = useBoardSummary();
  const { hostedMode } = useWorkspace();

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <>
      <div className="qb-scrim" data-testid="qb-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="qb-drawer" aria-label="Menu" aria-hidden={!open} {...(open ? {} : { inert: true })}>
        <div className="qb-drawer-brand">
          <span className="qb-brand-tile" aria-hidden="true"><BrandMark className="qb-mark" /></span>
          <b>Questboard</b>
          <button type="button" className="qb-xbtn" aria-label="Close the menu" onClick={onClose}>
            <HugeiconsIcon icon={Cancel01Icon} size={17} strokeWidth={STROKE} />
          </button>
        </div>

        <ProfileCard onNavigate={onClose} />

        <nav className="qb-drawer-nav">
          <Link to="/home" className={onHome ? 'qb-nav-item qb-active' : 'qb-nav-item'} onClick={onClose}>
            <span className="qb-nico"><HugeiconsIcon icon={Home01Icon} size={18} strokeWidth={STROKE} /></span>
            Home
          </Link>
          <Link to="/board" className={onBoard ? 'qb-nav-item qb-active' : 'qb-nav-item'} onClick={onClose}>
            <span className="qb-nico"><HugeiconsIcon icon={PinIcon} size={18} strokeWidth={STROKE} /></span>
            The board
            {summary && <span className="qb-nmeta">{summary.total.toLocaleString()} up</span>}
          </Link>
          <Link to="/log" className={onLog ? 'qb-nav-item qb-active' : 'qb-nav-item'} onClick={onClose}>
            <span className="qb-nico"><HugeiconsIcon icon={Notebook01Icon} size={18} strokeWidth={STROKE} /></span>
            Your log
          </Link>
          <button type="button" className="qb-nav-item qb-soon" disabled>
            <span className="qb-nico"><HugeiconsIcon icon={Notification03Icon} size={18} strokeWidth={STROKE} /></span>
            Alerts <em>soon</em>
          </button>
          <Link
            to="/settings"
            search={{ tab: undefined }}
            className={onSettings ? 'qb-nav-item qb-active' : 'qb-nav-item'}
            onClick={onClose}
          >
            <span className="qb-nico"><HugeiconsIcon icon={Settings02Icon} size={18} strokeWidth={STROKE} /></span>
            Settings
          </Link>
          {/* Ops zone: local mode means you run the board, so the health
              page gets a door here. Hosted visitors never see it. */}
          {!hostedMode && (
            <>
              <div className="qb-nav-hr" aria-hidden="true" />
              <Link
                to="/health"
                className={onHealth ? 'qb-nav-item qb-active' : 'qb-nav-item'}
                onClick={onClose}
              >
                <span className="qb-nico"><HugeiconsIcon icon={Activity01Icon} size={18} strokeWidth={STROKE} /></span>
                Source health
              </Link>
            </>
          )}
        </nav>

        <DawnFoot />
      </aside>
    </>
  );
}
