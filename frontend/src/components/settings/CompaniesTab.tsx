import { useState } from 'react';
import { Building2, Loader2, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAddCompany, useRemoveCompany, useWatchlist } from '@/hooks/use-watchlist';
import { openExternalClick } from '@/lib/open-external';
import type { WatchlistCompany } from '@/api/watchlist';

/* The companies the user watches. Add one by name (the backend looks it up
   on the ATS platforms) or paste its careers link (the backend stores the
   board token from the link). Every refresh then checks the boards it
   found directly. Entries without a confirmed board render as unfinished,
   with an inline input to paste the careers link, never as a healthy row. */

const ATS_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  workday: 'Workday',
};

function boardMissing(company: WatchlistCompany): boolean {
  return !ATS_LABELS[company.ats];
}

function atsLine(company: WatchlistCompany): string {
  const label = ATS_LABELS[company.ats];
  if (!label) return 'Job board not found yet.';
  if (company.job_count === 1) return `${label} board, 1 open role`;
  if (company.job_count > 1) return `${label} board, ${company.job_count} open roles`;
  return `${label} board`;
}

function looksLikeUrl(value: string): boolean {
  return (
    /^https?:\/\//i.test(value) ||
    /(greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com)\//i.test(value)
  );
}

export function CompaniesTab() {
  const watchlist = useWatchlist();
  const add = useAddCompany();
  const remove = useRemoveCompany();
  const [name, setName] = useState('');
  const [linkDrafts, setLinkDrafts] = useState<Record<string, string>>({});

  const companies = watchlist.data?.companies ?? [];
  const addMessage = add.data?.message ?? '';
  const addErrorStatus = (add.error as { status?: number } | null)?.status;
  const addErrorLine =
    addErrorStatus === 422 && add.error instanceof Error && add.error.message
      ? add.error.message
      : 'Could not add that company. Check the name and try again.';

  const handleAdd = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || add.isPending) return;
    const payload = looksLikeUrl(trimmed) ? { url: trimmed } : { name: trimmed };
    add.mutate(payload, { onSuccess: () => setName('') });
  };

  const handleLink = (companyName: string) => (event: React.FormEvent) => {
    event.preventDefault();
    const draft = (linkDrafts[companyName] ?? '').trim();
    if (!draft || add.isPending) return;
    add.mutate(
      { name: companyName, url: draft },
      {
        onSuccess: () => setLinkDrafts((prev) => ({ ...prev, [companyName]: '' })),
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-4 w-4" /> Companies you watch
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">
          Add a company by name, or paste its careers page link. Questboard checks its job board
          on every refresh, so new postings show up without the wait.
        </p>

        <form onSubmit={handleAdd} className="flex items-center gap-2">
          <Input
            aria-label="Company name or careers link"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Company name or careers page link"
            disabled={add.isPending}
          />
          <Button type="submit" size="sm" disabled={add.isPending}>
            {add.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-2 h-4 w-4" />
            )}
            {add.isPending ? 'Adding' : 'Add'}
          </Button>
        </form>
        {add.isError && <p className="text-sm text-destructive">{addErrorLine}</p>}
        {add.isSuccess && addMessage && (
          <p className="text-sm text-text-secondary">{addMessage}</p>
        )}

        {watchlist.isLoading ? (
          <p className="text-sm text-text-muted">Checking your list…</p>
        ) : watchlist.isError ? (
          <p className="text-sm text-destructive">
            Could not load your companies. Try again in a moment.
          </p>
        ) : companies.length === 0 ? (
          <p className="text-sm text-text-muted">
            No companies yet. Add one to check its job board on every refresh.
          </p>
        ) : (
          <div className="space-y-2">
            {companies.map((company) => (
              <div
                key={company.name}
                className="flex items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary">{company.name}</p>
                  {boardMissing(company) ? (
                    <div className="mt-1 space-y-2">
                      <p className="text-xs text-text-muted">
                        Job board not found yet. Paste its careers link to finish.
                      </p>
                      <form
                        onSubmit={handleLink(company.name)}
                        className="flex items-center gap-2"
                      >
                        <Input
                          aria-label={`Careers link for ${company.name}`}
                          value={linkDrafts[company.name] ?? ''}
                          onChange={(event) =>
                            setLinkDrafts((prev) => ({
                              ...prev,
                              [company.name]: event.target.value,
                            }))
                          }
                          placeholder="Paste its careers link"
                          className="h-8 text-xs"
                          disabled={add.isPending}
                        />
                        <Button
                          type="submit"
                          size="sm"
                          variant="outline"
                          aria-label={`Save link for ${company.name}`}
                          disabled={add.isPending}
                        >
                          Save
                        </Button>
                      </form>
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">
                      {atsLine(company)}
                      {company.careers_url && (
                        <>
                          {' '}
                          <a
                            href={company.careers_url}
                            onClick={openExternalClick(company.careers_url)}
                            className="font-medium underline underline-offset-2"
                          >
                            Careers page
                          </a>
                        </>
                      )}
                    </p>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={`Remove ${company.name}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(company.name)}
                >
                  Remove
                </Button>
              </div>
            ))}
          </div>
        )}
        {remove.isError && (
          <p className="text-sm text-destructive">Could not remove that company. Try again.</p>
        )}
      </CardContent>
    </Card>
  );
}
