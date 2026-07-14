/* The constitution's zeroed-bounty rules, as executable tests: decoration
   never reorders anything, the shipped null-tag state changes nothing, a
   poster without its catch is never monetized, and a live tag only ever
   edits the href's query string. */

import { describe, expect, it } from 'vitest';
import { decoratePosterLink, type AffiliateRegistry } from './affiliate';

const LIVE: AffiliateRegistry = {
  'ebay.com': {
    program: 'eBay Partner Network',
    tag: 'campid=test123',
    disclosure: 'test disclosure ebay',
  },
  'poshmark.com': {
    program: 'Poshmark referral program',
    tag: 'ref=qb-test',
    disclosure: 'test disclosure poshmark',
  },
};

describe('decoratePosterLink', () => {
  it('never reorders or replaces the posters it decorates', () => {
    const models = [
      { id: 1, href: 'https://www.ebay.com/sch/i.html?_nkw=lego' },
      { id: 2, href: 'https://poshmark.com/listing/abc' },
      { id: 3, href: 'https://craigslist.org/d/gigs' },
      { id: 4, href: 'https://www.ebay.com/itm/999' },
      { id: 5, href: undefined as string | undefined },
      { id: 6, href: 'https://turo.com/us/en/list-your-car' },
      { id: 7, href: 'https://www.mercari.com/sell/' },
    ];
    const before = [...models];
    const decorated = models.map((m) => decoratePosterLink(m.href, true, LIVE));

    expect(models).toHaveLength(before.length);
    models.forEach((m, i) => {
      expect(m).toBe(before[i]);
      expect(m.id).toBe(before[i].id);
    });
    /* the output carries a link and maybe a disclosure, nothing sortable */
    for (const out of decorated) {
      for (const key of Object.keys(out)) {
        expect(['href', 'disclosure']).toContain(key);
      }
    }
    /* only the matching hrefs changed, and only their query string */
    expect(decorated[0].href).toContain('campid=test123');
    expect(decorated[1].href).toContain('ref=qb-test');
    expect(decorated[2].href).toBe(models[2].href);
    expect(decorated[4].href).toBeUndefined();
    expect(decorated[5].href).toBe(models[5].href);
    expect(decorated[6].href).toBe(models[6].href);
  });

  it('ships with every tag null: hrefs come back byte-identical, no disclosure', () => {
    const hrefs = [
      'https://www.ebay.com/sch/i.html?_nkw=camera',
      'https://poshmark.com/listing/abc',
      'https://www.whatnot.com/invite/seller',
      'https://www.mercari.com/sell/',
      'https://turo.com/us/en/list-your-car',
      'https://www.depop.com/sell/',
    ];
    for (const href of hrefs) {
      const out = decoratePosterLink(href, true);
      expect(out.href).toBe(href);
      expect(out.disclosure).toBeUndefined();
    }
  });

  it('never decorates a poster whose catch is missing, even with a live tag', () => {
    const href = 'https://www.ebay.com/sch/i.html?_nkw=camera';
    const out = decoratePosterLink(href, false, LIVE);
    expect(out.href).toBe(href);
    expect(out.disclosure).toBeUndefined();
  });

  it('a decorated href carries the tag param and keeps the original URL intact', () => {
    const out = decoratePosterLink('https://www.ebay.com/sch/i.html?_nkw=lego', true, LIVE);
    const url = new URL(out.href!);
    expect(url.hostname).toBe('www.ebay.com');
    expect(url.pathname).toBe('/sch/i.html');
    expect(url.searchParams.get('_nkw')).toBe('lego');
    expect(url.searchParams.get('campid')).toBe('test123');
    expect(out.disclosure).toBe('test disclosure ebay');
  });

  it('leaves non-registry, malformed, and missing hrefs untouched', () => {
    expect(decoratePosterLink(undefined, true, LIVE)).toEqual({ href: undefined });
    expect(decoratePosterLink('not a url', true, LIVE)).toEqual({ href: 'not a url' });
    const other = 'https://example.com/quest';
    expect(decoratePosterLink(other, true, LIVE)).toEqual({ href: other });
    /* a lookalike host must not match: notebay.com is not a subdomain of ebay.com */
    const lookalike = 'https://notebay.com/deal';
    expect(decoratePosterLink(lookalike, true, LIVE)).toEqual({ href: lookalike });
  });
});
