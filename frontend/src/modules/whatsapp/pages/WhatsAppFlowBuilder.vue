<!--
  WhatsAppFlowBuilder — interactive visual editor for WhatsApp Flows.

  Three-panel layout:
  1. Header with save/publish/status actions
  2. Canvas area showing dynamic screen nodes + connections
  3. Context-aware sidebar switching between Flow Config, Screen Editor, and Field Editor

  Users create/edit screens and fields directly — no raw doctype exposure.
-->
<template>
  <div class="fb-shell">
    <!-- Header -->
    <PageHeader
      :title="flowName || 'Untitled Flow'"
      subtitle="Interactive Customer Journey Builder"
      :back-to="{ name: 'WhatsAppFlows' }"
      back-label="Flows"
    >
      <template #meta>
        <LStatusPill v-if="flowDoc.status" :kind="flowDoc.status" :label="flowDoc.status" />
      </template>
      <template #actions>
        <button class="l-btn l-btn--secondary" @click="$router.push({ name: 'WhatsAppFlows' })">
          Cancel
        </button>
        <button
          v-if="flowDoc.flow_id"
          class="l-btn l-btn--secondary"
          :disabled="checkingStatus"
          @click="onCheckStatus"
          title="Fetch live status and validation errors from Meta"
        >
          <FeatherIcon name="refresh-cw" class="w-4 h-4" />
          <span>{{ checkingStatus ? 'Checking…' : 'Check Status' }}</span>
        </button>
        <button
          v-if="isPublished"
          class="l-btn l-btn--danger"
          :disabled="deprecating"
          @click="onDeprecate"
          title="Retire this flow"
        >
          <FeatherIcon name="archive" class="w-4 h-4" />
          <span>{{ deprecating ? 'Deprecating…' : 'Deprecate' }}</span>
        </button>
        <button class="l-btn l-btn--secondary" :disabled="saving || !canSave" @click="onSave">
          <FeatherIcon name="save" class="w-4 h-4" />
          <span>{{ saving ? 'Saving…' : 'Save draft' }}</span>
        </button>
        <button class="l-btn l-btn--primary" :disabled="publishing || saving || !canSave || isPublished" @click="onPublish">
          <FeatherIcon name="cloud-lightning" class="w-4 h-4" />
          <span>{{ publishLabel }}</span>
        </button>
      </template>
    </PageHeader>
    <p v-if="saveError" class="fb-error">{{ saveError }}</p>
    <p v-if="statusMessage" class="fb-status-msg" :class="{ 'fb-status-msg-error': statusHasErrors }">{{ statusMessage }}</p>

    <!-- Workspace Container -->
    <div class="fb-workspace">
      <!-- Node Graph Canvas -->
      <div class="fb-canvas" @click.self="clearSelection">
        <div class="canvas-grid-overlay"></div>

        <div class="nodes-container">
          <!-- Trigger Node (always first) -->
          <div class="node-card trigger-node">
            <div class="node-pin-out"></div>
            <div class="node-header">
              <div class="node-icon bg-[var(--status-green-bg)] text-[var(--status-green-fg)]">
                <FeatherIcon name="play" class="w-4 h-4" />
              </div>
              <div class="node-info">
                <div class="node-type">Trigger</div>
                <div class="node-title">User opens chat</div>
              </div>
            </div>
            <div class="node-body">
              <span class="node-meta">Starts flow automatically</span>
            </div>
          </div>

          <!-- Dynamic Screen Nodes -->
          <template v-for="(screen, sIdx) in screens" :key="screen._uid">
            <!-- Connection line -->
            <div class="connection-line-horizontal">
              <div class="arrow-head"></div>
            </div>

            <!-- Screen Node -->
            <div
              class="node-card"
              :class="{
                'active': selectedScreenIdx === sIdx,
                'form-node': !screen.terminal,
                'success-node': screen.terminal,
              }"
              @click.stop="selectScreen(sIdx)"
            >
              <div class="node-pin-in"></div>
              <div v-if="sIdx < screens.length - 1 || !screen.terminal" class="node-pin-out"></div>
              <div class="node-header">
                <div
                  class="node-icon"
                  :class="screen.terminal ? 'bg-[var(--status-purple-bg)] text-[var(--status-purple-fg)]' : 'bg-[var(--status-violet-bg)] text-[var(--status-violet-fg)]'"
                >
                  <FeatherIcon :name="screen.terminal ? 'check' : 'file-text'" class="w-4 h-4" />
                </div>
                <div class="node-info">
                  <div class="node-type">Screen {{ sIdx + 1 }}</div>
                  <div class="node-title">{{ screen.screen_title || 'Untitled' }}</div>
                </div>
                <button
                  v-if="screens.length > 1 && !isPublished"
                  class="node-delete-btn"
                  @click.stop="removeScreen(sIdx)"
                  title="Remove screen"
                  aria-label="Remove screen"
                >
                  <FeatherIcon name="x" class="w-3 h-3" />
                </button>
              </div>
              <div class="node-body">
                <div class="mock-fields">
                  <div
                    v-for="field in screenFields(sIdx)"
                    :key="field._uid"
                    class="mock-field"
                    :class="{ 'mock-field-selected': selectedFieldUid === field._uid }"
                    @click.stop="selectField(sIdx, field._uid)"
                  >
                    <span class="field-dot" :class="fieldDotClass(field.field_type)"></span>
                    {{ field.label || field.field_name || 'Untitled' }}
                    <span class="field-type-tag">{{ friendlyFieldType(field.field_type) }}</span>
                  </div>
                  <div v-if="screenFields(sIdx).length === 0" class="mock-field empty-hint">
                    No fields yet
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Add Screen Button -->
          <div v-if="!isPublished && screens.length < 10" class="connection-line-horizontal">
            <div class="arrow-head"></div>
          </div>
          <button
            v-if="!isPublished && screens.length < 10"
            class="add-screen-btn"
            @click.stop="addScreen"
          >
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>Add Screen</span>
          </button>
        </div>
      </div>

      <!-- Settings Sidebar Panel -->
      <aside class="fb-sidebar">
        <!-- Sidebar mode: Field Editor -->
        <template v-if="sidebarMode === 'field'">
          <div class="sidebar-header">
            <button class="sidebar-back" @click="clearFieldSelection" aria-label="Back to screen">
              <FeatherIcon name="arrow-left" class="w-3.5 h-3.5" />
            </button>
            <FeatherIcon name="columns" class="w-4 h-4 text-[var(--status-violet-fg)]" />
            <h3>Edit Field</h3>
          </div>
          <div class="sidebar-body" v-if="activeField">
            <div class="form-group">
              <label class="form-label">Field Type</label>
              <select class="form-select" v-model="activeField.field_type" :disabled="isPublished">
                <optgroup label="Input Fields">
                  <option value="TextInput">Text Input</option>
                  <option value="TextArea">Text Area</option>
                  <option value="DatePicker">Date Picker</option>
                  <option value="Dropdown">Dropdown</option>
                  <option value="RadioButtonsGroup">Radio Buttons</option>
                  <option value="CheckboxGroup">Checkbox Group</option>
                  <option value="OptIn">Opt-In</option>
                </optgroup>
                <optgroup label="Display Elements">
                  <option value="TextHeading">Heading</option>
                  <option value="TextSubheading">Subheading</option>
                  <option value="TextBody">Body Text</option>
                  <option value="TextCaption">Caption</option>
                  <option value="Image">Image</option>
                  <option value="EmbeddedLink">Embedded Link</option>
                  <option value="Footer">Footer Button</option>
                </optgroup>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">Field Name</label>
              <input type="text" class="form-input" v-model="activeField.field_name" placeholder="e.g. customer_name" :disabled="isPublished" />
              <p class="field-hint">Internal name (snake_case). Must be unique within this screen.</p>
            </div>

            <div class="form-group">
              <label class="form-label">
                {{ isDisplayField(activeField.field_type) ? 'Display Text' : 'Label' }}
              </label>
              <input
                v-if="!isLongDisplayField(activeField.field_type)"
                type="text" class="form-input" v-model="activeField.label"
                :placeholder="isDisplayField(activeField.field_type) ? 'Text to display…' : 'Field label…'"
                :disabled="isPublished"
              />
              <textarea
                v-else
                class="form-textarea" v-model="activeField.label" rows="3"
                placeholder="Text to display…"
                :disabled="isPublished"
              ></textarea>
            </div>

            <!-- Required toggle (input fields only) -->
            <div v-if="isInputField(activeField.field_type)" class="form-group">
              <label class="form-label-inline">
                <input type="checkbox" v-model="activeField.required" :disabled="isPublished" />
                <span>Required</span>
              </label>
            </div>

            <!-- Options editor (Dropdown / RadioButtonsGroup / CheckboxGroup) -->
            <div v-if="isChoiceField(activeField.field_type)" class="form-group">
              <label class="form-label">Options</label>
              <div class="options-editor">
                <div v-for="(opt, oIdx) in activeField.options" :key="oIdx" class="option-row">
                  <input type="text" class="form-input opt-input" v-model="opt.title" placeholder="Title" :disabled="isPublished" @blur="autoSlugOptionId(opt)" />
                  <input type="text" class="form-input opt-id-input" v-model="opt.id" placeholder="id" :disabled="isPublished" />
                  <button v-if="!isPublished" class="opt-remove-btn" @click="removeOption(oIdx)" :disabled="activeField.options.length <= 1" title="Remove option" aria-label="Remove option">
                    <FeatherIcon name="x" class="w-3 h-3" />
                  </button>
                </div>
                <button v-if="!isPublished" class="opt-add-btn" @click="addOption">
                  <FeatherIcon name="plus" class="w-3 h-3" />
                  <span>Add Option</span>
                </button>
              </div>
              <p class="field-hint">Each option needs an ID and Title. At least 1 required.</p>
            </div>

            <!-- Min/Max chars (TextInput / TextArea) -->
            <template v-if="isTextField(activeField.field_type)">
              <div class="form-row">
                <div class="form-group half">
                  <label class="form-label">Min Chars</label>
                  <input type="number" class="form-input" v-model.number="activeField.min_chars" :disabled="isPublished" min="0" />
                </div>
                <div class="form-group half">
                  <label class="form-label">Max Chars</label>
                  <input type="number" class="form-input" v-model.number="activeField.max_chars" :disabled="isPublished" min="0" />
                </div>
              </div>
            </template>

            <!-- Helper text / error message (input fields) -->
            <template v-if="isInputField(activeField.field_type)">
              <div class="form-group">
                <label class="form-label">Helper Text</label>
                <input type="text" class="form-input" v-model="activeField.helper_text" placeholder="Hint shown below field" :disabled="isPublished" />
              </div>
              <div class="form-group">
                <label class="form-label">Error Message</label>
                <input type="text" class="form-input" v-model="activeField.error_message" placeholder="Shown on validation error" :disabled="isPublished" />
              </div>
            </template>

            <!-- Init value -->
            <div v-if="showInitValue(activeField.field_type)" class="form-group">
              <label class="form-label">
                {{ activeField.field_type === 'Image' ? 'Image URL' : activeField.field_type === 'EmbeddedLink' ? 'Target Screen ID' : 'Default Value' }}
              </label>
              <input type="text" class="form-input" v-model="activeField.init_value" :disabled="isPublished" />
            </div>

            <!-- Delete field -->
            <div v-if="!isPublished" class="form-group">
              <button class="btn-danger-full" @click="removeField">
                <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                <span>Delete Field</span>
              </button>
            </div>
          </div>
        </template>

        <!-- Sidebar mode: Screen Editor -->
        <template v-else-if="sidebarMode === 'screen'">
          <div class="sidebar-header">
            <button class="sidebar-back" @click="clearSelection">
              <FeatherIcon name="arrow-left" class="w-3.5 h-3.5" />
            </button>
            <FeatherIcon name="layout" class="w-4 h-4 text-[var(--status-violet-fg)]" />
            <h3>Screen {{ selectedScreenIdx + 1 }}</h3>
          </div>
          <div class="sidebar-body" v-if="activeScreen">
            <div class="form-group">
              <label class="form-label">Screen ID</label>
              <input
                type="text" class="form-input"
                v-model="activeScreen.screen_id"
                placeholder="e.g. CUSTOMER_DETAILS"
                :disabled="isPublished || !!flowDoc.flow_id"
              />
              <p class="field-hint">
                Uppercase + underscores. {{ flowDoc.flow_id ? 'Locked after creating on WhatsApp.' : 'Cannot be changed later.' }}
              </p>
            </div>

            <div class="form-group">
              <label class="form-label">Screen Title</label>
              <input type="text" class="form-input" v-model="activeScreen.screen_title" placeholder="e.g. Customer Details" :disabled="isPublished" />
            </div>

            <div class="form-group">
              <label class="form-label-inline">
                <input type="checkbox" v-model="activeScreen.terminal" :disabled="isPublished" />
                <span>Terminal (final) screen</span>
              </label>
              <p class="field-hint">The last step that completes the flow.</p>
            </div>

            <div v-if="activeScreen.terminal" class="form-group">
              <label class="form-label">Success Message</label>
              <input type="text" class="form-input" v-model="activeScreen.success_message" placeholder="Thank you for your submission!" :disabled="isPublished" />
            </div>

            <!-- Screen Fields List -->
            <div class="form-group">
              <div class="fields-list-header">
                <label class="form-label">Fields</label>
                <button v-if="!isPublished" class="btn-link-sm" @click="addField">
                  <FeatherIcon name="plus" class="w-3 h-3" />
                  Add field
                </button>
              </div>
              <div class="fields-list">
                <div
                  v-for="(field, fIdx) in screenFields(selectedScreenIdx)"
                  :key="field._uid"
                  class="field-list-item"
                  :class="{ 'field-list-item-selected': selectedFieldUid === field._uid }"
                  @click.stop="selectField(selectedScreenIdx, field._uid)"
                >
                  <span class="field-dot" :class="fieldDotClass(field.field_type)"></span>
                  <span class="field-list-name">{{ field.label || field.field_name || 'Untitled' }}</span>
                  <span class="field-list-type">{{ friendlyFieldType(field.field_type) }}</span>
                  <div v-if="!isPublished" class="field-list-actions">
                    <button
                      class="field-move-btn"
                      :disabled="fIdx === 0"
                      @click.stop="moveField(field._uid, -1)"
                      title="Move up"
                      aria-label="Move up"
                    >
                      <FeatherIcon name="chevron-up" class="w-3 h-3" />
                    </button>
                    <button
                      class="field-move-btn"
                      :disabled="fIdx === screenFields(selectedScreenIdx).length - 1"
                      @click.stop="moveField(field._uid, 1)"
                      title="Move down"
                      aria-label="Move down"
                    >
                      <FeatherIcon name="chevron-down" class="w-3 h-3" />
                    </button>
                  </div>
                </div>
                <div v-if="screenFields(selectedScreenIdx).length === 0" class="field-list-empty">
                  No fields on this screen yet.
                </div>
              </div>
            </div>

            <!-- Screen reorder -->
            <div v-if="!isPublished && screens.length > 1" class="form-group">
              <div class="screen-reorder-row">
                <button
                  class="btn-secondary btn-sm"
                  :disabled="selectedScreenIdx === 0"
                  @click="moveScreen(-1)"
                >
                  <FeatherIcon name="arrow-left" class="w-3 h-3" />
                  Move Left
                </button>
                <button
                  class="btn-secondary btn-sm"
                  :disabled="selectedScreenIdx === screens.length - 1"
                  @click="moveScreen(1)"
                >
                  Move Right
                  <FeatherIcon name="arrow-right" class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- Sidebar mode: Flow Config (default) -->
        <template v-else>
          <div class="sidebar-header">
            <FeatherIcon name="sliders" class="w-4 h-4 text-[var(--status-violet-fg)]" />
            <h3>Flow Configuration</h3>
          </div>

          <div class="sidebar-body">
            <div class="form-group">
              <label class="form-label">Flow Name</label>
              <input type="text" class="form-input" v-model="flowName" placeholder="e.g. Lead Survey Flow" />
            </div>
            <div class="form-group">
              <label class="form-label">WhatsApp Account</label>
              <select class="form-select" v-model="flowAccount">
                <option value="" disabled>Select an account…</option>
                <option v-for="acc in wabaAccounts" :key="acc.name" :value="acc.name">
                  {{ acc.account_name || acc.name }}
                </option>
              </select>
            </div>
            <div class="form-group category-picker">
              <label class="form-label">Categories</label>
              <button
                type="button"
                class="form-select category-trigger"
                @click="categoryMenuOpen = !categoryMenuOpen"
              >
                <span>{{ categorySummary }}</span>
                <FeatherIcon name="chevron-down" class="w-4 h-4" />
              </button>
              <!-- Backdrop to close the menu on click outside, matching the
                   country-code dropdown pattern in WhatsAppTemplateEditor.vue -->
              <div v-if="categoryMenuOpen" class="category-backdrop" @click="categoryMenuOpen = false"></div>
              <div v-if="categoryMenuOpen" class="category-menu">
                <label v-for="opt in CATEGORY_OPTIONS" :key="opt.value" class="category-option">
                  <input type="checkbox" :value="opt.value" v-model="flowCategories" />
                  <span>{{ opt.label }}</span>
                </label>
              </div>
              <p class="field-hint">Meta lets a flow belong to more than one category.</p>
            </div>
            <div class="form-group">
              <label class="form-label">Description</label>
              <textarea class="form-textarea" v-model="flowDescription" rows="3" placeholder="Brief description of the workflow..."></textarea>
            </div>
            <div class="form-group">
              <label class="form-label">Call to Action</label>
              <input type="text" class="form-input" v-model="flowCta" placeholder="Open Form" maxlength="20" />
              <p class="field-hint">Button text shown to user (max 20 chars). {{ flowCta.length }}/20</p>
            </div>
            <div class="form-group">
              <label class="form-label">Flow JSON Version</label>
              <select class="form-select" v-model="flowDataApiVersion">
                <option value="6.0">6.0 (Widest compatibility)</option>
                <option value="6.1">6.1</option>
                <option value="6.2">6.2</option>
                <option value="6.3">6.3</option>
                <option value="7.0">7.0</option>
                <option value="7.1">7.1</option>
                <option value="7.2">7.2</option>
                <option value="7.3">7.3</option>
              </select>
            </div>

            <!-- Meta identifiers + live actions, once created on WhatsApp -->
            <div v-if="flowDoc.flow_id" class="form-group">
              <label class="form-label">WhatsApp Flow ID</label>
              <div class="flow-id-row">
                <code class="flow-id-value">{{ flowDoc.flow_id }}</code>
              </div>
              <div class="inline-actions">
                <button class="btn-link" :disabled="loadingPreview" @click="onPreview">
                  {{ loadingPreview ? 'Loading…' : 'Preview link' }}
                </button>
                <span class="dot-sep">·</span>
                <button class="btn-link" :disabled="syncing" @click="onSync">
                  {{ syncing ? 'Syncing…' : 'Sync from WhatsApp' }}
                </button>
                <span class="dot-sep">·</span>
                <button class="btn-link" @click="onViewResponses">View Responses</button>
              </div>
            </div>

            <!-- Send a live test message -->
            <div v-if="flowDoc.flow_id" class="form-group test-send-box">
              <label class="form-label">Send Test</label>
              <div class="test-send-row">
                <input type="text" class="form-input" v-model="testPhone" :placeholder="EXAMPLE_PHONE_HINT" />
                <button class="btn-secondary btn-sm" :disabled="testSending || !testPhone.trim()" @click="onSendTest">
                  {{ testSending ? '…' : 'Send' }}
                </button>
              </div>
              <p v-if="testResult" class="test-result" :class="{ 'test-result-error': testError }">{{ testResult }}</p>
            </div>

            <!-- Flow JSON Preview (collapsible) -->
            <div class="form-group">
              <button class="json-toggle" @click="showJsonPreview = !showJsonPreview">
                <FeatherIcon :name="showJsonPreview ? 'chevron-down' : 'chevron-right'" class="w-3.5 h-3.5" />
                <span>Flow JSON Preview</span>
              </button>
              <div v-if="showJsonPreview" class="json-preview-box">
                <pre>{{ flowJsonPreview }}</pre>
              </div>
            </div>
          </div>
        </template>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FeatherIcon } from 'frappe-ui'
