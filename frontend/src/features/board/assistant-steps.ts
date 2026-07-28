/* The assistant run's checkpoints, in plain words.

   Each step is one MCP tool call the run actually made, so the list only ever
   claims work that happened. The board used to infer the phase from elapsed
   seconds and got it wrong in the obvious way: past 100 seconds it said
   "Ranking against your experience" whether or not ranking had begun. */

export interface AssistantStep {
  tool: string;
  at: string;
  count: number;
}

const STEP_WORDS: Record<string, string> = {
  read_resume_for_matching: 'Read your resume',
  get_career_preferences: 'Read your saved search',
  set_career_preferences: 'Sharpened your target roles',
  refresh_work: 'Started the source pull',
  get_refresh_status: 'Waiting on the sources',
  search_work: 'Pulled the shortlist',
  set_work_fit: 'Wrote your rankings',
};

/* Tools the run makes on its own that say nothing about progress. Hidden so
   the list reads as a story rather than a log. */
const QUIET_TOOLS = new Set(['server_info', 'get_source_status', 'get_opportunity']);

export interface StepLine {
  key: string;
  label: string;
  /* The last step is what the run is doing NOW; the ones above are done. */
  done: boolean;
  /* "×6" on the polling step, so a long wait reads as waiting and not stuck. */
  repeat: number;
}

export function stepLines(steps: AssistantStep[]): StepLine[] {
  const shown = steps.filter((s) => !QUIET_TOOLS.has(s.tool));
  return shown.map((step, i) => ({
    key: `${step.tool}-${i}`,
    label: STEP_WORDS[step.tool] ?? step.tool.replace(/_/g, ' '),
    done: i < shown.length - 1,
    repeat: step.count > 1 ? step.count : 0,
  }));
}
