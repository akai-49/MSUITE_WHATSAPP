/**
 * theme.config.js — single source of truth for every colour in the app.
 *
 * `defaultTheme` is the out-of-the-box MSuite palette. A business/tenant
 * can override any subset of these keys (typically just `brand` and
 * `rail`) via a config fetched from the backend — see `applyTheme.js`.
 *
 * Every value here ends up as a CSS custom property on `:root`
 * (see TOKEN_MAP in applyTheme.js). Components must reference colours
 * via `var(--token-name)`, never as literal hex values.
 */

export const defaultTheme = {
  // ── Brand ────────────────────────────────────────────────────────────
  brand: {
    color: '#0B192C', // Midnight Navy — primary actions, active states, links
    dark: '#060F1D',
    light: '#E2E8F0', // Brushed Platinum — chip / badge tint
    lighter: '#F1F4F8',
  },

  // ── Accents (Lemnia: Operations teal · Revenue blue · glow) ──────────
  // `glow` is for dark surfaces ONLY (rail, AI panels, loader on navy).
  accent: {
    teal: '#12907F',
    tealOnLight: '#0E7A6C',
    blue: '#34419C',
    glow: '#2DC8B6',
  },

  // ── AI / Aivo dark surface ───────────────────────────────────────────
  ai: {
    bg: '#0B192C',
    panel: '#11233F',
    border: '#213450',
    label: '#2DC8B6',
    text: '#C6D2DE',
    muted: '#6E83A8',
    inset: 'rgba(255,255,255,0.045)',
  },

  // ── Record-state pills (green=go, amber=hold, red=stop, grey=idle, blue=info)
  // Separate from the brand accents above — state pills ONLY.
  status: {
    successBg: '#DCFCE7', successText: '#15803D', successDot: '#22C55E',
    warningBg: '#FEF3C7', warningText: '#92400E', warningDot: '#F59E0B',
    dangerBg: '#FEE4E2', dangerText: '#B42318', dangerDot: '#EF4444',
    neutralBg: '#F1F5F9', neutralText: '#475569', neutralDot: '#94A3B8',
    infoBg: '#DBEAFE', infoText: '#1D4ED8', infoDot: '#3B82F6',
  },

  // ── Typography ───────────────────────────────────────────────────────
  // `family` is a Google Fonts family name (or any installed font). When
  // `googleFont` is true the stylesheet is injected at runtime.
  font: {
    family: 'Hanken Grotesk',
    googleFont: true,
    weights: '300;400;500;600;700',
    mono: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  },

  // ── Brand assets (empty string = the bundled Lemnia default) ─────────
  assets: {
    name: 'lemnia', // product wordmark shown beside the mark
    logo: '', // horizontal lockup (light & dark bg variants auto-picked when empty)
    mark: '', // square mark / rail icon
    favicon: '',
    aivoBase: '', // folder URL containing aivo-bust.svg, aivo-idle.svg … (optional override)
    showAivo: true, // false hides every mascot (a plain glyph is shown instead)
  },

  // ── Loader ───────────────────────────────────────────────────────────
  // style: 'mark' (animated lemnia mark) | 'dots' | 'ring'
  loader: {
    style: 'mark',
    label: '',
  },

  // ── Primary rail + secondary sidebar (dark nav) ─────────────────────
  rail: {
    bg: '#0B192C',
    border: '#060F1D',
    accent: '#E2E8F0',
    text: '#9FB0CC',
    textBright: '#E6ECF5',
    sectionLabel: '#5E739A',
    hoverBg: 'rgba(255,255,255,0.06)',
    activeBg: 'rgba(226,232,240,0.14)',
    scrollbar: '#2A3F62',
    scrollbarHover: '#38507F',
    secondaryBg: '#11233F',
    secondaryBorder: '#213450',
    secondaryText: '#9FB0CC',
    secondarySectionLabel: '#5E739A',
    alert: '#E5484D',
  },

  // ── Surfaces ─────────────────────────────────────────────────────────
  surfaces: {
    page: '#EDF1F6',
    surface: '#FFFFFF',
    rail: '#FFFFFF',
    sunken: '#E2E8F0',
  },

  // ── Typography ───────────────────────────────────────────────────────
  text: {
    primary: '#15181D',
    secondary: '#5B6270',
    tertiary: '#5F6673',
    onBrand: '#FFFFFF',
  },

  // ── Borders ──────────────────────────────────────────────────────────
  border: {
    base: '#E1E4EA',
    soft: '#EFF0F3',
    strong: '#C7CDD6',
  },

  // ── State colours ────────────────────────────────────────────────────
  state: {
    success: '#12907F', // brand teal (accent for numbers/deltas) — NOT a status pill
    successBg: '#E7F4F1',
    warning: '#B4541E',
    warningBg: '#F8EADF',
    danger: '#C4291F',
    dangerBg: '#FCEAE9',
    infoBg: '#EAECF6',
  },

  // ── Composer family tokens (Ad/Social/Campaign composers) ───────────
  composer: {
    brand25: 'rgba(52,65,156,0.03)',
    brand200: 'rgba(52,65,156,0.24)',
    brand300: '#8F99D4',
    brand400: '#5F6BBE',
    brand500: '#34419C',
    brand600: '#2C378A',
    brand700: '#242E75',
    brand800: '#1C245E',
    brand50: 'rgba(52,65,156,0.06)',
    brand100: 'rgba(52,65,156,0.12)',
    ink900: '#0B192C',
    ink850: '#14233A',
    ink800: '#1E2D44',
    ink700: '#334155',
    ink600: '#475569',
    ink500: '#64748B',
    ink400: '#94A3B8',
    ink300: '#94A3B8',
    ink200: '#CBD5E1',
    ink100: '#E2E8F0',
    ink50: '#F1F5F9',
    ink25: '#F8FAFC',
    green700: '#0E7A6C',
    green600: '#12907F',
    green500: '#2DC8B6',
    emerald500: '#12907F',
    orange500: '#F59E0B',
    amber700: '#B4541E',
    amber800: '#8A3F14',
    red700: '#B91C1C',
    red600: '#DC2626',
    red500: '#DC2626',
    red300: '#FCA5A5',
    rose500: '#F43F5E',
  },

  // ── Inbox-specific accents ───────────────────────────────────────────
  inbox: {
    bubbleIn: '#F3F4F6',
    bubbleOut: '#DCFCE7',
    hot: '#12907F',
    warm: '#F59E0B',
    cold: '#EF4444',
    slaWarn: '#F97316',
  },

  // ── Shape ────────────────────────────────────────────────────────────
  radius: {
    sm: '6px',
    md: '10px',
    lg: '16px',
    pill: '999px',
  },

  // ── Motion ───────────────────────────────────────────────────────────
  motion: {
    micro: '150ms ease-out',
    panel: '300ms cubic-bezier(0.22,1,0.36,1)',
    page: '200ms ease',
    aivo: '450ms cubic-bezier(0.22,1,0.36,1)',
  },

  // ── Shadows ──────────────────────────────────────────────────────────
  shadow: {
    sm: '0 1px 2px rgba(20,30,50,0.04)',
    md: '0 4px 16px rgba(20,30,50,0.06)',
    panel: '6px 0 24px rgba(20,30,50,0.10)',
    card: '0 1px 2px rgba(0,0,0,0.02), 0 4px 16px rgba(0,0,0,0.04)',
  },
}