import PageHeader from '@/shared/ui/PageHeader.vue'
import LStatusPill from '@/shared/ui/LStatusPill.vue'
import { callRpc } from '@/services/_factory'
import { EXAMPLE_PHONE_HINT } from '@/shared/constants/inputExamples'

const route = useRoute()
const router = useRouter()

// ── Unique ID generator ──────────────────────────────────────────────
let uidCounter = 0
function uid() { return `_uid_${++uidCounter}_${Date.now()}` }

// ── Flow metadata ────────────────────────────────────────────────────
const flowName = ref('Lead Survey Flow')
const flowAccount = ref('')
const flowDescription = ref('Capture contact information and account type preferences from new customers.')
const flowCta = ref('Open Form')
const flowDataApiVersion = ref('6.0')

const CATEGORY_OPTIONS = [
  { value: 'SIGN_UP', label: 'Sign Up' },
  { value: 'SIGN_IN', label: 'Sign In' },
  { value: 'APPOINTMENT_BOOKING', label: 'Appointment Booking' },
  { value: 'LEAD_GENERATION', label: 'Lead Generation' },
  { value: 'CONTACT_US', label: 'Contact Us' },
  { value: 'CUSTOMER_SUPPORT', label: 'Customer Support' },
  { value: 'SURVEY', label: 'Customer Feedback Survey' },
  { value: 'SHOPPING', label: 'Shopping' },
  { value: 'OTHER', label: 'Other' },
]
const flowCategories = ref(['LEAD_GENERATION'])
const categoryMenuOpen = ref(false)
const categorySummary = computed(() => {
  const n = flowCategories.value.length
  if (n === 0) return 'Select categories…'
  if (n === 1) return CATEGORY_OPTIONS.find(o => o.value === flowCategories.value[0])?.label || flowCategories.value[0]
  return `${n} options selected`
})

