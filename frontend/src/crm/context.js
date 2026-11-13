import { reactive } from 'vue'

export const ROOT_ID = 'msuite-wa-root'
export const PANEL_ROOT_KEY = Symbol('msuite-wa-root')

// Set on CRM's tab panel. `chat` keeps CRM's own WhatsApp chat visible under the panel's menu;
// `page` hides it and gives the tab to the open msuite WhatsApp screen (see panel.css).
export const VIEW_ATTR = 'data-msuite-wa'

// The CRM record whose WhatsApp tab is open, and which view the panel shows.
export const panelContext = reactive({
  doctype: '',
  docname: '',
  view: 'chat',
})
