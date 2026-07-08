import type { ReactNode } from 'react';

export interface LedgerRowProps {
  title: string;
  /* the small muted tag, e.g. the vertical name */
  tag?: string;
  /* right-aligned mono cell: a pay figure, or any short verdict node */
  pay?: ReactNode;
  payUnit?: string;
}

export function LedgerRow({ title, tag, pay, payUnit }: LedgerRowProps) {
  return (
    <div className="qb-fbrow">
      <span>{title}</span>
      {tag && <span className="qb-fv">{tag}</span>}
      {pay && (
        <span className="qb-fpay">
          {pay} {payUnit && <span className="qb-u">{payUnit}</span>}
        </span>
      )}
    </div>
  );
}