function parseCategories(raw) {
  if (!raw) return ['OTHER']
  if (Array.isArray(raw)) return raw.length ? raw : ['OTHER']
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length ? parsed : ['OTHER']
  } catch {
    return [raw]
  }
}

// ── Screens & fields (reactive arrays) ──────────────────────────────
const screens = ref([])
const fields = ref([])

function createDefaultScreens() {
  screens.value = [
    { _uid: uid(), screen_id: 'CUSTOMER_DETAILS', screen_title: 'Customer Details', terminal: false, success_message: '', refresh_on_back: false },
    { _uid: uid(), screen_id: 'THANK_YOU', screen_title: 'Thank You', terminal: true, success_message: '', refresh_on_back: false },
  ]
  fields.value = [
    { _uid: uid(), screen: 'CUSTOMER_DETAILS', field_name: 'name', field_type: 'TextInput', label: 'Name', required: true, options: [], helper_text: '', error_message: '', init_value: '', min_chars: null, max_chars: null },
    { _uid: uid(), screen: 'CUSTOMER_DETAILS', field_name: 'email', field_type: 'TextInput', label: 'Email', required: false, options: [], helper_text: '', error_message: '', init_value: '', min_chars: null, max_chars: null },
    { _uid: uid(), screen: 'CUSTOMER_DETAILS', field_name: 'account_type', field_type: 'Dropdown', label: 'Account Type', required: false, options: [{ id: 'personal', title: 'Personal' }, { id: 'business', title: 'Business' }], helper_text: '', error_message: '', init_value: '', min_chars: null, max_chars: null },
    { _uid: uid(), screen: 'THANK_YOU', field_name: 'thank_you_heading', field_type: 'TextHeading', label: 'Thank you!', required: false, options: [], helper_text: '', error_message: '', init_value: '', min_chars: null, max_chars: null },
    { _uid: uid(), screen: 'THANK_YOU', field_name: 'thank_you_body', field_type: 'TextBody', label: "We've received your details and will be in touch soon.", required: false, options: [], helper_text: '', error_message: '', init_value: '', min_chars: null, max_chars: null },
  ]
}

