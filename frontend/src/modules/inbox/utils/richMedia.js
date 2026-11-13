/** Limits and formats for Inbox voice notes, GIFs and stickers. */

/** Longest voice note the recorder allows (seconds); it stops itself at this length. */
export const VOICE_NOTE_MAX_SECONDS = 300

/** MediaRecorder formats in preference order; the first the browser supports wins. */
export const VOICE_NOTE_MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']

/** File extension per recorded container, so the server can tell it is audio. */
export const VOICE_NOTE_EXTENSIONS = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }

/** Only WebP stickers can be sent on WhatsApp. */
export const STICKER_MIME = 'image/webp'

/** GIF grid page size requested from the server. */
export const GIF_PAGE_SIZE = 24

/** Per-kind wording for the GIPHY search panel. */
export const GIF_PANEL_COPY = Object.freeze({
  gifs: { search: 'Search GIFs', notSetUp: 'GIFs are not set up', loadError: 'Could not load GIFs', alt: 'GIF' },
  stickers: { search: 'Search stickers', notSetUp: 'Stickers are not set up', loadError: 'Could not load stickers', alt: 'Sticker' },
})
