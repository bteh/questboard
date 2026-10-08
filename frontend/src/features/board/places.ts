/* Place suggestions for the board filter. US-first, because that is where
   the board's supply is. The backend matches a typed US state (name or
   abbr) against the pre-parsed state_codes, and a city as a plain location
   substring (see backend application_service + job_finder.us_states). So a
   state pick passes the state name and a city pick passes the bare city.
   Free text still works; this list only guides. */

export interface PlaceOption {
  /** what the reader sees, e.g. "Chicago, IL" or "California" */
  label: string;
  /** what goes to the location= filter: state name, or bare city */
  value: string;
  /** small right-aligned hint, e.g. "state" */
  sub?: string;
  /** extra strings the query can match (abbreviations, nicknames) */
  aliases?: string[];
}

const STATES: PlaceOption[] = [
  ['Alabama', 'AL'], ['Alaska', 'AK'], ['Arizona', 'AZ'], ['Arkansas', 'AR'],
  ['California', 'CA'], ['Colorado', 'CO'], ['Connecticut', 'CT'], ['Delaware', 'DE'],
  ['Florida', 'FL'], ['Georgia', 'GA'], ['Hawaii', 'HI'], ['Idaho', 'ID'],
  ['Illinois', 'IL'], ['Indiana', 'IN'], ['Iowa', 'IA'], ['Kansas', 'KS'],
  ['Kentucky', 'KY'], ['Louisiana', 'LA'], ['Maine', 'ME'], ['Maryland', 'MD'],
  ['Massachusetts', 'MA'], ['Michigan', 'MI'], ['Minnesota', 'MN'], ['Mississippi', 'MS'],
  ['Missouri', 'MO'], ['Montana', 'MT'], ['Nebraska', 'NE'], ['Nevada', 'NV'],
  ['New Hampshire', 'NH'], ['New Jersey', 'NJ'], ['New Mexico', 'NM'], ['New York', 'NY'],
  ['North Carolina', 'NC'], ['North Dakota', 'ND'], ['Ohio', 'OH'], ['Oklahoma', 'OK'],
  ['Oregon', 'OR'], ['Pennsylvania', 'PA'], ['Rhode Island', 'RI'], ['South Carolina', 'SC'],
  ['South Dakota', 'SD'], ['Tennessee', 'TN'], ['Texas', 'TX'], ['Utah', 'UT'],
  ['Vermont', 'VT'], ['Virginia', 'VA'], ['Washington', 'WA'], ['West Virginia', 'WV'],
  ['Wisconsin', 'WI'], ['Wyoming', 'WY'], ['Washington, D.C.', 'DC'],
].map(([label, abbr]) => ({ label, value: label, sub: 'state', aliases: [abbr] }));

/* bare city value for a clean substring; the label carries the state so
   the reader knows which one, the alias lets "nyc" find New York */
const CITIES: PlaceOption[] = [
  ['New York', 'NY', ['NYC', 'Brooklyn', 'Manhattan']],
  ['Los Angeles', 'CA', ['LA']],
  ['Chicago', 'IL'],
  ['Houston', 'TX'],
  ['Phoenix', 'AZ'],
  ['Philadelphia', 'PA', ['Philly']],
  ['San Antonio', 'TX'],
  ['San Diego', 'CA'],
  ['Dallas', 'TX'],
  ['Austin', 'TX'],
  ['San Francisco', 'CA', ['SF', 'Bay Area']],
  ['Seattle', 'WA'],
  ['Denver', 'CO'],
  ['Boston', 'MA'],
  ['Atlanta', 'GA'],
  ['Miami', 'FL'],
  ['Portland', 'OR'],
  ['Nashville', 'TN'],
  ['Minneapolis', 'MN'],
  ['Raleigh', 'NC'],
  ['Detroit', 'MI'],
  ['Las Vegas', 'NV', ['Vegas']],
  ['Charlotte', 'NC'],
  ['Columbus', 'OH'],
  ['Pittsburgh', 'PA'],
  ['Sacramento', 'CA'],
  ['Orlando', 'FL'],
  ['Tampa', 'FL'],
].map(([city, abbr, aliases]) => ({
  label: `${city as string}, ${abbr as string}`,
  value: city as string,
  aliases: aliases as string[] | undefined,
}));

/* Areas expand to their cities on the backend (job_finder.place_areas is
   the source of truth; tests/test_place_areas.py pins this list to it).
   Their cities pass "City, CA" so the backend's whole-word + CA guard
   keeps Orange, NJ and Walnut Creek out. */
const AREAS: PlaceOption[] = [
  {
    label: 'San Gabriel Valley (626)',
    value: 'San Gabriel Valley (626)',
    sub: 'area',
    aliases: ['626', 'SGV', 'San Gabriel Valley'],
  },
  {
    label: 'North Orange County',
    value: 'North Orange County',
    sub: 'area',
    aliases: ['North OC', 'Fullerton area'],
  },
];

const AREA_CITIES: PlaceOption[] = [
  'Arcadia', 'Alhambra', 'Monterey Park', 'El Monte', 'South El Monte', 'San Gabriel',
  'Rosemead', 'Temple City', 'San Marino', 'South Pasadena', 'Pasadena', 'Monrovia',
  'Duarte', 'Azusa', 'Covina', 'West Covina', 'Baldwin Park', 'Irwindale',
  'City of Industry', 'Rowland Heights', 'Hacienda Heights', 'Walnut', 'Diamond Bar',
  'La Puente', 'Glendora', 'Sierra Madre', 'Altadena',
  'Fullerton', 'Anaheim', 'Brea', 'Buena Park', 'La Habra', 'Placentia', 'Yorba Linda',
  'Orange', 'Cypress', 'La Palma', 'Garden Grove', 'Stanton',
].map((city) => ({ label: `${city}, CA`, value: `${city}, CA` }));

export const PLACE_OPTIONS: PlaceOption[] = [...AREAS, ...CITIES, ...AREA_CITIES, ...STATES];

/** Best matches for a query: prefix hits first, then contained, capped. */
export function filterPlaces(query: string, limit = 6): PlaceOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const starts: PlaceOption[] = [];
  const contains: PlaceOption[] = [];
  for (const opt of PLACE_OPTIONS) {
    const hay = [opt.label, opt.value, ...(opt.aliases ?? [])].map((s) => s.toLowerCase());
    if (hay.some((s) => s.startsWith(q))) starts.push(opt);
    else if (hay.some((s) => s.includes(q))) contains.push(opt);
  }
  return [...starts, ...contains].slice(0, limit);
}
