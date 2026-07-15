/* Per-kind facet chips: a kind's own sub-filters from @questboard/kinds,
   one active at a time, click again to clear. Kinds without facets render
   nothing. Counts are the API's own totals with the facet applied, the
   same page_size 1 probe the preset chips use. */

import { Chip } from '@questboard/ui';
import { facetsFor, type KindFacet } from '@questboard/kinds';
import { useApplications } from '@/hooks/use-applications';
import type { ApplicationFilters } from '@/types/application';

function FacetChip({
  facet,
  active,
  countFilters,
  onToggle,
}: {
  facet: KindFacet;
  active: boolean;
  countFilters: ApplicationFilters;
  onToggle: () => void;
}) {
  const { data } = useApplications(countFilters);
  return <Chip label={facet.label} count={data?.total} active={active} onClick={onToggle} />;
}

export function FacetChips({
  kind,
  selected,
  countBase,
  onToggle,
}: {
  kind: string;
  selected: string | undefined;
  /** the board's current filters; each chip probes them with itself applied */
  countBase: ApplicationFilters;
  onToggle: (id: string) => void;
}) {
  const facets = facetsFor(kind);
  if (facets.length === 0) return null;
  return (
    <div className="qb-facet-row">
      {facets.map((facet) => (
        <FacetChip
          key={facet.id}
          facet={facet}
          active={selected === facet.id}
          countFilters={{ ...countBase, facet: facet.id, page: 1, page_size: 1 }}
          onToggle={() => onToggle(facet.id)}
        />
      ))}
    </div>
  );
}
