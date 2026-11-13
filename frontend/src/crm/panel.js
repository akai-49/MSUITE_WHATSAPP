import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { Button, FrappeUI, frappeRequest, setConfig } from 'frappe-ui'

import whatsappRoutes from '@/modules/whatsapp/routes'
import { handleSessionExpiry } from '@/shared/utils/sessionExpiry'
import AivoAvatar from '@/shared/ui/AivoAvatar.vue'
import EmojiText from '@/shared/ui/EmojiText.vue'
import Icon from '@/shared/icons/Icon.vue'
import LLoader from '@/shared/ui/LLoader.vue'
import Shimmer from '@/shared/ui/Shimmer.vue'

import WhatsAppPanel from './WhatsAppPanel.vue'
import { PANEL_ROOT_KEY, ROOT_ID } from './context'

export const HOME_ROUTE = 'WhatsAppDashboard'

// The panel lives inside CRM's page, so its screens use an in-memory history: moving between
// them never changes CRM's URL.
function createPanelRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { render: () => h(RouterView) }, children: whatsappRoutes },
      { path: '/:pathMatch(.*)*', redirect: { name: HOME_ROUTE } },
    ],
  })
}

export function createPanel() {
  const element = document.createElement('div')
  element.id = ROOT_ID
  element.className = 'msuite-wa'

  setConfig('resourceFetcher', (options) =>
    frappeRequest(options).catch((err) => {
      handleSessionExpiry(err)
      throw err
    }),
  )

  const router = createPanelRouter()
  router.push({ name: HOME_ROUTE })

  const app = createApp(WhatsAppPanel)
  app.use(FrappeUI)
  app.use(createPinia())
  app.use(router)
  app.provide(PANEL_ROOT_KEY, element)
  // The Lemnia pages expect these to be registered globally, as msuite_frontend's main.js does.
  app.component('Button', Button)
  app.component('LLoader', LLoader)
  app.component('AivoAvatar', AivoAvatar)
  app.component('Shimmer', Shimmer)
  app.component('Icon', Icon)
  app.component('EmojiText', EmojiText)
  app.config.errorHandler = (err, _instance, info) => {
    console.error('[msuite_whatsapp] panel error', info, err)
  }
  app.mount(element)

  return { element }
}