function screenFields(screenIdx) {
  if (screenIdx < 0 || screenIdx >= screens.value.length) return []
  const sid = screens.value[screenIdx].screen_id
  return fields.value.filter(f => f.screen === sid)
}

// ── Selection state ─────────────────────────────────────────────────
const selectedScreenIdx = ref(-1)
const selectedFieldUid = ref(null)

const sidebarMode = computed(() => {
  if (selectedFieldUid.value) return 'field'
  if (selectedScreenIdx.value >= 0) return 'screen'
  return 'config'
})

const activeScreen = computed(() => {
  if (selectedScreenIdx.value < 0 || selectedScreenIdx.value >= screens.value.length) return null
  return screens.value[selectedScreenIdx.value]
})

const activeField = computed(() => {
  if (!selectedFieldUid.value) return null
  return fields.value.find(f => f._uid === selectedFieldUid.value) || null
})

function selectScreen(idx) {
  selectedScreenIdx.value = idx
  selectedFieldUid.value = null
}

function selectField(screenIdx, fieldUid) {
  selectedScreenIdx.value = screenIdx
  selectedFieldUid.value = fieldUid
}

function clearSelection() {
  selectedScreenIdx.value = -1
  selectedFieldUid.value = null
}

function clearFieldSelection() {
  selectedFieldUid.value = null
}

// ── Screen CRUD ─────────────────────────────────────────────────────
function addScreen() {
  const num = screens.value.length + 1
  const sid = `SCREEN_${num}`
  screens.value.push({
    _uid: uid(),
    screen_id: sid,
    screen_title: `Screen ${num}`,
    terminal: false,
    success_message: '',
    refresh_on_back: false,
  })
  selectScreen(screens.value.length - 1)
}

function removeScreen(idx) {
  const sid = screens.value[idx].screen_id
  screens.value.splice(idx, 1)
  // Remove orphaned fields
  fields.value = fields.value.filter(f => f.screen !== sid)
  if (selectedScreenIdx.value === idx) clearSelection()
  else if (selectedScreenIdx.value > idx) selectedScreenIdx.value--
}

function moveScreen(dir) {
  const idx = selectedScreenIdx.value
  const target = idx + dir
  if (target < 0 || target >= screens.value.length) return
  const temp = screens.value[idx]
  screens.value[idx] = screens.value[target]
  screens.value[target] = temp
  selectedScreenIdx.value = target
}

// ── Field CRUD ──────────────────────────────────────────────────────
function addField() {
  if (selectedScreenIdx.value < 0) return
  const screen = screens.value[selectedScreenIdx.value]
  const existingCount = fields.value.filter(f => f.screen === screen.screen_id).length
  const newField = {
    _uid: uid(),
    screen: screen.screen_id,
    field_name: `field_${existingCount + 1}`,
    field_type: 'TextInput',
    label: '',
    required: false,
    options: [],
    helper_text: '',
    error_message: '',
    init_value: '',
    min_chars: null,
    max_chars: null,
  }
  fields.value.push(newField)
  selectField(selectedScreenIdx.value, newField._uid)
}

function removeField() {
  if (!selectedFieldUid.value) return
  const idx = fields.value.findIndex(f => f._uid === selectedFieldUid.value)
  if (idx >= 0) {
    fields.value.splice(idx, 1)
    selectedFieldUid.value = null
  }
}

