/**
 * emoji → brand line icon.
 *
 * The app used colourful emoji as UI icons (📅 🏷️ 📷 …), which clash with the Lemnia look
 * and render differently on every OS. Every decorative emoji maps to one icon from the
 * shared line set (see Icon.vue), so icons are one weight, one colour (currentColor) and
 * follow the theme. Real user content — the reply emoji picker, WhatsApp message samples —
 * is NOT touched.
 *
 * Names are Lucide kebab names (Icon.vue resolves them). `brand` = the Lemnia mark, used
 * where an emoji stood for "AI" (✨ 🤖) so the app never shows a generic AI sparkle/robot.
 */
export const EMOJI_ICONS = {
  // status / feedback
  '✓': 'check', '✔': 'check', '✔️': 'check', '✅': 'circle-check', '✕': 'x', '✖': 'x', '❌': 'x-circle', '⚠': 'alert-triangle', '⚠️': 'alert-triangle',
  'ℹ': 'info', 'ℹ️': 'info', '❗': 'alert-circle', '⚑': 'flag', '🚩': 'flag',
  // time
  '⏰': 'alarm-clock', '⏱': 'timer', '⏱️': 'timer', '⏳': 'hourglass', '🕐': 'clock', '📅': 'calendar', '🗓': 'calendar', '🗓️': 'calendar',
  // comms & channels
  '🗣': 'audio-lines', '🗣️': 'audio-lines', '🎫': 'ticket', '🎟': 'ticket', '🎟️': 'ticket',
  '💬': 'message-square', '📞': 'phone', '☎️': 'phone', '📱': 'smartphone', '📧': 'mail', '✉': 'mail', '✉️': 'mail', '📥': 'inbox', '📮': 'mailbox', '🔔': 'bell',
  '📢': 'megaphone', '📣': 'megaphone', '🔗': 'link', '🌐': 'globe', '📺': 'tv',
  // media & files
  '📷': 'camera', '📸': 'camera', '🖼': 'image', '🖼️': 'image', '🎬': 'video', '🎥': 'video', '📄': 'file-text', '📝': 'file-pen', '📋': 'clipboard-list',
  '📁': 'folder', '📂': 'folder-open', '📚': 'library', '📌': 'pin', '🏷': 'tag', '🏷️': 'tag', '📎': 'paperclip',
  // actions
  '🔍': 'search', '🗑': 'trash-2', '🗑️': 'trash-2', '✎': 'pencil', '✏️': 'pencil', '🔒': 'lock', '🔓': 'unlock', '🛠': 'wrench', '🛠️': 'wrench', '⚙️': 'settings',
  '🚀': 'rocket', '🎯': 'target', '📊': 'bar-chart-3', '📈': 'trending-up', '📉': 'trending-down', '🔥': 'flame', '💡': 'lightbulb', '⚡': 'zap',
  // commerce / places
  '🛒': 'shopping-cart', '🛍': 'shopping-bag', '🛍️': 'shopping-bag', '💵': 'banknote', '💰': 'wallet', '💼': 'briefcase', '🏢': 'building-2', '🏙': 'building', '🗺': 'map', '🗳': 'vote', '🪟': 'app-window',
  // social brands (neutral line glyphs)
  '📘': 'facebook', '🐦': 'twitter', '🔴': 'chrome', '📹': 'youtube',
  // AI / Aivo — the Lemnia mark, never a sparkle or a robot
  '✨': 'brand', '🤖': 'brand', '✦': 'brand', '🧠': 'brand',
}

/** Emoji that are real content (pickers, sample message bodies) — callers skip these. */
export const KEEP_AS_EMOJI = new Set(['😀', '😂', '👍', '👋', '🙏', '❤️', '🎉'])

// Longest keys first so '⚠️' wins over '⚠' and '🏷️' over '🏷'.
export const EMOJI_KEYS = Object.keys(EMOJI_ICONS).sort((a, b) => b.length - a.length)
export const EMOJI_RE = new RegExp(EMOJI_KEYS.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g')
