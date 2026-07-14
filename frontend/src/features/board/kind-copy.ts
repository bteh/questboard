/* The per-kind bring and catch lines, from the verified requirements model
   in docs/board-ux-research.md. These are kind-level truths, never
   per-posting guesses: a focus group never asks for a resume, a casting
   call wants you as you look now. Career rows override the bring line with
   their real resume fit; source-stated beginner signals override with the
   friendly "nothing" line. Kinds without live sources yet keep their copy
   here so they light up correctly the day a source lands. */

export interface KindCopy {
  bring: string;
  /** true renders the friendly nothing-needed treatment */
  bringFree?: boolean;
  catchLine?: string;
}

const COPY: Record<string, KindCopy> = {
  skill: {
    bring: 'a portfolio or samples, and your own gear',
  },
  think: {
    bring: 'honest screener answers. no resume, ever',
    catchLine: 'a screener decides if you fit, and can pass you over; that is not a strike on your log',
  },
  perform: {
    bring: 'a current unedited photo, your sizes, your availability',
    catchLine: 'a retouched pro headshot gets you rejected here; they want you as you look now',
  },
  odd: { bring: 'nothing, just show up', bringFree: true },
  deliver: {
    bring: 'a 4-door car, license, insurance, 21+, a background check',
    catchLine: 'personal auto policies often exclude delivery, so check yours first',
  },
  lookafter: {
    bring: 'a meet-and-greet first; reviews if you have them',
    catchLine: 'real owners meet you and the pet in person first; anyone who skips the meet, pays off-platform, or overpays by check is a scam',
  },
  flip: {
    bring: 'cash upfront and patience',
    catchLine: 'grading and resale fees eat the spread; comps first',
  },
  house: {
    /* the live supply is bank and brokerage bonuses (Doctor of Credit,
       BankRewards), so the copy leads with that reality; sportsbook lines
       (21+, gubbing) return if a betting source ever ships */
    bring: 'an ID and money to park; some banks check ChexSystems first',
    catchLine: 'the bonus is taxable income, and closing the account early can claw it back',
  },
  body: {
    bring: 'a government ID and a health screen',
    catchLine: 'eligibility screen on a real study; read the consent first',
  },
  party: { bring: '4 friends and a Saturday, nothing else', bringFree: true },
};

export function kindCopy(kind: string): KindCopy {
  return COPY[kind] ?? { bring: 'what the posting states' };
}
