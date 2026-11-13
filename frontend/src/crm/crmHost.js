// Finds the WhatsApp tab on Frappe CRM's Lead and Deal pages and keeps the panel in it.
//
// CRM is not changed. It shows its WhatsApp tab when `crm.api.whatsapp.is_whatsapp_enabled`
// returns true (msuite_whatsapp overrides that method) and puts the open tab in the URL hash
// (`#whatsapp`). The panel is one Vue app; its element moves into whichever WhatsApp tab panel is
// visible and leaves the page when no WhatsApp tab is open.
import { createPanel } from './panel'
import { ROOT_ID, VIEW_ATTR, panelContext } from './context'

const CRM_PAGES = {
  Lead: { doctype: 'CRM Lead', param: 'leadId' },
  Deal: { doctype: 'CRM Deal', param: 'dealId' },
}
const WHATSAPP_HASH = '#whatsapp'
const CRM_WAIT_MS = 30000

let panel = null
let pendingSync = false

export function watchCrm() {
  waitForCrmRouter().then((router) => {
    if (!router) {
      console.warn('[msuite_whatsapp] Frappe CRM router not found; the WhatsApp panel is not added.')
      return
    }
    router.afterEach(scheduleSync)
    // CRM re-renders the tab panels without a route change (tab click before the hash
    // updates, a lead reload), so the DOM is watched as well.
    new MutationObserver(scheduleSync).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden'],
    })
    scheduleSync()

    function scheduleSync() {
      if (pendingSync) return
      pendingSync = true
      requestAnimationFrame(() => {
        pendingSync = false
        sync(router.currentRoute.value)
      })
    }
  })
}

function sync(route) {
  const page = CRM_PAGES[route.name]
  const tabPanel = page && route.hash === WHATSAPP_HASH ? visibleTabPanel() : null
  if (!tabPanel) {
    detach()
    return
  }

  panelContext.doctype = page.doctype
  panelContext.docname = route.params[page.param]
  panel = panel || createPanel()

  const root = panel.element
  if (root.parentElement !== tabPanel) {
    detach()
    tabPanel.prepend(root)
  } else if (tabPanel.firstElementChild !== root) {
    tabPanel.prepend(root)
  }
  tabPanel.setAttribute(VIEW_ATTR, panelContext.view)
}

// Lead and Deal pages have one set of tabs; CRM's dialogs are teleported outside #app.
function visibleTabPanel() {
  return document.querySelector('#app [role="tabpanel"]:not([hidden])')
}

function detach() {
  const root = document.getElementById(ROOT_ID)
  if (!root) return
  root.parentElement?.removeAttribute(VIEW_ATTR)
  root.remove()
}

function waitForCrmRouter() {
  const started = Date.now()
  return new Promise((resolve) => {
    const check = () => {
      const router = document.getElementById('app')?.__vue_app__?.config.globalProperties.$router
      if (router) resolve(router)
      else if (Date.now() - started > CRM_WAIT_MS) resolve(null)
      else setTimeout(check, 100)
    }
    check()
  })
}
