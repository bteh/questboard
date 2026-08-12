/**
 * Maps known company names (lowercase) to their domains.
 * Used to fetch real company logos from favicon/logo APIs.
 */
const KNOWN_DOMAINS: Record<string, string> = {
  // FAANG+
  google: 'google.com',
  alphabet: 'google.com',
  meta: 'meta.com',
  facebook: 'meta.com',
  apple: 'apple.com',
  amazon: 'amazon.com',
  netflix: 'netflix.com',
  microsoft: 'microsoft.com',
  nvidia: 'nvidia.com',
  // Big tech
  airbnb: 'airbnb.com',
  stripe: 'stripe.com',
  uber: 'uber.com',
  lyft: 'lyft.com',
  salesforce: 'salesforce.com',
  adobe: 'adobe.com',
  twitter: 'x.com',
  x: 'x.com',
  linkedin: 'linkedin.com',
  pinterest: 'pinterest.com',
  snap: 'snap.com',
  snapchat: 'snap.com',
  spotify: 'spotify.com',
  slack: 'slack.com',
  dropbox: 'dropbox.com',
  shopify: 'shopify.com',
  square: 'squareup.com',
  block: 'block.xyz',
  paypal: 'paypal.com',
  intuit: 'intuit.com',
  oracle: 'oracle.com',
  ibm: 'ibm.com',
  cisco: 'cisco.com',
  vmware: 'vmware.com',
  dell: 'dell.com',
  hp: 'hp.com',
  intel: 'intel.com',
  amd: 'amd.com',
  qualcomm: 'qualcomm.com',
  broadcom: 'broadcom.com',
  palantir: 'palantir.com',
  snowflake: 'snowflake.com',
  databricks: 'databricks.com',
  confluent: 'confluent.io',
  hashicorp: 'hashicorp.com',
  elastic: 'elastic.co',
  mongodb: 'mongodb.com',
  redis: 'redis.com',
  twilio: 'twilio.com',
  cloudflare: 'cloudflare.com',
  datadog: 'datadoghq.com',
  splunk: 'splunk.com',
  okta: 'okta.com',
  crowdstrike: 'crowdstrike.com',
  'palo alto networks': 'paloaltonetworks.com',
  zscaler: 'zscaler.com',
  fortinet: 'fortinet.com',
  servicenow: 'servicenow.com',
  workday: 'workday.com',
  zoom: 'zoom.us',
  docusign: 'docusign.com',
  atlassian: 'atlassian.com',
  github: 'github.com',
  gitlab: 'gitlab.com',
  figma: 'figma.com',
  notion: 'notion.so',
  vercel: 'vercel.com',
  netlify: 'netlify.com',
  supabase: 'supabase.com',
  planetscale: 'planetscale.com',
  neon: 'neon.tech',
  // Data / AI / ML
  openai: 'openai.com',
  anthropic: 'anthropic.com',
  cohere: 'cohere.com',
  'hugging face': 'huggingface.co',
  huggingface: 'huggingface.co',
  scale: 'scale.com',
  'scale ai': 'scale.com',
  weights: 'wandb.ai',
  'weights & biases': 'wandb.ai',
  dbt: 'getdbt.com',
  'dbt labs': 'getdbt.com',
  fivetran: 'fivetran.com',
  starburst: 'starburst.io',
  trino: 'trino.io',
  airbyte: 'airbyte.com',
  prefect: 'prefect.io',
  dagster: 'dagster.io',
  materialize: 'materialize.com',
  clickhouse: 'clickhouse.com',
  motherduck: 'motherduck.com',
  // Fintech
  robinhood: 'robinhood.com',
  coinbase: 'coinbase.com',
  plaid: 'plaid.com',
  chime: 'chime.com',
  sofi: 'sofi.com',
  brex: 'brex.com',
  ramp: 'ramp.com',
  mercury: 'mercury.com',
  'ally financial': 'ally.com',
  ally: 'ally.com',
  sezzle: 'sezzle.com',
  affirm: 'affirm.com',
  klarna: 'klarna.com',
  // Other notable
  doordash: 'doordash.com',
  instacart: 'instacart.com',
  grubhub: 'grubhub.com',
  reddit: 'reddit.com',
  discord: 'discord.com',
  roblox: 'roblox.com',
  epic: 'epicgames.com',
  'epic games': 'epicgames.com',
  valve: 'valvesoftware.com',
  unity: 'unity.com',
  tesla: 'tesla.com',
  spacex: 'spacex.com',
  rivian: 'rivian.com',
  waymo: 'waymo.com',
  cruise: 'getcruise.com',
  nuro: 'nuro.ai',
  anduril: 'anduril.com',
  'shield ai': 'shield.ai',
  flexport: 'flexport.com',
  rippling: 'rippling.com',
  gusto: 'gusto.com',
  lattice: 'lattice.com',
  linear: 'linear.app',
  retool: 'retool.com',
  airtable: 'airtable.com',
  asana: 'asana.com',
  monday: 'monday.com',
  'monday.com': 'monday.com',
  deel: 'deel.com',
  remote: 'remote.com',
  // Workday employer additions
  'motorola solutions': 'motorolasolutions.com',
  motorola: 'motorolasolutions.com',
  'thomson reuters': 'thomsonreuters.com',
  'fis global': 'fis.com',
  fis: 'fis.com',
  moderna: 'modernatx.com',
  // Healthcare / Biotech
  tempus: 'tempus.com',
  veracyte: 'veracyte.com',
  akido: 'akidolabs.com',
  // Media
  'new york times': 'nytimes.com',
  nyt: 'nytimes.com',
  bloomberg: 'bloomberg.com',
  reuters: 'reuters.com',
  'the athletic': 'theathletic.com',
  spokeo: 'spokeo.com',
  // Gaming
  'riot games': 'riotgames.com',
  riot: 'riotgames.com',
  activision: 'activision.com',
  'activision blizzard': 'activisionblizzard.com',
  blizzard: 'blizzard.com',
  ea: 'ea.com',
  'electronic arts': 'ea.com',
  niantic: 'nianticlabs.com',
  zynga: 'zynga.com',
  // Defense / Aerospace
  'northrop grumman': 'northropgrumman.com',
  lockheed: 'lockheedmartin.com',
  'lockheed martin': 'lockheedmartin.com',
  raytheon: 'rtx.com',
  boeing: 'boeing.com',
  // E-commerce / Marketplace
  stubhub: 'stubhub.com',
  etsy: 'etsy.com',
  ebay: 'ebay.com',
  wish: 'wish.com',
  poshmark: 'poshmark.com',
  // SaaS / Cloud
  segment: 'segment.com',
  amplitude: 'amplitude.com',
  mixpanel: 'mixpanel.com',
  launchdarkly: 'launchdarkly.com',
  postman: 'postman.com',
  'new relic': 'newrelic.com',
  grafana: 'grafana.com',
  sentry: 'sentry.io',
  // Ad tech / Marketing
  'the trade desk': 'thetradedesk.com',
  trade: 'thetradedesk.com',
  stackadapt: 'stackadapt.com',
  criteo: 'criteo.com',
  applovin: 'applovin.com',
  // Travel / Hospitality
  booking: 'booking.com',
  'booking.com': 'booking.com',
  expedia: 'expedia.com',
  tripadvisor: 'tripadvisor.com',
  zillow: 'zillow.com',
  redfin: 'redfin.com',
  compass: 'compass.com',
  // Consulting / Professional
  mckinsey: 'mckinsey.com',
  bain: 'bain.com',
  bcg: 'bcg.com',
  deloitte: 'deloitte.com',
  accenture: 'accenture.com',
  // Other notable
  mastercard: 'mastercard.com',
  visa: 'visa.com',
  'american express': 'americanexpress.com',
  amex: 'americanexpress.com',
  walmart: 'walmart.com',
  target: 'target.com',
  samsung: 'samsung.com',
  tiktok: 'tiktok.com',
  bytedance: 'bytedance.com',
};

