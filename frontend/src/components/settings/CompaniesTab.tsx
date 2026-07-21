import { useState } from 'react';
import { Building2, Loader2, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAddCompany, useRemoveCompany, useWatchlist } from '@/hooks/use-watchlist';
import { openExternalClick } from '@/lib/open-external';
import type { WatchlistCompany } from '@/api/watchlist';

/* The companies the user watches by name. On add, the backend looks the
   name up on Greenhouse, Lever, and Ashby to find its job board. Every
   refresh then checks the boards it found directly. This tab is the list:
   read it, add to it, take from it. */

const ATS_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
};

function atsLine(company: WatchlistCompany): string {
  const label = ATS_LABELS[company.ats];
  if (!label) return 'No job board found yet';
  if (company.job_count === 1) return `${label} board, 1 open role`;
  if (company.job_count > 1) return `${label} board, ${company.job_count} open roles`;
  return `${label} board`;
}

export function CompaniesTab() {
  const watchlist = useWatchlist();
  const add = useAddCompany();
  const remove = useRemoveCompany();
  const [name, setName] = useState('');

  const companies = watchlist.data?.companies ?? [];

  const handleAdd = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || add.isPending) return;
    add.mutate(trimmed, { onSuccess: () => setName('') });
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
          Add a company by name and Questboard finds its job board. Watched boards get checked
          directly on every refresh, so new postings show up without the wait.
        </p>

        <form onSubmit={handleAdd} className="flex items-center gap-2">
          <Input
            aria-label="Company name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Figma"
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
        {add.isError && (
          <p className="text-sm text-destructive">
            Could not add that company. Check the name and try again.
          </p>
        )}

        {watchlist.isLoading ? (
          <p className="text-sm text-text-muted">Checking your list…</p>
        ) : watchlist.isError ? (
          <p className="text-sm text-destructive">
            Could not load your companies. Try again in a moment.
          </p>
        ) : companies.length === 0 ? (
          <p className="text-sm text-text-muted">
            No companies yet. Add one and its job board gets checked on every refresh.
          </p>
        ) : (
          <div className="space-y-2">
            {companies.map((company) => (
              <div
                key={company.name}
                className="flex items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary">{company.name}</p>
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
