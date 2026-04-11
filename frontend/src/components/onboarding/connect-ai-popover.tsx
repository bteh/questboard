import { cloneElement, isValidElement, useState, type ReactElement } from 'react';
import { AiDiagnosticModal } from '@/components/onboarding/ai-diagnostic-modal';

interface ConnectAiPopoverProps {
  /**
   * Trigger element. Gets a click handler attached that opens the
   * diagnostic modal. Any React element works.
   */
  children: ReactElement;
  /** Deprecated — popover positioning props are ignored now that this
   *  opens a dialog instead. Kept for backwards compatibility with
   *  existing call sites that pass side/align. */
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
}

/**
 * Thin wrapper around AiDiagnosticModal that preserves the ConnectAiPopover
 * trigger API. Historically this was a popover; it's now a proper dialog
 * because popover-hidden UX was too subtle — users couldn't find how to
 * fix a broken AI connection.
 *
 * All existing call sites work unchanged: wrap any element, clicking it
 * opens the diagnostic modal.
 */
export function ConnectAiPopover({ children }: ConnectAiPopoverProps) {
  const [open, setOpen] = useState(false);

  const trigger = isValidElement(children)
    ? cloneElement(children as ReactElement<{ onClick?: () => void }>, {
        onClick: () => setOpen(true),
      })
    : children;

  return (
    <>
      {trigger}
      <AiDiagnosticModal open={open} onOpenChange={setOpen} />
    </>
  );
}
