import { Link, useMatchRoute } from '@tanstack/react-router';
import { LayoutDashboard, Search, Briefcase, BarChart3, Settings as SettingsIcon, Zap, Sun, Moon, Monitor } from 'lucide-react';
import { useDashboardStats } from '@/hooks/use-analytics';
import { useLLMStatus } from '@/hooks/use-settings';
import { useTheme } from '@/contexts/theme-context';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { to: '/' as const, label: 'Dashboard', icon: LayoutDashboard },
  { to: '/search' as const, label: 'Search', icon: Search },
  { to: '/applications' as const, label: 'Applications', icon: Briefcase },
  { to: '/analytics' as const, label: 'Analytics', icon: BarChart3 },
  { to: '/settings' as const, label: 'Settings', icon: SettingsIcon },
];

const THEME_OPTIONS = [
  { value: 'light' as const, icon: Sun, label: 'Light' },
  { value: 'dark' as const, icon: Moon, label: 'Dark' },
  { value: 'system' as const, icon: Monitor, label: 'System' },
];

export function Sidebar() {
  const { data: stats } = useDashboardStats();
  const { data: llm } = useLLMStatus();
  const { theme, setTheme } = useTheme();
  const matchRoute = useMatchRoute();

  return (
    <aside className="flex h-screen w-[260px] flex-col border-r border-border-default bg-bg-card">
      {/* Brand */}
      <Link to="/" className="flex items-center gap-3 px-5 py-5 hover:bg-bg-subtle transition-colors cursor-pointer">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand shadow-sm">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-white">
            <path d="M4 12V4l4 2v6l-4-2z" fill="currentColor" opacity="0.7" />
            <path d="M8 6l4-2v8l-4 2V6z" fill="currentColor" />
          </svg>
        </div>
        <div>
          <span className="text-sm font-semibold text-text-primary tracking-tight">Launchboard</span>
          <p className="text-[11px] text-text-muted leading-none mt-0.5">AI Job Agent</p>
        </div>
      </Link>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
          const isActive = !!matchRoute({ to, fuzzy: to !== '/' });
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-100',
                isActive
                  ? 'bg-brand-light text-brand'
                  : 'text-text-tertiary hover:bg-bg-subtle hover:text-text-primary'
              )}
            >
              <Icon className={cn('h-4 w-4', isActive ? 'text-brand' : 'text-text-muted')} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Stats Summary */}
      {stats && (
        <div className="mx-3 mb-3 rounded-lg border border-border-default bg-bg-subtle px-4 py-3">
          <div className="grid grid-cols-2 gap-3 text-center">
            <div>
              <div className="text-lg font-semibold text-text-primary tabular-nums">{stats.total_jobs}</div>
              <div className="text-[11px] font-medium text-text-muted">Found</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-success tabular-nums">{stats.strong_apply_count}</div>
              <div className="text-[11px] font-medium text-text-muted">Strong</div>
            </div>
          </div>
        </div>
      )}

      {/* Theme Toggle */}
      <div className="mx-3 mb-3">
        <div className="flex items-center rounded-lg border border-border-default bg-bg-subtle p-0.5" role="radiogroup" aria-label="Theme">
          {THEME_OPTIONS.map(({ value, icon: Icon, label }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={theme === value}
              aria-label={label}
              onClick={() => setTheme(value)}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors duration-100',
                theme === value
                  ? 'bg-bg-card text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* LLM Connection */}
      <div className="border-t border-border-default px-4 py-3">
        <div className="flex items-center gap-2" role="status" aria-label={`LLM: ${llm?.available ? 'connected' : llm?.configured ? 'disconnected' : 'not configured'}`}>
          <div
            className={cn(
              'h-1.5 w-1.5 rounded-full shrink-0',
              llm?.available ? 'bg-success' : llm?.configured ? 'bg-danger' : 'bg-text-faint'
            )}
            aria-hidden="true"
          />
          <Zap className="h-3.5 w-3.5 text-text-muted shrink-0" />
          <span className="text-xs text-text-muted truncate">
            {llm?.available ? llm.label || 'Connected' : llm?.configured ? 'Disconnected' : 'Not configured'}
          </span>
        </div>
      </div>
    </aside>
  );
}
