import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { HugeiconsIcon } from '@hugeicons/react';
import { Location01Icon } from '@hugeicons/core-free-icons';
import { filterPlaces, type PlaceOption } from '@/features/board/places';
import { getLocationSuggestions } from '@/lib/profile-preferences';
import '@/features/board/place-picker.css';

/* The board's place control: a plain-text field that suggests US states
   and cities as you type. Picking a state passes the state name (the
   backend matches it against the pre-parsed state_codes); picking a city
   passes the bare city (a location substring). Free text always works, so
   any place the list does not carry still filters. */

export function PlacePicker({
  value,
  onChange,
  placeholder = 'your city or state',
  ariaLabel,
  className = '',
  suggestionScope = 'board',
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  /** First run uses the global catalog; the board keeps its supply-aware list. */
  suggestionScope?: 'board' | 'global';
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const matches: PlaceOption[] = open
    ? suggestionScope === 'global'
      ? getLocationSuggestions(value).map((suggestion) => ({
          label: suggestion.label,
          value: suggestion.label,
          sub: suggestion.subtitle,
        }))
      : filterPlaces(value)
    : [];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('pointerdown', onDown);
    return () => window.removeEventListener('pointerdown', onDown);
  }, [open]);

  const commit = (opt: PlaceOption) => {
    onChange(opt.value);
    setOpen(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
        return;
      }
      setActive((a) => Math.min(a + 1, matches.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && matches[active]) {
        e.preventDefault();
        commit(matches[active]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className={`qb-place ${className}`.trim()} ref={wrapRef}>
      <HugeiconsIcon icon={Location01Icon} size={16} strokeWidth={1.7} />
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => {
          if (value.trim()) setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {open && matches.length > 0 && (
        <ul className="qb-place-menu" id={listId} role="listbox">
          {matches.map((opt, i) => (
            <li
              key={opt.label}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'qb-place-opt qb-place-opt-on' : 'qb-place-opt'}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(opt);
              }}
            >
              <span className="qb-place-opt-label">{opt.label}</span>
              {opt.sub && <span className="qb-place-opt-sub">{opt.sub}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
