import { defaultTheme, darkTheme, mergeTheme } from './theme.config'

export const DEFAULT_FAVICON = '/assets/msuite_frontend/frontend/lemnia-mark.svg'

/**
 * Maps every theme token to its CSS custom property name. Keeping this
 * as an explicit list (rather than walking the object generically)
 * means renaming a CSS var doesn't silently break — adding a new
 * token requires adding a line here, which is the point.
 */
function writeTokens(root, t) {
  // Brand
  root.style.setProperty('--brand', t.brand.color)
  root.style.setProperty('--brand-dark', t.brand.dark)
  root.style.setProperty('--brand-light', t.brand.light)
  root.style.setProperty('--brand-lighter', t.brand.lighter)

  // Rail / secondary sidebar
  root.style.setProperty('--rail-bg', t.rail.bg)
  root.style.setProperty('--rail-border', t.rail.border)
  root.style.setProperty('--rail-accent', t.rail.accent)
  root.style.setProperty('--rail-text', t.rail.text)
  root.style.setProperty('--rail-text-bright', t.rail.textBright)
  root.style.setProperty('--rail-section-label', t.rail.sectionLabel)
  root.style.setProperty('--rail-hover-bg', t.rail.hoverBg)
  root.style.setProperty('--rail-active-bg', t.rail.activeBg)
  root.style.setProperty('--rail-scrollbar', t.rail.scrollbar)
  root.style.setProperty('--rail-scrollbar-hover', t.rail.scrollbarHover)
  root.style.setProperty('--rail-secondary-bg', t.rail.secondaryBg)
  root.style.setProperty('--rail-secondary-border', t.rail.secondaryBorder)
  root.style.setProperty('--rail-secondary-text', t.rail.secondaryText)
  root.style.setProperty('--rail-secondary-section-label', t.rail.secondarySectionLabel)
  root.style.setProperty('--rail-alert', t.rail.alert)

  // Surfaces
  root.style.setProperty('--bg-page', t.surfaces.page)
  root.style.setProperty('--bg-surface', t.surfaces.surface)
  root.style.setProperty('--bg-rail', t.surfaces.rail)
  root.style.setProperty('--bg-sunken', t.surfaces.sunken)

  // Text
  root.style.setProperty('--text-primary', t.text.primary)
  root.style.setProperty('--text-secondary', t.text.secondary)
  root.style.setProperty('--text-tertiary', t.text.tertiary)
  root.style.setProperty('--text-on-brand', t.text.onBrand)

  // Borders
  root.style.setProperty('--border', t.border.base)
  root.style.setProperty('--border-soft', t.border.soft)

  // State
  root.style.setProperty('--success', t.state.success)
  root.style.setProperty('--success-bg', t.state.successBg)
  root.style.setProperty('--warning', t.state.warning)
  root.style.setProperty('--warning-bg', t.state.warningBg)
  root.style.setProperty('--danger', t.state.danger)
  root.style.setProperty('--danger-bg', t.state.dangerBg)
  root.style.setProperty('--info-bg', t.state.infoBg)

  // Composer family
  root.style.setProperty('--brand-25', t.composer.brand25)
  root.style.setProperty('--brand-50', t.composer.brand50)
  root.style.setProperty('--brand-100', t.composer.brand100)
  root.style.setProperty('--brand-200', t.composer.brand200)
  root.style.setProperty('--brand-300', t.composer.brand300)
  root.style.setProperty('--brand-400', t.composer.brand400)
  root.style.setProperty('--brand-500', t.composer.brand500)
  root.style.setProperty('--brand-600', t.composer.brand600)
  root.style.setProperty('--brand-700', t.composer.brand700)
  root.style.setProperty('--brand-800', t.composer.brand800)
  root.style.setProperty('--ink-900', t.composer.ink900)
  root.style.setProperty('--ink-850', t.composer.ink850)
  root.style.setProperty('--ink-800', t.composer.ink800)
  root.style.setProperty('--ink-700', t.composer.ink700)
  root.style.setProperty('--ink-600', t.composer.ink600)
  root.style.setProperty('--ink-500', t.composer.ink500)
  root.style.setProperty('--ink-400', t.composer.ink400)
  root.style.setProperty('--ink-300', t.composer.ink300)
  root.style.setProperty('--ink-200', t.composer.ink200)
  root.style.setProperty('--ink-100', t.composer.ink100)
  root.style.setProperty('--ink-50', t.composer.ink50)
  root.style.setProperty('--ink-25', t.composer.ink25)
  root.style.setProperty('--green-700', t.composer.green700)
  root.style.setProperty('--green-600', t.composer.green600)
  root.style.setProperty('--green-500', t.composer.green500)
  root.style.setProperty('--emerald-500', t.composer.emerald500)
  root.style.setProperty('--orange-500', t.composer.orange500)
  root.style.setProperty('--amber-700', t.composer.amber700)
  root.style.setProperty('--amber-800', t.composer.amber800)
  root.style.setProperty('--red-700', t.composer.red700)
  root.style.setProperty('--red-600', t.composer.red600)
  root.style.setProperty('--red-500', t.composer.red500)
  root.style.setProperty('--red-300', t.composer.red300)
  root.style.setProperty('--rose-500', t.composer.rose500)

  // Inbox accents
  root.style.setProperty('--inbox-bubble-in', t.inbox.bubbleIn)
  root.style.setProperty('--inbox-bubble-out', t.inbox.bubbleOut)
  root.style.setProperty('--inbox-hot', t.inbox.hot)
  root.style.setProperty('--inbox-warm', t.inbox.warm)
  root.style.setProperty('--inbox-cold', t.inbox.cold)
  root.style.setProperty('--inbox-sla-warn', t.inbox.slaWarn)

  // Lemnia accents (teal = Operations, blue = Revenue, glow = dark surfaces only)
  root.style.setProperty('--accent-teal', t.accent.teal)
  root.style.setProperty('--accent-teal-on-light', t.accent.tealOnLight)
  root.style.setProperty('--accent-blue', t.accent.blue)
  root.style.setProperty('--glow', t.accent.glow)

  // AI / Aivo dark surface
  root.style.setProperty('--ai-bg', t.ai.bg)
  root.style.setProperty('--ai-panel', t.ai.panel)
  root.style.setProperty('--ai-border', t.ai.border)
  root.style.setProperty('--ai-label', t.ai.label)
  root.style.setProperty('--ai-text', t.ai.text)
  root.style.setProperty('--ai-muted', t.ai.muted)
  root.style.setProperty('--ai-inset', t.ai.inset)

  // Record-state pill palette
  for (const tone of ['success', 'warning', 'danger', 'neutral', 'info']) {
    root.style.setProperty(`--status-${tone}-bg`, t.status[`${tone}Bg`])
    root.style.setProperty(`--status-${tone}-text`, t.status[`${tone}Text`])
    root.style.setProperty(`--status-${tone}-dot`, t.status[`${tone}Dot`])
  }
  root.style.setProperty('--border-strong', t.border.strong)

  // Typography
  const stack = fontStack(t.font)
  root.style.setProperty('--font-sans', stack)
  root.style.setProperty('--font-stack', stack)
  root.style.setProperty('--font-mono', t.font.mono)

  // Shape
  root.style.setProperty('--radius-pill', t.radius.pill)
  root.style.setProperty('--radius-sm', t.radius.sm)
  root.style.setProperty('--radius-md', t.radius.md)
  root.style.setProperty('--radius-lg', t.radius.lg)

  // Shadows
  root.style.setProperty('--shadow-sm', t.shadow.sm)
  root.style.setProperty('--shadow-md', t.shadow.md)
  root.style.setProperty('--shadow-panel', t.shadow.panel)
  root.style.setProperty('--shadow-card', t.shadow.card)

  // Motion
  root.style.setProperty('--motion-micro', t.motion.micro)
  root.style.setProperty('--motion-panel', t.motion.panel)
  root.style.setProperty('--motion-page', t.motion.page)
  root.style.setProperty('--motion-aivo', t.motion.aivo)

  // Compatibility aliases for component tokens
  root.style.setProperty('--accent', t.brand.color)
  root.style.setProperty('--brand-color', t.brand.color)
  root.style.setProperty('--surface-surface', t.surfaces.surface)
  root.style.setProperty('--surface-page', t.surfaces.page)
  root.style.setProperty('--surface-sunken', t.surfaces.sunken)
  root.style.setProperty('--surface-rail', t.surfaces.rail)
  root.style.setProperty('--border-base', t.border.base)
  root.style.setProperty('--state-success', t.state.success)
  root.style.setProperty('--state-success-bg', t.state.successBg)
  root.style.setProperty('--state-success-border', t.state.success)
  root.style.setProperty('--state-warning', t.state.warning)
  root.style.setProperty('--state-warning-bg', t.state.warningBg)
  root.style.setProperty('--state-warning-border', t.state.warning)
  root.style.setProperty('--state-danger', t.state.danger)
  root.style.setProperty('--state-danger-bg', t.state.dangerBg)
  root.style.setProperty('--state-danger-border', t.state.danger)

  // Semantic aliases that components referenced before they existed. Each
  // was previously an undefined var — either silently locked to its
  // hardcoded light-mode fallback, or (with no fallback) rendering as an
  // invalid value. Mapping them onto real tokens is what makes those
  // components follow light/dark.
  root.style.setProperty('--text-muted', t.text.tertiary)
  root.style.setProperty('--bg-hover', t.surfaces.sunken)
  root.style.setProperty('--surface-bg', t.surfaces.page)
  root.style.setProperty('--surface-gray-1', t.surfaces.sunken)
  root.style.setProperty('--surface-surface-dark', t.surfaces.sunken)
  root.style.setProperty('--border-color', t.border.base)
  root.style.setProperty('--border-medium', t.border.base)
  root.style.setProperty('--border-dark', t.composer.ink300)
  root.style.setProperty('--danger-border', t.state.danger)
  root.style.setProperty('--primary', t.brand.color)
  root.style.setProperty('--gray-50', t.composer.ink50)
  root.style.setProperty('--gray-200', t.composer.ink200)
  root.style.setProperty('--gray-600', t.composer.ink600)
  root.style.setProperty('--slate-500', t.composer.ink500)
  root.style.setProperty('--shadow-lg', t.shadow.panel)
}

