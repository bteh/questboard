import { useState } from 'react';
import { ArrowDownToLine, GraduationCap, Loader2, ScrollText, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { TagListInput } from '@/components/shared/tag-list-input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useSaveWorkspacePreferences } from '@/hooks/use-workspace';
import { mergeKeywordLists } from '@/lib/resume-analysis';
import type { ResumeAnalysisSummary } from '@/types/resume';
import type { WorkspacePreferences } from '@/types/workspace';

interface ResumeAnalysisPanelProps {
  analysis: ResumeAnalysisSummary;
  /** Current saved preferences, the base the edited roles/keywords are merged into. */
  preferences: WorkspacePreferences;
}

/**
 * "What we read from your resume": the review-and-correct panel shown after a
 * resume upload that produced an analysis.
 *
 * Skills, target roles, and keywords are editable chip lists. Roles and
 * keywords persist to the workspace search preferences (the same API the
 * Search settings tab uses). Skills have no dedicated preferences field, so
 * they are persisted by explicitly promoting them into search keywords.
 */
export function ResumeAnalysisPanel({ analysis, preferences }: ResumeAnalysisPanelProps) {
  const savePreferences = useSaveWorkspacePreferences();

  const [skills, setSkills] = useState<string[]>(analysis.skills);
  const [roles, setRoles] = useState<string[]>(
    analysis.suggested_target_roles.length > 0 ? analysis.suggested_target_roles : preferences.roles,
  );
  const [keywords, setKeywords] = useState<string[]>(
    analysis.suggested_keywords.length > 0 ? analysis.suggested_keywords : preferences.keywords,
  );

  const handlePromoteSkills = () => {
    if (skills.length === 0) return;
    setKeywords((prev) => mergeKeywordLists(prev, skills));
    toast.success('Skills added to keywords. Save to apply.');
  };

  const handleSave = () => {
    savePreferences.mutate(
      {
        ...preferences,
        roles,
        keywords,
        current_title: analysis.current_title || preferences.current_title,
        current_level: analysis.seniority || preferences.current_level,
      },
      {
        onSuccess: () => toast.success('Search preferences updated from your resume'),
        onError: (error) =>
          toast.error(error instanceof Error ? error.message : 'Could not save. Try again in a minute.'),
      },
    );
  };

  return (
    <div
      data-testid="resume-analysis-panel"
      className="space-y-5 rounded-xl border border-border-default bg-bg-card p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-semibold text-text-primary">
            <Sparkles className="h-4 w-4 text-brand" />
            What we read from your resume
          </h3>
          <p className="mt-0.5 text-xs text-text-muted">
            Fix anything wrong here. These drive your search and ranking.
          </p>
        </div>
      </div>

      {(analysis.current_title || analysis.seniority) && (
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
          {analysis.current_title && (
            <div>
              <span className="font-medium text-text-tertiary uppercase tracking-wider text-[10px]">Current title</span>
              <p className="mt-0.5 text-sm text-text-primary">{analysis.current_title}</p>
            </div>
          )}
          {analysis.seniority && (
            <div>
              <span className="font-medium text-text-tertiary uppercase tracking-wider text-[10px]">Seniority</span>
              <p className="mt-0.5 text-sm text-text-primary capitalize">{analysis.seniority}</p>
            </div>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <Label>Skills</Label>
          {skills.length > 0 && (
            <button
              type="button"
              onClick={handlePromoteSkills}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-brand transition-colors hover:text-brand-hover"
            >
              <ArrowDownToLine className="h-3 w-3" />
              Add all to keywords
            </button>
          )}
        </div>
        <TagListInput
          value={skills}
          onChange={setSkills}
          placeholder="Add a skill, press Enter"
          emptyText="No skills extracted."
          helperText="Skills found on your resume. Use 'Add all to keywords' to make them search terms."
        />
      </div>

      <div className="space-y-1.5">
        <Label>Target roles</Label>
        <TagListInput
          value={roles}
          onChange={setRoles}
          placeholder="The title you want next, then press Enter"
          emptyText="No target roles suggested."
          helperText="Titles you want next, not the ones you had. Breaking in? Try Data Analyst, IT Support Specialist, Sales Development Representative, Customer Success Associate."
        />
      </div>

      <div className="space-y-1.5">
        <Label>Search keywords</Label>
        <TagListInput
          value={keywords}
          onChange={setKeywords}
          placeholder="Add a keyword, press Enter"
          emptyText="No keywords suggested."
        />
      </div>

      {analysis.certifications.length > 0 && (
        <div className="space-y-1.5">
          <Label className="flex items-center gap-1.5">
            <ScrollText className="h-3.5 w-3.5 text-text-muted" />
            Certifications
          </Label>
          <div className="flex flex-wrap gap-1.5">
            {analysis.certifications.map((cert) => (
              <span
                key={cert}
                className="inline-flex items-center rounded-full border border-border-default bg-bg-subtle px-3 py-1 text-xs text-text-secondary"
              >
                {cert}
              </span>
            ))}
          </div>
        </div>
      )}

      {analysis.education.length > 0 && (
        <div className="space-y-1.5">
          <Label className="flex items-center gap-1.5">
            <GraduationCap className="h-3.5 w-3.5 text-text-muted" />
            Education
          </Label>
          <ul className="space-y-1 text-sm text-text-secondary">
            {analysis.education.map((entry, index) => (
              <li key={`${entry.degree}-${entry.institution}-${index}`}>
                {[entry.degree, entry.field].filter(Boolean).join(' in ')}
                {entry.institution && (
                  <span className="text-text-muted">, {entry.institution}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3 border-t border-border-default pt-3">
        <Button size="sm" onClick={handleSave} disabled={savePreferences.isPending}>
          {savePreferences.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save to search preferences
        </Button>
        <p className="text-xs text-text-muted">Roles and keywords update your saved search.</p>
      </div>
    </div>
  );
}
