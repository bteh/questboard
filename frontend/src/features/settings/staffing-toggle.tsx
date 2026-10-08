import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';

/* Saved as exclude_staffing_agencies (default true) so older workspaces keep
   their behavior; the box shows the include side because that is the choice
   a seeker makes. */
interface StaffingToggleProps {
  excludeStaffingAgencies: boolean;
  onChange: (excludeStaffingAgencies: boolean) => void;
}

export function StaffingToggle({ excludeStaffingAgencies, onChange }: StaffingToggleProps) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id="include-staffing"
        checked={!excludeStaffingAgencies}
        onCheckedChange={(checked) => onChange(!checked)}
      />
      <div>
        <Label htmlFor="include-staffing">Include staffing agencies</Label>
        <p className="mt-0.5 text-xs text-text-muted">Staffing agencies. Often contract-to-hire. A common way back into IT.</p>
      </div>
    </div>
  );
}
