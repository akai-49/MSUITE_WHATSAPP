export default [
  {
    path: 'whatsapp',
    name: 'WhatsAppDashboard',
    component: () => import('./pages/WhatsAppDashboard.vue'),
  },
  {
    path: 'whatsapp/insights',
    name: 'WhatsAppInsights',
    component: () => import('./pages/WhatsAppInsights.vue'),
  },
  {
    path: 'whatsapp/insights/:account',
    name: 'WhatsAppAccountInsights',
    component: () => import('./pages/WhatsAppInsights.vue'),
    props: true,
  },
  {
    path: 'whatsapp/templates',
    name: 'WhatsAppTemplates',
    component: () => import('./pages/WhatsAppTemplates.vue'),
  },
  {
    path: 'whatsapp/templates/new',
    name: 'WhatsAppTemplateEditor',
    component: () => import('./pages/WhatsAppTemplateEditor.vue'),
    props: (route) => ({
      name: route.query.name || '',
    }),
  },
  {
    path: 'whatsapp/recipients',
    name: 'WhatsAppRecipients',
    component: () => import('./pages/WhatsAppRecipients.vue'),
  },
  {
    path: 'whatsapp/recipients/new',
    name: 'WhatsAppRecipientCreate',
    component: () => import('./pages/WhatsAppRecipientDetail.vue'),
    props: { isNew: true, id: '' },
  },
  {
    path: 'whatsapp/recipients/:id',
    name: 'WhatsAppRecipientDetail',
    component: () => import('./pages/WhatsAppRecipientDetail.vue'),
    props: true,
  },
  {
    path: 'whatsapp/consent',
    name: 'WhatsAppConsent',
    component: () => import('./pages/WhatsAppConsent.vue'),
  },
  {
    path: 'whatsapp/bulk-messages',
    name: 'WhatsAppBulkMessages',
    component: () => import('./pages/WhatsAppBulkMessages.vue'),
  },
  {
    path: 'whatsapp/bulk-messages/new',
    name: 'WhatsAppBroadcastWizard',
    component: () => import('./pages/WhatsAppBroadcastWizard.vue'),
  },
  {
    path: 'whatsapp/flows',
    name: 'WhatsAppFlows',
    component: () => import('./pages/WhatsAppFlows.vue'),
  },
  {
    path: 'whatsapp/flows/new',
    name: 'WhatsAppFlowBuilder',
    component: () => import('./pages/WhatsAppFlowBuilder.vue'),
  },
  {
    path: 'whatsapp/flows/responses',
    name: 'WhatsAppFlowResponses',
    component: () => import('./pages/WhatsAppFlowResponses.vue'),
    props: (route) => ({
      flow: route.query.flow || '',
    }),
  },
  {
    path: 'whatsapp/bulk',
    beforeEnter(to) {
      const name = to.query.name || ''
      if (name) {
        window.location.href = `/app/bulk-whatsapp-message/${encodeURIComponent(name)}`
      } else {
        window.location.href = '/app/bulk-whatsapp-message'
      }
    }
  },
]
