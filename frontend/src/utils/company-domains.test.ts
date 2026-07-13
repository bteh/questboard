import { describe, it, expect } from 'vitest';
import { getCompanyDomain, domainFromUrl, getCompanyLogoUrl } from './company-domains';

describe('getCompanyDomain', () => {
  it('resolves known companies from the map', () => {
    expect(getCompanyDomain('Twilio')).toBe('twilio.com');
    expect(getCompanyDomain('Coinbase')).toBe('coinbase.com');
  });

  it('uses a name that is already written as a domain', () => {
    expect(getCompanyDomain('IPinfo.io')).toBe('ipinfo.io');
    expect(getCompanyDomain('monday.com')).toBe('monday.com');
  });

  it('strips corporate suffixes before the map lookup', () => {
    expect(getCompanyDomain('Twilio Inc.')).toBe('twilio.com');
  });

  it('falls back to a slugified .com for unknown names', () => {
    expect(getCompanyDomain('Sports Trading Exchange')).toBe('sportstradingexchange.com');
  });

  it('prefers a real employer domain from the posting URL', () => {
    // unknown name, but the URL points at the employer's own site
    expect(getCompanyDomain('Acme Widgets', 'https://careers.acmewidgets.com/job/123')).toBe('acmewidgets.com');
  });

  it('ignores ATS / aggregator URLs when guessing the domain', () => {
    // greenhouse is an ATS, so it must not become the logo domain
    const d = getCompanyDomain('Some Startup', 'https://boards.greenhouse.io/somestartup/jobs/123');
    expect(d).toBe('somestartup.com'); // slug of the name, not greenhouse.io
    expect(d).not.toContain('greenhouse');
  });

  it('returns null for an empty name and no url', () => {
    expect(getCompanyDomain('')).toBeNull();
  });
});

describe('domainFromUrl', () => {
  it('extracts and de-subdomains a real employer host', () => {
    expect(domainFromUrl('https://jobs.example.com/x')).toBe('example.com');
    expect(domainFromUrl('https://www.example.com')).toBe('example.com');
  });
  it('returns null for aggregator/ATS hosts', () => {
    expect(domainFromUrl('https://jobs.lever.co/acme/1')).toBeNull();
    expect(domainFromUrl('https://www.linkedin.com/jobs/view/1')).toBeNull();
    expect(domainFromUrl('https://builtin.com/job/1')).toBeNull();
  });
  it('returns null for junk', () => {
    expect(domainFromUrl('not a url')).toBeNull();
    expect(domainFromUrl(null)).toBeNull();
  });
});

describe('getCompanyLogoUrl', () => {
  it('builds an unavatar URL with a clean-miss fallback', () => {
    const u = getCompanyLogoUrl('Twilio', 64);
    expect(u).toContain('unavatar.io/twilio.com');
    expect(u).toContain('fallback=false');
  });
  it('is null when no domain can be guessed', () => {
    expect(getCompanyLogoUrl('')).toBeNull();
  });
});