/**
 * darkTheme — same key shape as `defaultTheme` so every existing
 * consumer (component CSS reading `var(--token)`) keeps working
 * unchanged. Dark gray surfaces, not an inversion of the light palette.
 */
export const darkTheme = {
  brand: {
    color: '#4A57B5', // navy is invisible on dark surfaces — lift to the Lemnia blue so white-on-brand stays AA
    dark: '#3C489E',
    light: 'rgba(143,153,212,0.16)',
    lighter: 'rgba(143,153,212,0.08)',
  },

  accent: {
    teal: '#2DC8B6',
    tealOnLight: '#2DC8B6',
    blue: '#8F99D4',
    glow: '#2DC8B6',
  },

  ai: {
    bg: '#0B192C',
    panel: '#11233F',
    border: '#213450',
    label: '#2DC8B6',
    text: '#C6D2DE',
    muted: '#6E83A8',
    inset: 'rgba(255,255,255,0.045)',
  },

  status: {
    successBg: 'rgba(34,197,94,0.16)', successText: '#86EFAC', successDot: '#4ADE80',
    warningBg: 'rgba(245,158,11,0.16)', warningText: '#FCD34D', warningDot: '#FBBF24',
    dangerBg: 'rgba(239,68,68,0.16)', dangerText: '#FCA5A5', dangerDot: '#F87171',
    neutralBg: 'rgba(148,163,184,0.16)', neutralText: '#CBD5E1', neutralDot: '#94A3B8',
    infoBg: 'rgba(59,130,246,0.18)', infoText: '#93C5FD', infoDot: '#60A5FA',
  },

  rail: {
    bg: '#08121F',
    border: '#050A12',
    accent: '#E2E8F0',
    text: '#93A2C7',
    textBright: '#E2E8F5',
    sectionLabel: '#5C6D96',
    hoverBg: 'rgba(255,255,255,0.08)',
    activeBg: 'rgba(226,232,240,0.14)',
    scrollbar: '#2A3550',
    scrollbarHover: '#3A4870',
    secondaryBg: '#0D1B30',
    secondaryBorder: '#1A2A44',
    secondaryText: '#8592B8',
    secondarySectionLabel: '#4E5F8C',
    alert: '#F0555A',
  },

  surfaces: {
    page: '#0A111C',
    surface: '#111B2B',
    rail: '#08121F',
    sunken: '#16233A',
  },

  text: {
    primary: '#E6E8EC',
    secondary: '#A0A6B3',
    tertiary: '#94A3B8',
    onBrand: '#FFFFFF',
  },

  border: {
    base: '#233249',
    soft: '#1B2739',
    strong: '#32455F',
  },

  state: {
    success: '#2DC8B6',
    successBg: 'rgba(45,200,182,0.14)',
    warning: '#F59A5B',
    warningBg: 'rgba(245,154,91,0.14)',
    danger: '#F26A6A',
    dangerBg: 'rgba(242,106,106,0.12)',
    infoBg: 'rgba(143,153,212,0.14)',
  },

  composer: {
    brand25: 'rgba(143,153,212,0.04)',
    brand200: 'rgba(143,153,212,0.28)',
    brand300: '#5F6BBE',
    brand400: '#7A86CB',
    brand500: '#8F99D4',
    brand600: '#7A86CB',
    brand700: '#B1B8E3',
    brand800: '#CFD3EE',
    brand50: 'rgba(143,153,212,0.08)',
    brand100: 'rgba(143,153,212,0.16)',
    ink900: '#F1F5F9',
    ink850: '#E2E8F0',
    ink800: '#DDE4ED',
    ink700: '#CBD5E1',
    ink600: '#AFBACB',
    ink500: '#94A3B8',
    ink400: '#7C8AA0',
    ink300: '#64748B',
    ink200: '#475569',
    ink100: '#334155',
    ink50: '#1E293B',
    ink25: '#161F30',
    green700: '#4ADE80',
    green600: '#34D399',
    green500: '#22C55E',
    emerald500: '#34D399',
    orange500: '#FBBF24',
    amber700: '#FCD34D',
    amber800: '#FDE68A',
    red700: '#F87171',
    red600: '#F87171',
    red500: '#EF4444',
    red300: '#7F1D1D',
    rose500: '#FB7185',
  },

  inbox: {
    bubbleIn: '#242A35',
    bubbleOut: '#183C2C',
    hot: '#34D399',
    warm: '#FBBF24',
    cold: '#F87171',
    slaWarn: '#FB923C',
  },

  radius: {
    sm: '6px',
    md: '10px',
    lg: '16px',
    pill: '999px',
  },

  motion: {
    micro: '150ms ease-out',
    panel: '300ms cubic-bezier(0.22,1,0.36,1)',
    page: '200ms ease',
    aivo: '450ms cubic-bezier(0.22,1,0.36,1)',
  },

  shadow: {
    sm: '0 1px 2px rgba(0,0,0,0.3)',
    md: '0 4px 16px rgba(0,0,0,0.35)',
    panel: '6px 0 24px rgba(0,0,0,0.45)',
    card: '0 1px 2px rgba(0,0,0,0.25), 0 4px 16px rgba(0,0,0,0.3)',
  },
}

// Fonts, assets and loader are not light/dark specific — share one definition.
darkTheme.font = defaultTheme.font
darkTheme.assets = defaultTheme.assets
darkTheme.loader = defaultTheme.loader

/**
 * Deep merge helper — only plain objects, not arrays. Lets a tenant
 * override e.g. just `theme.brand.color` without restating the rest.
 */
export function mergeTheme(base, overrides) {
  const out = { ...base }
  for (const [key, value] of Object.entries(overrides || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value) && typeof base[key] === 'object') {
      out[key] = mergeTheme(base[key], value)
    } else {
      out[key] = value
    }
  }
  return out
}

/**
 * Inverse of mergeTheme — the minimal override object that, merged onto `base`,
 * reproduces `draft`. Settings saves this (not the full palette) so a tenant only
 * stores what they actually changed, and defaults can still evolve underneath.
 */
export function diffTheme(base, draft) {
  const out = {}
  for (const [key, value] of Object.entries(draft || {})) {
    const b = base?.[key]
    if (value && typeof value === 'object' && !Array.isArray(value) && b && typeof b === 'object') {
      const d = diffTheme(b, value)
      if (Object.keys(d).length) out[key] = d
    } else if (value !== b) {
      out[key] = value
    }
  }
  return out
}
