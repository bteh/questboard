import { useState } from 'react';
import { Loader2, Plus, Store } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAddWatchedPage, useRemoveWatchedPage, useWatchedPages } from '@/hooks/use-watched-pages';
import { openExternalClick } from '@/lib/open-external';
import type { WatchedPage } from '@/api/watched-pages';

/* Places I'd work at: shops that post jobs only on their own site. Each
   quest refresh reads these pages and puts part-time openings near the
   saved place on the Part-time lane. Suggestions come from the starter
   list and are added only on a click. */

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function statusLine(page: WatchedPage): string {
  if (page.last_error) return `Last check failed. ${page.last_error}`;
  if (page.last_found === 1) return '1 part-time opening near you';
  return `${page.last_found} part-time openings near you`;
}

export function WatchedPagesSection() {
  const watched = useWatchedPages();
  const add = useAddWatchedPage();
  const remove = useRemoveWatchedPage();
  const [url, setUrl] = useState('');

  const pages = watched.data?.pages ?? [];
  const suggestions = watched.data?.suggestions ?? [];
  const addError =
    add.error instanceof Error && add.error.message
      ? add.error.message
      : 'Could not add that page. Try again.';

  const submit = (value: string, onDone?: () => void) => {
    const trimmed = value.trim();
    if (!trimmed || add.isPending) return;
    add.mutate(trimmed, { onSuccess: onDone });
  };

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Store className="h-4 w-4" /> Places I'd work at
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">
          Paste a shop's careers page. Part-time openings near you land on the Part-time lane
          every refresh.
        </p>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit(url, () => setUrl(''));
          }}
          className="flex items-center gap-2"
        >
          <Input
            aria-label="Careers page link"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://shop.com/pages/careers"
            disabled={add.isPending}
          />
          <Button type="submit" size="sm" disabled={add.isPending}>
            {add.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-2 h-4 w-4" />
            )}
            {add.isPending ? 'Checking' : 'Add'}
          </Button>
        </form>
        {add.isError && <p className="text-sm text-destructive">{addError}</p>}
        {add.isSuccess && add.data?.message && (
          <p className="text-sm text-text-secondary">{add.data.message}</p>
        )}

        {watched.isLoading ? (
          <p className="text-sm text-text-muted">Loading your places…</p>
        ) : watched.isError ? (
          <p className="text-sm text-destructive">Could not load your places. Try again soon.</p>
        ) : pages.length === 0 ? (
          <p className="text-sm text-text-muted">No places yet.</p>
        ) : (
          <ul className="space-y-2">
            {pages.map((page) => (
              <li
                key={page.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary">
                    {page.name || hostOf(page.url)}
                  </p>
                  <p className="text-xs text-text-muted">
                    {statusLine(page)}{' '}
                    <a
                      href={page.url}
                      onClick={openExternalClick(page.url)}
                      className="font-medium underline underline-offset-2"
                    >
                      {hostOf(page.url)}
                    </a>
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={`Remove ${page.name || hostOf(page.url)}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(page.id)}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
        {remove.isError && <p className="text-sm text-destructive">Could not remove it. Try again.</p>}

        {suggestions.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
              Places to try
            </p>
            <ul className="space-y-2">
              {suggestions.map((suggestion) => (
                <li
                  key={suggestion.url}
                  className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border-default p-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-text-primary">
                      {suggestion.name}
                      {suggestion.area && (
                        <span className="text-text-muted"> · {suggestion.area}</span>
                      )}
                    </p>
                    {suggestion.note && (
                      <p className="text-xs text-text-muted">{suggestion.note}</p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`Add ${suggestion.name}`}
                    disabled={add.isPending}
                    onClick={() => submit(suggestion.url)}
                  >
                    Add
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
