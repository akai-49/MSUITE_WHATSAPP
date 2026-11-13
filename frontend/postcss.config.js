import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

// The panel's CSS loads on Frappe CRM's own page, so the Lemnia stylesheet must not restyle CRM:
//  • rules for the whole page (`html`, `body`, `#app`) are dropped;
//  • rules that use a class name CRM or its frappe-ui also uses apply only inside the panel root;
//  • Lemnia's new values for frappe-ui's own tokens (`--gray-50`, `--radius-sm` …) are dropped,
//    so the panel uses Frappe CRM's. src/crm/crm-theme.css then maps Lemnia's own tokens
//    (`--bg-page`, `--brand` …) onto frappe-ui's, so the screens look like Frappe CRM.
const PAGE_SELECTOR = /^(html|body|#app)$/
const PANEL_ROOT = '.msuite-wa'
const SHARED_CLASSES = [
  'active', 'alert', 'animate-spin', 'btn', 'collapsed', 'content', 'dot',
  'form-textarea', 'full-width', 'main', 'rail', 'rail-item', 'rotated',
]
const SHARED_CLASS = new RegExp(`\\.(${SHARED_CLASSES.join('|')})(?![\\w-])`)
const THEME_SELECTOR = /^(\[data-theme=[^\]]+\]\s*)?(.*)$/s
const TOKEN_SCOPES = [':root', "[data-theme='dark']", '[data-theme=dark]', "[data-theme='light']"]
// frappe-ui token names, and the few CRM's own stylesheet sets.
const FRAPPE_TOKEN = new RegExp(
  '^--(' +
    [
      '(dark-)?(gray|red|green|orange|amber|yellow|blue|teal|cyan|purple|violet|pink)-\\d+',
      '(surface|ink|outline)-.+',
      'radius-.+',
      '(success|warning|info|error)-bg',
    ].join('|') +
    ')$',
)

function isFromLemniaCss(node) {
  return /lemnia\.css$/.test(node.source?.input?.file || '')
}

function inPanel(selector) {
  if (selector.startsWith(PANEL_ROOT)) return selector
  // `[data-theme='dark']` sits on <html>, above the panel root.
  const [, theme = '', rest] = selector.match(THEME_SELECTOR)
  return rest ? `${theme}${PANEL_ROOT} ${rest}` : `${theme}${PANEL_ROOT}`
}

function dropFrappeTokens(rule) {
  rule.nodes
    .filter((node) => node.type === 'decl' && FRAPPE_TOKEN.test(node.prop))
    .forEach((decl) => decl.remove())
  if (!rule.nodes.length) rule.remove()
}

function scopeForCrm() {
  return {
    postcssPlugin: 'scope-for-crm',
    Rule(rule) {
      if (rule.parent?.type === 'atrule' && /keyframes$/.test(rule.parent.name)) return
      const kept = rule.selectors.filter((selector) => !PAGE_SELECTOR.test(selector.trim()))
      if (!kept.length) {
        rule.remove()
        return
      }
      if (isFromLemniaCss(rule) && kept.every((selector) => TOKEN_SCOPES.includes(selector.trim()))) {
        dropFrappeTokens(rule)
        return
      }
      const scoped = kept.map((selector) => (SHARED_CLASS.test(selector) ? inPanel(selector) : selector))
      if (scoped.join() !== rule.selectors.join()) rule.selectors = scoped
    },
  }
}
scopeForCrm.postcss = true

export default {
  plugins: [tailwindcss(), scopeForCrm(), autoprefixer()],
}
