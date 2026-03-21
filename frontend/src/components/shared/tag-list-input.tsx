import { useState } from 'react';
import { X } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface TagListInputProps {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  helperText?: string;
  emptyText?: string;
  className?: string;
}

export function TagListInput({
  value,
  onChange,
  placeholder = 'Type and press Enter',
  helperText,
  emptyText = 'None added yet.',
  className,
}: TagListInputProps) {
  const [draft, setDraft] = useState('');

  const addTags = (raw: string) => {
    const parts = raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length === 0) return;
    const unique = [...new Set([...value, ...parts])];
    onChange(unique);
    setDraft('');
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className={cn('space-y-2', className)}>
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          addTags(draft);
        }}
        onBlur={() => {
          if (draft.trim()) addTags(draft);
        }}
        placeholder={placeholder}
        className="h-9"
      />

      {value.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => removeTag(tag)}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-card px-3 py-1 text-xs text-text-secondary transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:hover:border-red-800 dark:hover:bg-red-950 dark:hover:text-red-400"
            >
              {tag}
              <X className="h-3 w-3" />
            </button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{emptyText}</p>
      )}

      {helperText && <p className="text-xs text-text-muted">{helperText}</p>}
    </div>
  );
}
