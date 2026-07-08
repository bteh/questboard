/** The tight prompt behind a full read. */

import type { ApplicationResponse } from '@/types/application';

const MAX_POSTING_CHARS = 6000;

/**
 * Null when the record has no description text: a full read of nothing would
 * only invite invention, so the quick read stands and the request completes.
 */
export function buildFullReadPrompt(app: ApplicationResponse): string | null {
  const posting = (app.description || '').trim();
  if (!posting) return null;
  const title = app.company ? `${app.job_title}, ${app.company}` : app.job_title;
  return [
    'Explain this posting in plain words to someone deciding whether to pursue it.',
    'Write one short paragraph, under 90 words. No headings, no lists.',
    'Never write in the first person.',
    'Use only facts stated in the posting. If pay or dates are not stated, do not invent or guess them.',
    'Say what the poster wants, and end with the one thing applicants likely miss.',
    '',
    `Posting title: ${title}`,
    'Posting text:',
    posting.slice(0, MAX_POSTING_CHARS),
  ].join('\n');
}
