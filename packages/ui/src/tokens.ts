export const colors = {
  ground: '#F6F3EC',
  step2: '#EFEBE0',
  hair: '#E4DED1',
  step4: '#CFC8B8',
  mute: 'rgba(28, 27, 23, .66)',
  soft: 'rgba(28, 27, 23, .84)',
  ink: '#1C1B17',
  paper: '#FFFFFF',
  edge: '#D9D1BF',
  sage: '#3F6B54',
  sageDark: '#345A46',
  clay: '#A6522E',
  ochre: '#8A6A1F',
  slate: '#44607A',
  wine: '#7D3B4C',
} as const;

export const radii = {
  control: '4px',
  card: '10px',
} as const;

export const fonts = {
  serif: "'Fraunces', ui-serif, Georgia, serif",
  sans: "'Atkinson Hyperlegible Next', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif",
  mono: "ui-monospace, 'SF Mono', 'Berkeley Mono', 'JetBrains Mono', Menlo, monospace",
} as const;

export type Vertical = 'career' | 'camera' | 'study' | 'lens' | 'party' | 'personal';

export interface VerticalMeta {
  hue: string;
  /* band and chip label, e.g. "On camera" */
  label: string;
  /* lowercase name used in running text and tags */
  name: string;
  /* hue class suffix shared by bands and chips */
  bandClass: string;
}

export const verticals: Record<Vertical, VerticalMeta> = {
  career: { hue: colors.sage, label: 'Career', name: 'career', bandClass: 'sage' },
  camera: { hue: colors.clay, label: 'On camera', name: 'on camera', bandClass: 'clay' },
  study: { hue: colors.ochre, label: 'Paid studies', name: 'paid studies', bandClass: 'ochre' },
  lens: { hue: colors.slate, label: 'Behind the camera', name: 'behind the camera', bandClass: 'slate' },
  party: { hue: colors.wine, label: 'Party quests', name: 'party quests', bandClass: 'wine' },
  personal: { hue: colors.soft, label: 'Personal', name: 'personal', bandClass: 'personal' },
};

export const tokens = { colors, radii, fonts, verticals } as const;
