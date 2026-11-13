<!--
  The msuite WhatsApp menu in Frappe CRM's Lead / Deal WhatsApp tab.

  "Chat" shows CRM's own WhatsApp chat for the record, which msuite_whatsapp feeds through its
  overrides of `crm.api.whatsapp.*`. Every other item opens the msuite WhatsApp screen (the same
  pages as the Lemnia /msuite app) inside the tab.
-->
<template>
  <FrappeUIProvider>
    <div class="mwa-shell">
      <nav class="mwa-nav" :aria-label="'WhatsApp'">
        <button
          v-for="item in NAV_ITEMS"
          :key="item.label"
          type="button"
          class="mwa-nav-item"
          :class="{ 'is-active': isActive(item) }"
          @click="open(item)"
        >
          {{ item.label }}
        </button>
      </nav>
      <div v-if="panelContext.view === 'chat' && setup && !setup.connected" class="mwa-banner" role="status">
        <span>No WhatsApp account is connected, so messages cannot be sent yet.</span>
        <a v-if="setup.connect_url" :href="setup.connect_url" target="_blank" rel="noopener" class="mwa-banner-action">
          Connect WhatsApp
        </a>
        <span v-else>Ask your administrator to connect a WhatsApp account.</span>
      </div>
      <div v-show="panelContext.view === 'page'" class="mwa-page">
        <RouterView />
      </div>
    </div>
  </FrappeUIProvider>
</template>

<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FrappeUIProvider, frappeRequest } from 'frappe-ui'

import { PANEL_ROOT_KEY, VIEW_ATTR, panelContext } from './context'

const NAV_ITEMS = [
  { label: 'Chat' },
  { label: 'Overview', route: 'WhatsAppDashboard' },
  { label: 'Templates', route: 'WhatsAppTemplates', also: ['WhatsAppTemplateEditor'] },
  { label: 'Broadcasts', route: 'WhatsAppBulkMessages', also: ['WhatsAppBroadcastWizard'] },
  {
    label: 'Recipients',
    route: 'WhatsAppRecipients',
    also: ['WhatsAppRecipientCreate', 'WhatsAppRecipientDetail'],
  },
  { label: 'Flows', route: 'WhatsAppFlows', also: ['WhatsAppFlowBuilder', 'WhatsAppFlowResponses'] },
  { label: 'Consent', route: 'WhatsAppConsent' },
  { label: 'Insights', route: 'WhatsAppInsights', also: ['WhatsAppAccountInsights'] },
]

const route = useRoute()
const router = useRouter()
const rootElement = inject(PANEL_ROOT_KEY)

// { connected, connect_url } — without a connected account, CRM's chat cannot send.
const setup = ref(null)
onMounted(async () => {
  try {
    setup.value = await frappeRequest({ url: 'msuite_whatsapp.api.v1.crm.whatsapp.get_setup_status' })
  } catch (err) {
    console.error('[msuite_whatsapp] setup status', err)
  }
})

function isActive(item) {
  if (!item.route) return panelContext.view === 'chat'
  if (panelContext.view !== 'page') return false
  return route.name === item.route || (item.also || []).includes(route.name)
}

function open(item) {
  if (!item.route) {
    panelContext.view = 'chat'
    return
  }
  panelContext.view = 'page'
  if (!isActive(item)) router.push({ name: item.route })
}

// CRM's tab panel carries the view, so panel.css can hide CRM's chat while a screen is open.
watch(
  () => panelContext.view,
  (view) => rootElement.parentElement?.setAttribute(VIEW_ATTR, view),
)
</script>
