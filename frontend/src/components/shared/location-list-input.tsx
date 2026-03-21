import { useMemo, useState } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLocationSuggestions } from '@/hooks/use-workspace';
import type { PlaceSelection } from '@/types/workspace';
import { cn } from '@/lib/utils';
import {
  createManualPlace,
  getLocationSuggestions,
  normalizeLocationInput,
  normalizePlaceList,
  placeLabel,
  suggestionToPlace,
} from '@/lib/profile-preferences';

interface LocationListInputProps {
  value: PlaceSelection[];
  onChange: (next: PlaceSelection[]) => void;
  placeholder?: string;
  helperText?: string;
  emptyText?: string;
  className?: string;
}

export function LocationListInput({
  value,
  onChange,
  placeholder = 'Add a city, state, or region',
  helperText = 'Type City, ST or choose a suggestion. Press Enter or click Add. Remote is controlled separately.',
  emptyText = 'No preferred locations saved yet.',
  className,
}: LocationListInputProps) {
  const [draft, setDraft] = useState('');
  const normalizedDraft = normalizeLocationInput(draft);
  const { data: remoteSuggestions } = useLocationSuggestions(draft, draft.trim().length >= 2);
  const localSuggestions = useMemo(
    () => getLocationSuggestions(draft, value.map((item) => item.label)),
    [draft, value],
  );
  const suggestions = (remoteSuggestions && remoteSuggestions.length > 0 ? remoteSuggestions : localSuggestions);
  const hasExactSuggestion = suggestions.some((suggestion) => suggestion.label === normalizedDraft);

  const addLocations = (raw: string) => {
    const parts = raw
      .split(/\n|;/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (parts.length === 0) return;
    onChange(normalizePlaceList([...value, ...parts.map((item) => createManualPlace(item))]));
    setDraft('');
  };

  const addSuggestion = (suggestion: PlaceSelection) => {
    onChange(normalizePlaceList([...value, suggestion]));
    setDraft('');
  };

  const removeLocation = (target: string) => {
    onChange(value.filter((item) => item.label !== target));
  };

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            addLocations(draft);
          }}
          placeholder={placeholder}
          className="h-9"
        />
        <Button
          type="button"
          variant="outline"
          className="h-9 shrink-0"
          onClick={() => addLocations(draft)}
          disabled={!draft.trim()}
        >
          Add
        </Button>
      </div>

      {draft.trim() && (suggestions.length > 0 || !!normalizedDraft) && (
        <div className="rounded-xl border border-border-default bg-bg-card p-1.5">
          <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-text-muted">
            Suggestions
          </p>
          <div className="space-y-1">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion.label}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addSuggestion(suggestionToPlace(suggestion))}
                className="flex w-full items-start justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-bg-subtle hover:text-text-primary"
              >
                <div className="min-w-0">
                  <p className="text-sm text-text-secondary">{suggestion.label}</p>
                  <p className="text-[11px] text-text-muted">
                    {suggestion.subtitle}
                  </p>
                </div>
                <span className="text-[10px] uppercase tracking-wide text-text-muted">
                  {suggestion.kind}
                </span>
              </button>
            ))}
            {!hasExactSuggestion && normalizedDraft && (
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addSuggestion(createManualPlace(normalizedDraft))}
                className="flex w-full items-start justify-between gap-3 rounded-lg border border-dashed border-border-default px-2.5 py-2 text-left transition-colors hover:border-border-hover hover:bg-bg-subtle"
              >
                <div className="min-w-0">
                  <p className="text-sm text-text-secondary">Use exactly: {normalizedDraft}</p>
                  <p className="text-[11px] text-text-muted">
                    Keep your custom location if none of the suggestions are right.
                  </p>
                </div>
              </button>
            )}
          </div>
        </div>
      )}

      {value.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {value.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => removeLocation(item.label)}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-card px-3 py-1 text-xs text-text-secondary transition-colors hover:border-border-hover hover:bg-bg-subtle"
            >
              {placeLabel(item)}
              <X className="h-3 w-3" />
            </button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{emptyText}</p>
      )}

      <p className="text-xs text-text-muted">{helperText}</p>
    </div>
  );
}
