/**
 * Shared Questboard types. Starting point: the evaluation-report shapes
 * copied from frontend/src/types/application.ts. The frontend still uses
 * its own copies; migration to this package happens with the design-system
 * work.
 */

export interface RequirementMatch {
  requirement: string;
  strength: 'strong' | 'partial' | 'missing';
  evidence: string;
  mitigation: string;
}

export interface EvaluationReport {
  archetype: string;
  tldr: string;
  requirements: RequirementMatch[];
  top_gaps: string[];
  recommended_framing: string;
  red_flags: string[];
}
