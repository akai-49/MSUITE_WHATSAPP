// Entry of the WhatsApp panel that msuite_whatsapp adds to Frappe CRM.
//
// `msuite_whatsapp/crm_tab/renderer.py` adds this script to CRM's /crm page. Frappe CRM's code is
// not changed: the script finds CRM's Vue app on #app, follows its router, and mounts the panel in
// the WhatsApp tab of the Lead and Deal pages.
import '../lemnia.css'
import './crm-theme.css'
import './panel.css'

import { watchCrm } from './crmHost'

// The Lemnia pages read the site timezone from frappeBootData. CRM's boot puts it on window.
window.frappeBootData = window.frappeBootData || {
  user: window.user,
  csrf_token: window.csrf_token,
  site_name: window.site_name,
  timezone: window.timezone,
}

watchCrm()
