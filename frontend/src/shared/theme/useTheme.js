import { readonly, ref, computed } from 'vue'
import { defaultTheme } from './theme.config'
import { applyTheme } from './applyTheme'

const MODE_KEY = 'msuite_theme_mode'
const MODES = ['light', 'dark', 'system']

// Singleton — the currently active, merged theme. Components that need
// JS-level colour tokens (charts, canvas, inline style bindings) read
// this; everything else should just use `var(--token)` in CSS.
const activeTheme = ref(defaultTheme)

// User's chosen mode (persisted); 'system' tracks the OS preference.
const themeMode = ref('system')

let activeOverrides = {}
let systemQuery = null

function resolveEffectiveMode(mode) {
  if (mode !== 'system') return mode
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// The mode actually in force ('light' | 'dark') — 'system' already resolved.
const resolvedMode = ref('light')

function applyCurrent() {
  resolvedMode.value = resolveEffectiveMode(themeMode.value)
  activeTheme.value = applyTheme(activeOverrides, resolvedMode.value)
}

function watchSystemPreference() {
  if (typeof window === 'undefined' || !window.matchMedia) return
  if (systemQuery) return
  systemQuery = window.matchMedia('(prefers-color-scheme: dark)')
  systemQuery.addEventListener('change', () => {
    if (themeMode.value === 'system') applyCurrent()
  })
}

/**
 * Fetch the tenant's theme from the backend and apply it. Falls back
 * to `defaultTheme` silently if no override exists or the request
 * fails — branding must never block boot. Also restores the user's
 * saved light/dark/system preference (defaulting to 'system').
 */
export async function bootTheme(fetcher) {
  try {
    activeOverrides = (await fetcher?.()) || {}
  } catch (e) {
    console.warn('[msuite] theme fetch failed, using default theme:', e)
    activeOverrides = {}
  }

  try {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(MODE_KEY) : null
    themeMode.value = MODES.includes(saved) ? saved : 'system'
  } catch {
    themeMode.value = 'system'
  }

  watchSystemPreference()
  applyCurrent()
  return activeTheme.value
}

/** Re-apply a theme at runtime (e.g. from the Theme & Branding settings page). */
export function setTheme(overrides) {
  activeOverrides = overrides || {}
  applyCurrent()
  return activeTheme.value
}

/** Switch light/dark/system mode and persist the choice. */
export function setThemeMode(mode) {
  if (!MODES.includes(mode)) return activeTheme.value
  themeMode.value = mode
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    // Storage unavailable (private browsing, quota) — mode still applies for this session.
  }
  applyCurrent()
  return activeTheme.value
}

export function useTheme() {
  return readonly(activeTheme)
}

/** Readonly ref of the user's chosen mode: 'light' | 'dark' | 'system'. */
export function useThemeMode() {
  return readonly(themeMode)
}

/** Readonly ref of the mode in force right now: 'light' | 'dark'. */
export function useResolvedMode() {
  return computed(() => resolvedMode.value)
}
