import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import './money.css';

/* The payment constitution as a page. Every claim states the rule as
   adopted; the referral block is phrased conditionally so the page stays
   true whether or not any referral program is live. */

function Block({ idx, title, children }: { idx: string; title: string; children: ReactNode }) {
  return (
    <section className="qb-money-block">
      <span className="qb-money-idx">{idx}</span>
      <h2>{title}</h2>
      <p>{children}</p>
    </section>
  );
}

export function MoneyPage() {
  return (
    <div style={{ maxWidth: 620, margin: '0 auto', padding: '0 44px 96px' }}>
      <div className="qb-money-head">
        <Link to="/board" className="qb-textlink" style={{ fontSize: 13.5 }}>
          The board
        </Link>
        <h1>How we make money</h1>
        <p className="qb-money-sub">The whole arrangement, on one page.</p>
      </div>

      <Block idx="01" title="The board is free">
        Forever, for everyone. There is no locked tier of listings.
      </Block>

      <Block idx="02" title="The people listed here never pay us">
        No company or poster can pay to be pinned, ranked higher, or put in
        front of you. There is no sales channel for it, so there is nothing
        to buy. A quest gets its pin by clearing the same bars as every
        other quest.
      </Block>

      <Block idx="03" title="You can pay us">
        Later, optional passes will add depth on top of the free board.
        One-time or seasonal, never a subscription dressed up as one. A
        pass never gates a listing; the free board stays whole.
      </Block>

      <Block idx="04" title="Some side-quest links may carry a referral">
        When you start on a platform (say, selling on eBay) through a link
        here, that platform may pay us a small referral. When a link
        carries one, the poster says so right next to it. The referral
        never changes what we show or the order we show it in, and job
        listings never carry one.
      </Block>

      <Block idx="05" title="No ads">
        Not now, not later.
      </Block>

      <p className="qb-money-why">
        This is strict on purpose. A board that takes listing money ends up
        showing you whatever paid to be shown. Everything here rides on the
        promise that what you see is real, and selling placement would
        spend it.
      </p>
      <p className="qb-money-foot">the payment constitution, adopted 2026-07-10</p>
    </div>
  );
}
