/* The assistant run's checkpoints, drawn from what it actually did. */

import { stepLines, type AssistantStep } from '@/features/board/assistant-steps';

export function AssistantSteps({ steps }: { steps: AssistantStep[] }) {
  const lines = stepLines(steps);
  if (lines.length === 0) return null;

  return (
    <ul className="qb-agentsteps">
      {lines.map((line) => (
        <li key={line.key} className={line.done ? 'qb-agentstep-done' : 'qb-agentstep-now'}>
          <span className="qb-agentstep-mark" aria-hidden="true">
            {line.done ? '✓' : '·'}
          </span>
          {line.label}
          {line.repeat > 0 && <span className="qb-agentstep-repeat"> ×{line.repeat}</span>}
        </li>
      ))}
    </ul>
  );
}
