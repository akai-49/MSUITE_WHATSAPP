<template>
  <div class="l-card p-6">
    <div class="flex items-center justify-between gap-4 border-b border-[var(--border-soft)] dark:border-gray-700 pb-4">
      <div>
        <h2 class="text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
          <span><Icon name="shopping-bag" :size="14" class="ei" /></span> WhatsApp Order Delivery Form Settings
        </h2>
        <p class="text-sm text-[var(--text-tertiary)] mt-1">
          Configure which WhatsApp Flow form is sent to buyers when a shopping cart order arrives on WhatsApp.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold" :class="settings.auto_send_enabled ? 'text-[var(--status-green-fg)] dark:text-emerald-400' : 'text-[var(--text-tertiary)]'">
          {{ settings.auto_send_enabled ? 'Auto-Send Active' : 'Auto-Send Disabled' }}
        </span>
        <button
          type="button"
          role="switch"
          aria-label="Toggle auto-send delivery form"
          :aria-checked="settings.auto_send_enabled"
          @click="settings.auto_send_enabled = !settings.auto_send_enabled"
          class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
          :class="settings.auto_send_enabled ? 'bg-[var(--brand)]' : 'bg-gray-300 dark:bg-gray-600'"
        >
          <span
            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-[var(--bg-surface)] shadow ring-0 transition duration-200 ease-in-out"
            :class="settings.auto_send_enabled ? 'translate-x-5' : 'translate-x-0'"
          />
        </button>
      </div>
    </div>

    <div class="mt-5 space-y-4">
      <!-- Select Flow Dropdown -->
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-[var(--text-secondary)] mb-1.5">
          Select Delivery Form (WhatsApp Flow)
        </label>
        <select
          v-model="settings.selected_flow"
          class="l-input w-full"
        >
          <option v-if="settings.available_flows.length" value="" disabled>-- Select a flow --
          </option>
          <option
            v-for="flow in settings.available_flows"
            :key="flow.name"
            :value="flow.name"
          >
            {{ flow.flow_name || flow.name }} ({{ flow.status || 'Draft' }})
          </option>
          <option v-if="!settings.available_flows.length" value="">No WhatsApp Flows created yet (Create one under WhatsApp → Flows)
          </option>
        </select>
        <p class="text-[11px] text-[var(--text-tertiary)] mt-1">
          Select any published or draft flow created under WhatsApp → Flows.
        </p>

        <!-- Warning when no Flow selected -->
        <div
          v-if="!settings.selected_flow"
          class="mt-2.5 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2"
          role="alert"
        >
          <svg class="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <span class="font-semibold">Notice:</span> Orders will wait for an address; no Sales Order is created until a delivery address is captured.
          </div>
        </div>
      </div>

      <!-- Prompt Text -->
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-[var(--text-secondary)] mb-1.5">
          Form Prompt Message Text
        </label>
        <textarea
          v-model="settings.prompt_text"
          rows="3"
          class="l-input w-full h-auto min-h-[80px] p-3"
          placeholder="Thank you for your order!  Please tap below to provide your delivery address..."
        />
        <p class="text-[11px] text-[var(--text-tertiary)] mt-1">
          This text is displayed to the customer alongside the interactive form button on WhatsApp.
        </p>
      </div>

      <!-- Save Button & Feedback -->
      <div class="flex items-center justify-between pt-2">
        <span v-if="toastMessage" class="text-xs font-semibold text-[var(--status-green-fg)] dark:text-emerald-400">
          <Icon name="check" :size="14" class="ei" /> {{ toastMessage }}
        </span>
        <span v-else class="text-xs text-[var(--text-tertiary)]">
          Changes take effect immediately on incoming orders.
        </span>

        <button
          @click="saveSettings"
          :disabled="saving"
          class="l-btn l-btn--primary l-btn--sm"
        >
          {{ saving ? 'Saving...' : 'Save Order Settings' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { frappeRequest, toast } from 'frappe-ui'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'

const settings = ref({
  selected_flow: '',
  auto_send_enabled: true,
  prompt_text: '',
  available_flows: [],
})

const saving = ref(false)
const toastMessage = ref('')

async function loadSettings() {
  try {
    const data = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.order_settings.get_order_flow_settings',
      method: 'GET',
    })
    const msg = data?.message || data
    if (msg) {
      const flows = msg.available_flows || []
      settings.value = {
        // Reflect exactly what's saved — never guess a flow just because
        // it's first in the list. The backend already stopped doing this
        // (order_settings.py::get_order_flow_settings) precisely because a
        // silent guess here can send the wrong form to a real customer;
        // guessing client-side would just reintroduce that bug one layer up.
        selected_flow: msg.selected_flow || '',
        auto_send_enabled: msg.auto_send_enabled ?? true,
        prompt_text: msg.prompt_text || '',
        available_flows: flows,
      }
    }
  } catch (err) {
    console.error('Failed to load order flow settings', err)
  }
}

async function saveSettings() {
  saving.value = true
  toastMessage.value = ''
  try {
    const data = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.order_settings.save_order_flow_settings',
      method: 'POST',
      body: {
        selected_flow: settings.value.selected_flow,
        auto_send_enabled: settings.value.auto_send_enabled ? 1 : 0,
        prompt_text: settings.value.prompt_text,
      },

    })
    if (data) {
      toastMessage.value = 'Order Flow settings saved successfully!'
      setTimeout(() => {
        toastMessage.value = ''
      }, 4000)
    }
  } catch (err) {
    console.error('Failed to save order flow settings', err)
    toast.error(prettifyFrappeError(err) || 'Failed to save order flow settings')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>