function moveField(fieldUid, dir) {
  const screenIdx = selectedScreenIdx.value
  if (screenIdx < 0) return
  const sid = screens.value[screenIdx].screen_id
  // Get indices of all fields on this screen (in global fields array)
  const screenFieldIndices = []
  fields.value.forEach((f, i) => { if (f.screen === sid) screenFieldIndices.push(i) })
  const localIdx = screenFieldIndices.findIndex(gi => fields.value[gi]._uid === fieldUid)
  if (localIdx < 0) return
  const targetLocal = localIdx + dir
  if (targetLocal < 0 || targetLocal >= screenFieldIndices.length) return
  const globalA = screenFieldIndices[localIdx]
  const globalB = screenFieldIndices[targetLocal]
  const temp = fields.value[globalA]
  fields.value[globalA] = fields.value[globalB]
  fields.value[globalB] = temp
}

// ── Field type helpers ──────────────────────────────────────────────
const DISPLAY_TYPES = new Set(['TextHeading', 'TextSubheading', 'TextBody', 'TextCaption', 'Image', 'EmbeddedLink', 'Footer'])
const CHOICE_TYPES = new Set(['Dropdown', 'RadioButtonsGroup', 'CheckboxGroup'])
const TEXT_TYPES = new Set(['TextInput', 'TextArea'])

function isDisplayField(type) { return DISPLAY_TYPES.has(type) }
function isInputField(type) { return !DISPLAY_TYPES.has(type) }
function isChoiceField(type) { return CHOICE_TYPES.has(type) }
function isTextField(type) { return TEXT_TYPES.has(type) }
function isLongDisplayField(type) { return type === 'TextBody' || type === 'TextCaption' }

function showInitValue(type) {
  return ['TextInput', 'TextArea', 'DatePicker', 'Image', 'EmbeddedLink'].includes(type)
}

function friendlyFieldType(type) {
  const map = {
    TextInput: 'Text', TextArea: 'Long Text', DatePicker: 'Date',
    RadioButtonsGroup: 'Radio', CheckboxGroup: 'Checkbox', Dropdown: 'Dropdown',
    OptIn: 'Opt-In', EmbeddedLink: 'Link', Image: 'Image',
    TextHeading: 'Heading', TextSubheading: 'Sub', TextBody: 'Body',
    TextCaption: 'Caption', Footer: 'Button',
  }
  return map[type] || type
}

function fieldDotClass(type) {
  if (DISPLAY_TYPES.has(type)) return 'dot-display'
  if (CHOICE_TYPES.has(type)) return 'dot-choice'
  return 'dot-input'
}

// ── Options helpers ─────────────────────────────────────────────────
function addOption() {
  if (!activeField.value) return
  if (!activeField.value.options) activeField.value.options = []
  activeField.value.options.push({ id: '', title: '' })
}

function removeOption(idx) {
  if (!activeField.value) return
  activeField.value.options.splice(idx, 1)
}

function autoSlugOptionId(opt) {
  if (!opt.id && opt.title) {
    opt.id = opt.title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  }
}

// ── Parse options from backend (JSON string → array) ────────────────
function parseOptions(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

// ── Doc state ───────────────────────────────────────────────────────
const flowDoc = ref({ name: route.query.name || '', status: '', flow_id: '' })
const wabaAccounts = ref([])
const saving = ref(false)
const publishing = ref(false)
const saveError = ref('')
const checkingStatus = ref(false)
const statusMessage = ref('')
const statusHasErrors = ref(false)
const deprecating = ref(false)
const loadingPreview = ref(false)
const syncing = ref(false)
const testPhone = ref('')
const testSending = ref(false)
const testResult = ref('')
const testError = ref(false)
const showJsonPreview = ref(false)

const canSave = computed(() => flowName.value.trim() && flowAccount.value)
const isPublished = computed(() => flowDoc.value.status === 'Published')
const publishLabel = computed(() => {
  if (publishing.value) return 'Publishing…'
  if (isPublished.value) return 'Published'
  return flowDoc.value.flow_id ? 'Publish Flow' : 'Create + Publish'
})

// ── Flow JSON preview (computed from current screens/fields) ────────
const flowJsonPreview = computed(() => {
  try {
    const flow = { version: flowDataApiVersion.value, screens: [] }
    for (const screen of screens.value) {
      const sf = fields.value.filter(f => f.screen === screen.screen_id)
      const children = sf.map(f => {
        const comp = { type: f.field_type }
        if (f.label) comp.label = f.label
        if (f.field_name) comp.name = f.field_name
        if (f.required) comp.required = true
        return comp
      })
      const s = { id: screen.screen_id, title: screen.screen_title, layout: { type: 'SingleColumnLayout', children } }
      if (screen.terminal) { s.terminal = true; s.success = true }
      flow.screens.push(s)
    }
    return JSON.stringify(flow, null, 2)
  } catch { return '{}' }
})

// ── API calls ───────────────────────────────────────────────────────

async function fetchWabaAccounts() {
  try {
    wabaAccounts.value = await callRpc('msuite_whatsapp.api.v1.app.crud.get_waba_accounts') || []
  } catch (e) {
    console.error('Failed to fetch WABA accounts', e)
  }
}

function buildSavePayload() {
  return {
    name: flowDoc.value.name,
    flow_name: flowName.value.trim(),
    whatsapp_account: flowAccount.value,
    category: JSON.stringify(flowCategories.value.length ? flowCategories.value : ['OTHER']),
    description: flowDescription.value,
    flow_cta: flowCta.value,
    data_api_version: flowDataApiVersion.value,
    screens: screens.value.map(s => ({
      screen_id: s.screen_id,
      screen_title: s.screen_title,
      terminal: !!s.terminal,
      refresh_on_back: !!s.refresh_on_back,
      success_message: s.success_message || '',
    })),
    fields: fields.value.map(f => ({
      screen: f.screen,
      field_name: f.field_name,
      field_type: f.field_type,
      label: f.label || '',
      required: !!f.required,
      options: isChoiceField(f.field_type) ? (f.options || []) : undefined,
      helper_text: f.helper_text || '',
      error_message: f.error_message || '',
      init_value: f.init_value || '',
      min_chars: isTextField(f.field_type) ? (f.min_chars || undefined) : undefined,
      max_chars: isTextField(f.field_type) ? (f.max_chars || undefined) : undefined,
    })),
  }
}

async function onSave() {
  saveError.value = ''
  saving.value = true
  try {
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.save_flow', {
      doc: JSON.stringify(buildSavePayload()),
    })
    flowDoc.value = res
    // Sync screen/field UIDs after save (they come back from the DB)
    if (res?.screens) loadScreensFromDoc(res)
    if (res?.name && route.query.name !== res.name) {
      router.replace({ name: 'WhatsAppFlowBuilder', query: { ...route.query, name: res.name } })
    }
  } catch (e) {
    saveError.value = e?.messages?.[0] || e?.message || 'Could not save the flow.'
  } finally {
    saving.value = false
  }
}