/** Hosts that are job boards / ATS, not the employer's own site. A job_url on
 * one of these tells us nothing about the company's real domain, so we ignore
 * it and fall back to name-based guessing. */
const AGGREGATOR_HOSTS = [
  'greenhouse.io', 'lever.co', 'ashbyhq.com', 'workday.com', 'myworkdayjobs.com',
  'builtin.com', 'indeed.com', 'linkedin.com', 'remotive.com', 'himalayas.app',
  'weworkremotely.com', 'ycombinator.com', 'workatastartup.com', 'remoteok.com',
  'remoteok.io', 'cryptojobslist.com', 'web3.career', 'wellfound.com', 'angel.co', 'getro.com',
  'consider.com', 'themuse.com', 'arbeitnow.com', 'jobs.gem.com', 'smartrecruiters.com',
  'bamboohr.com', 'workable.com', 'jobvite.com', 'icims.com', 'taleo.net',
  'google.com', 'bing.com', 'ziprecruiter.com', 'glassdoor.com', 'dice.com',
];

/** Pull a real employer domain out of a job posting URL, or null if the URL
 * only points at an aggregator/ATS. */
export function domainFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const host = new URL(url).hostname.toLowerCase()
      .replace(/^(www|jobs|job|boards|board|apply|careers|career|hire|hiring)\./, '');
    if (!host.includes('.')) return null;
    // registrable-ish domain = last two labels (good enough for logo lookup)
    const parts = host.split('.');
    const registrable = parts.slice(-2).join('.');
    if (AGGREGATOR_HOSTS.some((h) => host === h || host.endsWith('.' + h) || registrable === h)) {
      return null;
    }
    return host;
  } catch {
    return null;
  }
}

