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
  lookafter: { bring: 'references' },
  flip: {
    bring: 'cash upfront and patience',
    catchLine: 'grading and resale fees eat the spread; comps first',
  },
  house: {
    bring: '21+, a KYC ID before you can bet, a funded bank account',
    catchLine: 'the book limits you the moment you start winning (gubbing)',
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