async function onPublish() {
  if (!canSave.value) return
  saveError.value = ''
  publishing.value = true
  try {
    if (!flowDoc.value.name) {
      await onSave()
      if (!flowDoc.value.name) return
    }

    let res = flowDoc.value
    if (!res.flow_id) {
      res = await callRpc('msuite_whatsapp.api.v1.app.crud.create_flow_on_whatsapp', {
        name: flowDoc.value.name,
      })
    }
    res = await callRpc('msuite_whatsapp.api.v1.app.crud.publish_flow_to_whatsapp', {
      name: res.name,
    })
    flowDoc.value = res
    notify('Flow created and published on WhatsApp.')
  } catch (e) {
    const msg = e?.messages?.[0] || e?.message || 'Could not publish the flow.'
    saveError.value = msg
    notify(msg, 'red')
  } finally {
    publishing.value = false
  }
}

function notify(message, indicator = 'green') {
  if (window.frappe?.show_alert) {
    window.frappe.show_alert({ message, indicator })
  }
}

async function onCheckStatus() {
  if (!flowDoc.value.name) return
  checkingStatus.value = true
  statusMessage.value = ''
  statusHasErrors.value = false
  try {
    const data = await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow_status_from_whatsapp', {
      name: flowDoc.value.name,
    })
    flowDoc.value.status = data?.status ? data.status.charAt(0) + data.status.slice(1).toLowerCase() : flowDoc.value.status
    const errors = data?.validation_errors || []
    if (errors.length) {
      statusHasErrors.value = true
      statusMessage.value = `Meta status: ${data.status}. Validation errors: ${errors.map(e => e.error || 'Unknown error').join('; ')}`
    } else {
      statusMessage.value = `Meta status: ${data?.status || 'Unknown'} — no validation errors.`
    }
  } catch (e) {
    statusHasErrors.value = true
    statusMessage.value = e?.messages?.[0] || e?.message || 'Could not fetch status from WhatsApp.'
  } finally {
    checkingStatus.value = false
  }
}

async function onDeprecate() {
  if (!flowDoc.value.name) return
  deprecating.value = true
  try {
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.deprecate_flow_on_whatsapp', {
      name: flowDoc.value.name,
    })
    flowDoc.value = res
    notify('Flow deprecated. Existing conversations keep working; it can no longer be opened for new submissions.')
  } catch (e) {
    notify(e?.messages?.[0] || e?.message || 'Could not deprecate the flow.', 'red')
  } finally {
    deprecating.value = false
  }
}

async function onPreview() {
  if (!flowDoc.value.name) return
  loadingPreview.value = true
  try {
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow_preview_url', {
      name: flowDoc.value.name,
    })
    if (res?.preview_url) {
      window.open(res.preview_url, '_blank', 'noopener')
    } else {
      notify('No preview URL returned by WhatsApp.', 'orange')
    }
  } catch (e) {
    notify(e?.messages?.[0] || e?.message || 'Could not fetch the preview link.', 'red')
  } finally {
    loadingPreview.value = false
  }
}

async function onSync() {
  if (!flowDoc.value.name) return
  syncing.value = true
  try {
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.sync_flow_from_whatsapp', {
      name: flowDoc.value.name,
    })
    flowDoc.value = res
    if (res) loadScreensFromDoc(res)
    flowCategories.value = parseCategories(res.category)
    notify('Synced latest status and flow.json from WhatsApp.')
  } catch (e) {
    notify(e?.messages?.[0] || e?.message || 'Could not sync from WhatsApp.', 'red')
  } finally {
    syncing.value = false
  }
}

function onViewResponses() {
  if (!flowDoc.value.name) return
  router.push({ name: 'WhatsAppFlowResponses', query: { flow: flowDoc.value.name } })
}

async function onSendTest() {
  if (!flowDoc.value.name || !testPhone.value.trim()) return
  testSending.value = true
  testResult.value = ''
  testError.value = false
  try {
    await callRpc('msuite_whatsapp.api.v1.app.crud.send_test_flow', {
      name: flowDoc.value.name,
      phone_number: testPhone.value.trim(),
    })
    testResult.value = `Test message sent to ${testPhone.value.trim()}.`
  } catch (e) {
    testError.value = true
    testResult.value = e?.messages?.[0] || e?.message || 'Could not send the test message.'
  } finally {
    testSending.value = false
  }
}

// ── Load existing flow from backend ─────────────────────────────────
function loadScreensFromDoc(doc) {
  if (doc.screens && doc.screens.length) {
    screens.value = doc.screens.map(s => ({
      _uid: uid(),
      screen_id: s.screen_id || '',
      screen_title: s.screen_title || '',
      terminal: !!s.terminal,
      success_message: s.success_message || '',
      refresh_on_back: !!s.refresh_on_back,
    }))
  }
  if (doc.fields && doc.fields.length) {
    fields.value = doc.fields.map(f => ({
      _uid: uid(),
      screen: f.screen || '',
      field_name: f.field_name || '',
      field_type: f.field_type || 'TextInput',
      label: f.label || '',
      required: !!f.required,
      options: parseOptions(f.options),
      helper_text: f.helper_text || '',
      error_message: f.error_message || '',
      init_value: f.init_value || '',
      min_chars: f.min_chars || null,
      max_chars: f.max_chars || null,
    }))
  }
}

// ── When screen_id changes, update all fields referencing it ────────
watch(screens, (newScreens, oldScreens) => {
  if (!oldScreens || newScreens.length !== oldScreens.length) return
  for (let i = 0; i < newScreens.length; i++) {
    const oldSid = oldScreens[i]?.screen_id
    const newSid = newScreens[i]?.screen_id
    if (oldSid && newSid && oldSid !== newSid) {
      fields.value.forEach(f => {
        if (f.screen === oldSid) f.screen = newSid
      })
    }
  }
}, { deep: true })

// ── Mount ───────────────────────────────────────────────────────────
onMounted(async () => {
  await fetchWabaAccounts()
  const name = route.query.name
  if (name) {
    try {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow', { name })
      if (res) {
        flowDoc.value = res
        flowName.value = res.flow_name || ''
        flowAccount.value = res.whatsapp_account || ''
        flowCategories.value = parseCategories(res.category)
        flowDescription.value = res.description || ''
        flowCta.value = res.flow_cta || 'Open Form'
        flowDataApiVersion.value = res.data_api_version || '6.0'
        loadScreensFromDoc(res)
      }
    } catch (e) {
      console.error(e)
    }
  }
  // If still no screens (new flow), seed defaults
  if (!screens.value.length) createDefaultScreens()
})
</script>

<style scoped>
.fb-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ink-25);
  color: var(--ink-900);
  overflow: hidden;
}

/* Header */
.fb-header {
  height: 70px;
  background: var(--surface-surface);
  border-bottom: 1.5px solid var(--ink-100);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  flex-shrink: 0;
}
.fb-header-left { display: flex; align-items: center; gap: 16px; }
.back-link {
  width: 36px; height: 36px; border-radius: 8px;
  border: 1.5px solid var(--ink-100); background: var(--surface-surface);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--ink-500); transition: all 0.1s;
}
.back-link:hover { border-color: var(--brand-500); color: var(--brand-500); }
.fb-title-area { display: flex; align-items: center; gap: 10px; }
.fb-title { margin: 0; font-size: 16px; font-weight: 700; }
.fb-subtitle { margin: 2px 0 0; font-size: 11px; color: var(--ink-500); }