const FALLBACK_STACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

function fontStack(font) {
  const fam = (font?.family || '').trim()
  if (!fam) return FALLBACK_STACK
  return `"${fam.replace(/"/g, '')}", ${FALLBACK_STACK}`
}

/**
 * Load the configured font. Google-hosted families are injected as one
 * <link id="msuite-theme-font">; swapping family replaces the same node, so
 * switching fonts in Settings previews instantly and never leaks stylesheets.
 */
function loadFont(font) {
  if (typeof document === 'undefined') return
  const id = 'msuite-theme-font'
  let link = document.getElementById(id)
  const fam = (font?.family || '').trim()
  if (!font?.googleFont || !fam) {
    if (link) link.remove()
    return
  }
  const weights = String(font.weights || '400;500;600;700').replace(/[^0-9;]/g, '')
  const href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fam).replace(/%20/g, '+')}:wght@${weights}&display=swap`
  if (!link) {
    link = document.createElement('link')
    link.id = id
    link.rel = 'stylesheet'
    document.head.appendChild(link)
  }
  if (link.getAttribute('href') !== href) link.setAttribute('href', href)
}

/** Point the tab icon at the configured favicon (falls back to the bundled one). */
function applyFavicon(assets) {
  if (typeof document === 'undefined') return
  const href = assets?.favicon || DEFAULT_FAVICON
  let fav = document.querySelector("link[rel~='icon']")
  if (!fav) {
    fav = document.createElement('link')
    fav.rel = 'icon'
    document.head.appendChild(fav)
  }
  fav.type = href.endsWith('.png') ? 'image/png' : 'image/svg+xml'
  if (fav.getAttribute('href') !== href) fav.setAttribute('href', href)
}

/**
 * Apply a (possibly partial) theme to `document.documentElement`.
 * Missing keys fall back to `defaultTheme`/`darkTheme` via deep merge,
 * so a tenant config that only sets `{ brand: { color: '#E63946' } }`
 * is safe in either mode.
 *
 * `mode` selects the base palette ('light' | 'dark') — it must already
 * be resolved (never 'system') by the time it reaches here. Stamps
 * `data-theme` on `<html>` so any handwritten CSS can also branch off
 * it if a component ever needs more than `var(--token)`.
 *
 * Returns the merged theme object so callers can also use it as plain
 * JS tokens (e.g. for canvas/chart colours that can't read CSS vars).
 */
export function applyTheme(overrides = {}, mode = 'light') {
  const base = mode === 'dark' ? darkTheme : defaultTheme
  const merged = mergeTheme(base, overrides)
  if (typeof document !== 'undefined') {
    writeTokens(document.documentElement, merged)
    loadFont(merged.font)
    applyFavicon(merged.assets)
    document.documentElement.setAttribute('data-theme', mode === 'dark' ? 'dark' : 'light')
  }
  return merged
}