/** True when a company name is already written as a domain, e.g. "IPinfo.io",
 * "monday.com", "booking.com". */
function nameLooksLikeDomain(lower: string): string | null {
  const compact = lower.replace(/\s+/g, '');
  if (/^[a-z0-9][a-z0-9-]*\.[a-z]{2,}$/.test(compact)) return compact;
  return null;
}

/**
 * Guess a company's domain from its name (and the posting URL when it points at
 * the employer's own site). Exact map, then domain-shaped names, then the URL,
 * then a slug heuristic. A wrong guess just 404s and falls back to a letter, so
 * over-guessing is safe.
 */
export function getCompanyDomain(companyName: string, url?: string | null): string | null {
  const lower = (companyName || '').toLowerCase().trim();

  // 1. Exact lookup
  if (lower && KNOWN_DOMAINS[lower]) return KNOWN_DOMAINS[lower];

  // 2. The name is already a domain ("IPinfo.io")
  const asDomain = lower ? nameLooksLikeDomain(lower) : null;
  if (asDomain) return asDomain;

  // 3. Strip common suffixes, retry the map
  const cleaned = lower
    .replace(/,?\s*(inc\.?|corp\.?|corporation|llc|ltd\.?|co\.?|group|holdings|technologies|technology|labs|studio|studios|global)$/i, '')
    .trim();
  if (cleaned && KNOWN_DOMAINS[cleaned]) return KNOWN_DOMAINS[cleaned];

  // 4. A real employer domain from the posting URL (skips ATS/aggregator hosts)
  const fromUrl = domainFromUrl(url);
  if (fromUrl) return fromUrl;

  // 5. Heuristic: slugify the name to a .com
  const slug = cleaned.replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, '').trim();
  if (slug.length >= 2 && slug.length <= 30) return `${slug}.com`;

  return null;
}

/**
 * Primary logo URL. unavatar aggregates real company logos (Clearbit, favicon,
 * Twitter, ...) and, with fallback=false, returns a clean error on a miss so the
 * avatar falls through to a colored letter instead of a generic globe.
 */
export function getCompanyLogoUrl(companyName: string, size = 128, url?: string | null): string | null {
  const domain = getCompanyDomain(companyName, url);
  if (!domain) return null;
  // DuckDuckGo's icon service returns the company's real favicon with no rate
  // limit or API key. We switched off unavatar.io because its free anonymous
  // tier now hard-rate-limits (429), so real logos stopped loading and every
  // card fell back to the monogram. `size` is unused here (DDG serves a fixed
  // icon); the caller still renders the colored-initial monogram on a network
  // error via the <img> onError handler.
  void size;
  return `https://icons.duckduckgo.com/ip3/${domain}.ico`;
}