.fb-header-actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.fb-error { margin: 0; padding: 8px 24px; background: var(--status-red-bg); border-bottom: 1px solid var(--status-red-bg); color: var(--red-700); font-size: 12.5px; }
.fb-status-msg { margin: 0; padding: 8px 24px; background: var(--status-blue-bg); border-bottom: 1px solid var(--status-blue-bg); color: var(--status-blue-fg); font-size: 12.5px; }
.fb-status-msg-error { background: var(--status-red-bg); border-bottom-color: var(--status-red-bg); color: var(--red-700); }

/* Buttons */
.btn-secondary {
  height: 38px; padding: 0 16px; border-radius: 8px; font-size: 13px; font-weight: 500;
  background: var(--surface-surface); border: 1.5px solid var(--ink-100); color: var(--ink-900);
  cursor: pointer; transition: all 0.1s; display: inline-flex; align-items: center; gap: 6px;
}
.btn-secondary:hover { border-color: var(--ink-200); }
.btn-secondary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { height: 32px !important; padding: 0 12px !important; font-size: 12px !important; }
.btn-primary {
  height: 38px; padding: 0 16px; border-radius: 8px; font-size: 13px; font-weight: 600;
  background: var(--brand); border: 1.5px solid var(--brand-500); color: white;
  display: flex; align-items: center; gap: 6px; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger-text { color: var(--red-700) !important; border-color: var(--status-red-bg) !important; }
.btn-danger-text:hover:not(:disabled) { background: var(--status-red-bg); border-color: var(--red-300) !important; }
.btn-danger-full {
  width: 100%; height: 36px; border-radius: 8px; font-size: 12.5px; font-weight: 500;
  background: var(--status-red-bg); border: 1.5px solid var(--status-red-bg); color: var(--red-700);
  cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;
  transition: all 0.1s;
}
.btn-danger-full:hover { background: var(--status-red-bg); border-color: var(--red-300); }

/* Workspace */
.fb-workspace { flex: 1; display: flex; min-height: 0; }

/* Canvas */
.fb-canvas {
  flex: 1;
  min-width: 0; position: relative; background-color: var(--ink-50);
  overflow: auto; display: flex; align-items: center; justify-content: center;
}
.canvas-grid-overlay {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background-image: radial-gradient(circle, var(--ink-200) 1.2px, transparent 1.2px);
  background-size: 24px 24px; opacity: 0.55; pointer-events: none;
}
.nodes-container { display: flex; align-items: center; position: relative; padding: 40px; }

/* Node Cards */
.node-card {
  width: 240px; background: var(--surface-surface); border: 1.5px solid var(--ink-100); border-radius: 12px;
  padding: 14px; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  transition: all 0.2s; cursor: pointer; flex-shrink: 0;
}
.node-card:hover { border-color: var(--ink-200); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.05); }
.node-card.active { border-color: var(--brand-500); box-shadow: 0 0 0 1px var(--brand-500), 0 8px 24px rgba(52, 65, 156,0.08); }
.trigger-node { cursor: default; }
.trigger-node:hover { transform: none; }

