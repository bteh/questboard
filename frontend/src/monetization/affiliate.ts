/* Pay-blind affiliate machinery. The payment constitution allows a standard
   referral when a reader freely signs up for a platform, under hard rules:
   the bounty is a display concern only and never touches ranking or order,
   a monetized poster must show its catch, and disclosure sits at the link.
   No program is signed yet, so every tag is null and the board renders
   plain links. This module exports nothing usable for sorting. */

export interface AffiliateProgram {
  program: string;
  /** the program's own "name=value" referral pair; null until a deal is signed */
  tag: string | null;
  disclosure: string;
}

export type AffiliateRegistry = Readonly<Record<string, AffiliateProgram>>;

function disclosureFor(name: string): string {
  return `If you start here through this link, ${name} pays Questboard a small referral. It never changes what we show or the order.`;
}

const PROGRAMS: AffiliateRegistry = {
  'ebay.com': { program: 'eBay Partner Network', tag: null, disclosure: disclosureFor('eBay') },
  'poshmark.com': { program: 'Poshmark referral program', tag: null, disclosure: disclosureFor('Poshmark') },
  'whatnot.com': { program: 'Whatnot referral program', tag: null, disclosure: disclosureFor('Whatnot') },
  'mercari.com': { program: 'Mercari referral program', tag: null, disclosure: disclosureFor('Mercari') },
  'turo.com': { program: 'Turo referral program', tag: null, disclosure: disclosureFor('Turo') },
  'depop.com': { program: 'Depop referral program', tag: null, disclosure: disclosureFor('Depop') },
  'rover.com': { program: 'Rover via FlexOffers', tag: null, disclosure: disclosureFor('Rover') },
  'trustedhousesitters.com': {
    program: 'TrustedHousesitters via Impact',
    tag: null,
    disclosure: disclosureFor('TrustedHousesitters'),
  },
};

export function decoratePosterLink(
  href: string | undefined,
  hasCatch: boolean,
  registry: AffiliateRegistry = PROGRAMS, // test seam only
): { href: string | undefined; disclosure?: string } {
  if (!href || !hasCatch) return { href };
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return { href };
  }
  const host = url.hostname.toLowerCase();
  const match = Object.entries(registry).find(
    ([domain]) => host === domain || host.endsWith(`.${domain}`),
  );
  if (!match) return { href };
  const { tag, disclosure } = match[1];
  if (tag === null) return { href };
  const eq = tag.indexOf('=');
  if (eq < 1) return { href };
  url.searchParams.set(tag.slice(0, eq), tag.slice(eq + 1));
  return { href: url.toString(), disclosure };
}
