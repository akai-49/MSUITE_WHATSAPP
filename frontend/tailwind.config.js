// Tailwind preset comes from frappe-ui so colour tokens / fonts / spacing
// match Frappe CRM + Helpdesk pixel-for-pixel. The frappe-ui version is pinned to
// Frappe CRM's own (see package.json): this CSS loads on CRM's page, and an older preset
// would redefine CRM's colour tokens with other values.
//
// Deliberately minimal. Two things that look like omissions but are not:
//
//  • `darkMode` — the preset already sets
//    `['selector', '[data-theme="dark"]']`, which is exactly the attribute
//    applyTheme.js writes, so `dark:` utilities follow the app's
//    light/dark/system toggle rather than the OS. Re-declaring it here is
//    how you accidentally switch the whole app back to `media`.
//
//  • no extra grey shades — an undefined shade (e.g. the old
//    `border-gray-150`) compiles to nothing and the border falls through to
//    the preset's `borderColor.DEFAULT`, `var(--outline-gray-1)`, which IS
//    theme-aware. Defining the shade would replace that with a fixed
//    literal and break dark mode. Prefer removing the bogus class.
import frappeUIPreset from 'frappe-ui/tailwind'
import colors from 'tailwindcss/colors'

export default {
  presets: [frappeUIPreset],
  // Frappe CRM's page already loads Tailwind's reset. A second copy would restyle CRM.
  corePlugins: { preflight: false },
  theme: {
    extend: {
      // The frappe-ui preset ships a trimmed palette, so utilities the pages already use
      // (bg-emerald-600, text-indigo-600, bg-blue-700 …) compiled to nothing — white text
      // on a transparent button. These families restore them, mapped onto the Lemnia
      // palette: emerald = Operations teal, indigo = Revenue blue.
      colors: {
        emerald: { ...colors.emerald, 400: '#2DC8B6', 500: '#12907F', 600: '#12907F', 700: '#0E7A6C', 800: '#0A5F54' },
        indigo: { ...colors.indigo, 400: '#5F6BBE', 500: '#34419C', 600: '#34419C', 700: '#2C378A', 800: '#242E75' },
        // purple and blue are not added: the frappe-ui 1.0 preset has them, and this CSS also
        // loads on Frappe CRM's page, where other values would recolour CRM.
        rose: colors.rose,
      },
    },
  },
  content: [
    './src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
  ],
}