.node-header { display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--ink-50); padding-bottom: 10px; margin-bottom: 10px; }
.node-icon { width: 30px; height: 30px; border-radius: 6px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.node-info { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.node-type { font-size: var(--fs-2xs); font-weight: 700; color: var(--ink-500); text-transform: uppercase; letter-spacing: 0.05em; }
.node-title { font-size: 12px; font-weight: 600; color: var(--ink-900); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.node-body { font-size: 11px; }
.node-meta { color: var(--ink-300); font-style: italic; }

.node-delete-btn {
  width: 22px; height: 22px; border-radius: 4px; border: none; background: transparent;
  color: var(--ink-300); cursor: pointer; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.1s;
}
.node-delete-btn:hover { background: var(--status-red-bg); color: var(--status-red-fg); }

/* Mock fields in node cards */
.mock-fields { display: flex; flex-direction: column; gap: 4px; }
.mock-field {
  padding: 5px 8px; background: var(--ink-25); border-radius: 5px; border: 1px solid var(--ink-100);
  color: var(--ink-600); display: flex; align-items: center; gap: 6px; font-size: var(--fs-2xs);
  cursor: pointer; transition: all 0.1s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mock-field:hover { border-color: var(--brand-100); background: var(--status-violet-bg); }
.mock-field-selected { border-color: var(--brand-500); background: var(--brand-50); }
.mock-field.empty-hint { color: var(--ink-300); font-style: italic; cursor: default; border-style: dashed; }
.mock-field.empty-hint:hover { border-color: var(--ink-100); background: var(--ink-25); }

.field-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot-input { background: var(--status-blue-dot); }
.dot-choice { background: var(--status-violet-dot); }
.dot-display { background: var(--ink-300); }
.field-type-tag { margin-left: auto; font-size: var(--fs-2xs); color: var(--ink-300); font-weight: 500; flex-shrink: 0; }

/* Connection lines + node pins */
.node-pin-in, .node-pin-out {
  width: 10px; height: 10px; border-radius: 50%; background: var(--surface-surface);
  border: 2px solid var(--ink-300); position: absolute; top: 50%; transform: translateY(-50%); z-index: 5;
}
.node-pin-in { left: -6px; }
.node-pin-out { right: -6px; }
.node-card.active .node-pin-in, .node-card.active .node-pin-out { border-color: var(--brand-500); }

.connection-line-horizontal {
  height: 2px; background: var(--ink-200); position: relative; flex-grow: 1; min-width: 50px; max-width: 80px;
}
.arrow-head {
  width: 0; height: 0; border-top: 5px solid transparent; border-bottom: 5px solid transparent;
  border-left: 6px solid var(--ink-200); position: absolute; top: 50%; right: 0; transform: translateY(-50%);
}

/* Add Screen button */
.add-screen-btn {
  width: 140px; height: 60px; border-radius: 12px; border: 2px dashed var(--ink-200);
  background: var(--surface-surface); color: var(--ink-500); display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 4px; cursor: pointer;
  font-size: 11.5px; font-weight: 500; transition: all 0.15s; flex-shrink: 0;
}
.add-screen-btn:hover { border-color: var(--brand-500); color: var(--brand-500); background: var(--status-violet-bg); }

/* Sidebar */
.fb-sidebar {
  width: 340px; max-width: 100vw; background: var(--surface-surface); border-left: 1.5px solid var(--ink-100);
  display: flex; flex-direction: column; flex-shrink: 0;
}
/* Below this the canvas has no usable room left beside a 340px inspector. */
@media (max-width: 900px) {
  .fb-sidebar { width: 100%; border-left: none; border-top: 1.5px solid var(--ink-100); }
}
.sidebar-header {
  height: 52px; border-bottom: 1.5px solid var(--ink-100);
  display: flex; align-items: center; padding: 0 16px; gap: 10px;
}
.sidebar-header h3 { margin: 0; font-size: 13.5px; font-weight: 700; }
.sidebar-back {
  width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--ink-100);
  background: var(--surface-surface); display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--ink-500); transition: all 0.1s;
}
.sidebar-back:hover { border-color: var(--brand-500); color: var(--brand-500); }

.sidebar-body {
  padding: 16px; display: flex; flex-direction: column; gap: 14px;
  overflow-y: auto; flex-grow: 1;
}

/* Form elements */
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-label { font-size: 11px; font-weight: 600; color: var(--ink-600); text-transform: uppercase; letter-spacing: 0.03em; }
.form-label-inline { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 500; color: var(--ink-700); cursor: pointer; }
.form-label-inline input[type="checkbox"] { accent-color: var(--brand-500); }
.form-input, .form-select, .form-textarea {
  border: 1.5px solid var(--ink-100); border-radius: 8px; padding: 8px 12px;
  font-size: 12.5px; outline: none; background: var(--surface-surface); transition: border-color 0.1s;
  width: 100%; box-sizing: border-box;
}
.form-input:focus, .form-select:focus, .form-textarea:focus { border-color: var(--brand-500); }
.form-input:disabled, .form-select:disabled, .form-textarea:disabled { background: var(--ink-25); color: var(--ink-300); cursor: not-allowed; }
.field-hint { font-size: 11px; color: var(--ink-300); margin: 0; }
.form-row { display: flex; gap: 10px; }
.form-group.half { flex: 1; }

/* Category picker */
.category-picker { position: relative; }
.category-trigger { width: 100%; display: flex; align-items: center; justify-content: space-between; cursor: pointer; text-align: left; color: var(--ink-800); }
.category-backdrop { position: fixed; inset: 0; z-index: 19; }
.category-menu {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 20;
  background: var(--surface-surface); border: 1.5px solid var(--ink-100); border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15,23,42,0.12); padding: 6px; max-height: 220px; overflow-y: auto;
}
.category-option { display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 6px; font-size: 12.5px; color: var(--ink-700); cursor: pointer; }
.category-option:hover { background: var(--ink-50); }

/* Options editor */
.options-editor { display: flex; flex-direction: column; gap: 6px; }
.option-row { display: flex; gap: 6px; align-items: center; }
.opt-input { flex: 2; }
.opt-id-input { flex: 1; font-family: monospace; font-size: 11px; }
.opt-remove-btn {
  width: 26px; height: 26px; border-radius: 4px; border: none; background: transparent;
  color: var(--ink-300); cursor: pointer; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.opt-remove-btn:hover { background: var(--status-red-bg); color: var(--status-red-fg); }
.opt-remove-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.opt-add-btn {
  display: flex; align-items: center; gap: 4px; padding: 6px 8px;
  border: 1px dashed var(--ink-200); border-radius: 6px; background: transparent;
  color: var(--brand-500); font-size: 11.5px; font-weight: 500; cursor: pointer;
  transition: all 0.1s;
}
.opt-add-btn:hover { border-color: var(--brand-500); background: var(--status-violet-bg); }

/* Fields list in screen editor sidebar */
.fields-list-header { display: flex; justify-content: space-between; align-items: center; }
.btn-link-sm {
  border: none; background: none; padding: 0; font-size: 11.5px; font-weight: 600;
  color: var(--brand-500); cursor: pointer; display: flex; align-items: center; gap: 4px;
}
.btn-link-sm:hover { text-decoration: underline; }
.fields-list { display: flex; flex-direction: column; gap: 4px; }
.field-list-item {
  padding: 7px 10px; background: var(--ink-25); border-radius: 6px; border: 1px solid var(--ink-100);
  display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--ink-700);
  cursor: pointer; transition: all 0.1s;
}
.field-list-item:hover { border-color: var(--brand-100); background: var(--status-violet-bg); }
.field-list-item-selected { border-color: var(--brand-500); background: var(--brand-50); }
.field-list-name { flex: 1;
  min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.field-list-type { font-size: var(--fs-2xs); color: var(--ink-300); font-weight: 500; flex-shrink: 0; }
.field-list-actions { display: flex; gap: 2px; flex-shrink: 0; }
.field-move-btn {
  width: 22px; height: 22px; border: none; background: transparent; border-radius: 4px;
  color: var(--ink-300); cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.field-move-btn:hover { background: var(--ink-100); color: var(--ink-700); }
.field-move-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.field-list-empty { padding: 12px; text-align: center; font-size: 11px; color: var(--ink-300); font-style: italic; }

/* Screen reorder */
.screen-reorder-row { display: flex; gap: 8px; justify-content: center; }

/* Flow ID / live-action rows */
.flow-id-row { display: flex; align-items: center; }
.flow-id-value {
  font-size: 11px; font-family: monospace; background: var(--ink-50);
  border: 1px solid var(--ink-100); border-radius: 6px; padding: 4px 8px;
  color: var(--ink-700); word-break: break-all;
}
.inline-actions { display: flex; align-items: center; gap: 6px; margin-top: 8px; }
.btn-link { border: none; background: none; padding: 0; font-size: 11.5px; font-weight: 600; color: var(--brand-500); cursor: pointer; }
.btn-link:hover:not(:disabled) { text-decoration: underline; }
.btn-link:disabled { opacity: 0.6; cursor: not-allowed; }
.dot-sep { color: var(--ink-200); font-size: 11px; }

/* Send test */
.test-send-box { background: var(--ink-25); border: 1px solid var(--ink-100); border-radius: 10px; padding: 12px; }
.test-send-row { display: flex; gap: 8px; }
.test-send-row .form-input { flex: 1; }
.test-result { margin: 8px 0 0; font-size: 11px; color: var(--status-green-fg); }
.test-result-error { color: var(--red-700); }

/* JSON Preview */
.json-toggle {
  display: flex; align-items: center; gap: 6px; border: none; background: none;
  font-size: 12px; font-weight: 600; color: var(--ink-600); cursor: pointer; padding: 0;
}
.json-toggle:hover { color: var(--ink-800); }
.json-preview-box {
  margin-top: 6px; padding: 10px; background: var(--ink-800); border-radius: 8px;
  max-height: 200px; overflow: auto;
}
.json-preview-box pre {
  margin: 0; font-size: var(--fs-2xs); line-height: 1.5; color: var(--status-cyan-bg); font-family: monospace;
  white-space: pre-wrap; word-break: break-all;
}

/* Colors */
.bg-emerald-50 { background-color: var(--status-green-bg); }
.text-emerald-600 { color: var(--status-green-fg); }
.bg-brand-50 { background-color: var(--brand-50, var(--bg-sunken)); }
.text-brand-600 { color: var(--brand); }
.bg-purple-50 { background-color: var(--status-purple-bg); }
.text-purple-600 { color: var(--status-purple-fg); }
</style>

