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
  'shield ai': 'shield.ai',
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
  twilio: 'twilio.com',
  segment: 'segment.com',
  amplitude: 'amplitude.com',
  mixpanel: 'mixpanel.com',
  launchdarkly: 'launchdarkly.com',
  postman: 'postman.com',
  'new relic': 'newrelic.com',
  grafana: 'grafana.com',
  sentry: 'sentry.io',
  vercel: 'vercel.com',
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

/**
 * Guess a company's domain from its name.
 * Tries exact match, lowercase match, then heuristic domain generation.
 */
export function getCompanyDomain(companyName: string): string | null {
  if (!companyName) return null;
  const lower = companyName.toLowerCase().trim();

  // 1. Exact lookup
  if (KNOWN_DOMAINS[lower]) return KNOWN_DOMAINS[lower];

  // 2. Try without common suffixes: "Inc.", "Corp", "LLC", "Ltd", "Co."
  const cleaned = lower
    .replace(/,?\s*(inc\.?|corp\.?|llc|ltd\.?|co\.?|group|holdings|technologies|technology|labs|studio|studios)$/i, '')
    .trim();
  if (KNOWN_DOMAINS[cleaned]) return KNOWN_DOMAINS[cleaned];

  // 3. Heuristic: slugify name to domain
  const slug = cleaned
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, '')
    .trim();
  if (slug.length >= 2 && slug.length <= 30) {
    return `${slug}.com`;
  }

  return null;
}

/**
 * Get a logo URL for a company. Returns null if no domain can be determined.
 * Uses img.logo.dev for high-quality logos with Google Favicon as built-in fallback.
 */
export function getCompanyLogoUrl(companyName: string, size = 128): string | null {
  const domain = getCompanyDomain(companyName);
  if (!domain) return null;
  // logo.dev provides high-quality company logos; fallback to Google Favicon in CompanyAvatar onError
  return `https://img.logo.dev/${domain}?token=pk_a8V7kXYGRZqIlWfB06kPJA&size=${size}&format=png`;
}

/**
 * Fallback logo URL using Google Favicon API.
 */
export function getCompanyLogoFallbackUrl(companyName: string, size = 128): string | null {
  const domain = getCompanyDomain(companyName);
  if (!domain) return null;
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=${size}`;
}
