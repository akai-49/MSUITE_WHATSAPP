<!--
  WhatsAppConsent — Bulk WhatsApp consent management (opt-in / opt-out).
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="WhatsApp Consent"
      subtitle="Bulk opt-in or opt-out phone numbers for WhatsApp communications"
    />

    <!-- Results Section (shown after execution) -->
    <section v-if="hasRun" class="mb-6 space-y-4">
      <!-- Status Alert Banner -->
      <div
        class="result-alert"
        :class="result.updated > 0 ? 'result-alert-success' : 'result-alert-warning'"
      >
        <div class="flex items-center gap-3">
          <FeatherIcon
            :name="result.updated > 0 ? 'check-circle' : 'alert-triangle'"
            class="w-5 h-5 flex-shrink-0"
          />
          <div>
            <h4 class="font-semibold text-sm">
              {{
                result.updated > 0
                  ? `Successfully updated consent for ${result.updated.toLocaleString()} contact${result.updated === 1 ? '' : 's'}.`
                  : 'No contacts were updated.'
              }}
            </h4>
            <p class="text-xs mt-0.5 opacity-90">
              <span v-if="result.updated > 0">
                Action: <strong>{{ executedAction === 'opt_in' ? 'Opted In' : 'Opted Out' }}</strong>.
              </span>
              <span v-else>
                None of the provided numbers resulted in a consent update.
              </span>
              <span v-if="result.not_found > 0">
                {{ result.not_found.toLocaleString() }} not found in CRM contacts.
              </span>
              <span v-if="result.invalid > 0">
                {{ result.invalid.toLocaleString() }} invalid format.
              </span>
            </p>
          </div>
        </div>
        <button class="l-btn l-btn--secondary l-btn--sm" @click="resetResults">Dismiss</button>
      </div>

      <!-- Stats Cards -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard
          label="Updated"
          :value="result.updated.toLocaleString()"
          icon="check"
        />
        <KpiCard
          label="Not Found"
          :value="result.not_found.toLocaleString()"
          icon="help-circle"
        />
        <KpiCard
          label="Invalid"
          :value="result.invalid.toLocaleString()"
          icon="x-circle"
        />
      </div>
    </section>

    <!-- Main Configuration Card -->
    <div class="consent-card l-card">
      <!-- Action Selection -->
      <div class="form-group">
        <label class="form-label">Consent Action</label>
        <div class="action-toggle-grid">
          <div
            class="action-option"
            :class="{ active: action === 'opt_in' }"
            @click="action = 'opt_in'"
          >
            <div class="action-option-header">
              <div class="action-icon-circle opt-in-icon">
                <FeatherIcon name="user-check" class="w-4 h-4 text-[var(--status-green-fg)]" />
              </div>
              <span class="action-option-title">Opt In</span>
            </div>
            <p class="action-option-desc">
              Record customer consent to receive WhatsApp promotional messages.
            </p>
          </div>

          <div
            class="action-option"
            :class="{ active: action === 'opt_out' }"
            @click="action = 'opt_out'"
          >
            <div class="action-option-header">
              <div class="action-icon-circle opt-out-icon">
                <FeatherIcon name="user-x" class="w-4 h-4 text-[var(--status-red-fg)]" />
              </div>
              <span class="action-option-title">Opt Out</span>
            </div>
            <p class="action-option-desc">
              Withdraw promotional consent (only updates existing contacts).
            </p>
          </div>
        </div>
      </div>

      <!-- Input Tabs -->
      <div class="form-group">
        <div class="flex items-center justify-between mb-2">
          <label class="form-label mb-0">Phone Numbers</label>
          <div class="tab-pill-group">
            <button
              type="button"
              class="tab-pill"
              :class="{ active: inputTab === 'paste' }"
              @click="inputTab = 'paste'"
            >
              <FeatherIcon name="edit-3" class="w-3.5 h-3.5" />
              <span>Paste / Type</span>
            </button>
            <button
              type="button"
              class="tab-pill"
              :class="{ active: inputTab === 'upload' }"
              @click="inputTab = 'upload'"
            >
              <FeatherIcon name="upload-cloud" class="w-3.5 h-3.5" />
              <span>Upload CSV / TXT</span>
            </button>
          </div>
        </div>

        <!-- Tab 1: Paste Textarea -->
        <div v-show="inputTab === 'paste'">
          <textarea
            v-model="rawInput"
            rows="7"
            class="form-control form-textarea"
            placeholder="Paste phone numbers (one per line, comma or semicolon separated)&#10;e.g.&#10;+1234567890&#10;+1234567891&#10;+1234567892"
          ></textarea>
          <p class="input-helper">
            Paste one number per line or separate by commas. Duplicates and column headers are automatically cleaned.
          </p>
        </div>

        <!-- Tab 2: File Upload Zone -->
        <div v-show="inputTab === 'upload'" class="upload-zone">
          <div
            class="upload-drop-area"
            :class="{ 'upload-drag-over': isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="handleFileDrop"
            @click="triggerFileInput"
          >
            <FeatherIcon name="upload-cloud" class="w-10 h-10 text-[var(--brand)] opacity-80" />
            <h4 class="upload-title">
              {{ uploadedFileName ? uploadedFileName : 'Drop CSV or TXT file here' }}
            </h4>
            <p class="upload-desc">
              {{ uploadedFileName ? 'Click or drop another file to replace' : 'or click to browse from your computer' }}
            </p>
            <p class="upload-formats">Supported formats: .csv, .txt (max 50,000 numbers)</p>
            <input
              ref="fileInputRef"
              type="file"
              accept=".csv,.txt"
              class="hidden-file-input"
              @change="handleFileSelect"
            />
          </div>
          <p v-if="fileError" class="upload-error">{{ fileError }}</p>
        </div>
      </div>

      <!-- Parsed Summary & Preview -->
      <div v-if="parsedNumbers.length > 0" class="preview-box">
        <div class="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div class="flex items-center gap-2">
            <span class="summary-pill summary-valid">
              {{ parsedNumbers.length.toLocaleString() }} unique number{{ parsedNumbers.length === 1 ? '' : 's' }} detected
            </span>
            <span v-if="batchCount > 1" class="summary-pill summary-total">
              {{ batchCount }} API batch{{ batchCount === 1 ? '' : 'es' }} (5k max each)
            </span>
          </div>
          <button
            type="button"
            class="text-xs text-[var(--ink-500)] hover:text-[var(--status-red-fg)] transition-colors"
            @click="clearNumbers"
          >
            Clear all
          </button>
        </div>

        <div class="preview-tags">
          <span
            v-for="num in previewNumbers"
            :key="num"
            class="preview-number-badge"
          >
            {{ num }}
          </span>
          <span v-if="parsedNumbers.length > previewNumbers.length" class="preview-more-badge">
            +{{ (parsedNumbers.length - previewNumbers.length).toLocaleString() }} more
          </span>
        </div>
      </div>

      <!-- Action Footer -->
      <div class="consent-footer">
        <div class="text-xs text-[var(--ink-500)]">
          <span v-if="parsedNumbers.length > 0">
            Ready to {{ action === 'opt_in' ? 'opt in' : 'opt out' }} {{ parsedNumbers.length.toLocaleString() }} contact(s).
          </span>
          <span v-else>
            Enter or upload phone numbers to begin.
          </span>
        </div>

        <button
          type="button"
          class="l-btn l-btn--primary"
          :disabled="parsedNumbers.length === 0 || isProcessing"
          @click="showConfirm = true"
        >
          <FeatherIcon :name="action === 'opt_in' ? 'user-check' : 'user-x'" class="w-4 h-4" />
          <span>
            {{
              isProcessing
                ? progressLabel
                : `${action === 'opt_in' ? 'Opt In' : 'Opt Out'} ${parsedNumbers.length ? `(${parsedNumbers.length.toLocaleString()})` : ''}`
            }}
          </span>
        </button>
      </div>
    </div>

    <!-- Confirmation Dialog -->
    <ConfirmDialog
      :open="showConfirm"
      :title="action === 'opt_in' ? 'Confirm WhatsApp Bulk Opt-In' : 'Confirm WhatsApp Bulk Opt-Out'"
      :message="confirmMessage"
      :confirm="action === 'opt_in' ? 'Confirm Opt In' : 'Confirm Opt Out'"
      cancel="Cancel"
      :tone="action === 'opt_in' ? 'primary' : 'danger'"
      :busy="isProcessing"
      :busy-label="progressLabel"
      @confirm="executeBulkConsent"
      @cancel="showConfirm = false"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { FeatherIcon, frappeRequest, toast } from 'frappe-ui'
import PageHeader from '@/shared/ui/PageHeader.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'
import { parseNumbers, chunkNumbers, sumConsentResults } from './consentHelpers.js'

// ── State ────────────────────────────────────────────────────────────────────
const action = ref('opt_in') // 'opt_in' | 'opt_out'
const inputTab = ref('paste') // 'paste' | 'upload'
const rawInput = ref('')
const uploadedFileName = ref('')
const fileError = ref('')
const isDragging = ref(false)
const fileInputRef = ref(null)

const isProcessing = ref(false)
const progressLabel = ref('Processing...')
const showConfirm = ref(false)
const hasRun = ref(false)
const result = ref({ updated: 0, not_found: 0, invalid: 0 })
const executedAction = ref('')

// ── Parsing & Chunks ─────────────────────────────────────────────────────────
const parsedNumbers = computed(() => parseNumbers(rawInput.value))

const previewNumbers = computed(() => parsedNumbers.value.slice(0, 15))

const batchCount = computed(() => Math.ceil(parsedNumbers.value.length / 5000) || 1)

const confirmMessage = computed(() => {
  const count = parsedNumbers.value.length.toLocaleString()
  const act = action.value === 'opt_in' ? 'Opted In' : 'Opted Out'
  return `Are you sure you want to set ${count} phone number(s) to ${act}? This will update the consent status of matching WhatsApp contacts.`
})

// ── File Upload ──────────────────────────────────────────────────────────────
function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(e) {
  const files = e.target?.files
  if (files && files.length > 0) {
    readFile(files[0])
  }
}

function handleFileDrop(e) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    readFile(files[0])
  }
}

function readFile(file) {
  fileError.value = ''
  if (!file) return

  const ext = file.name.split('.').pop().toLowerCase()
  if (!['csv', 'txt'].includes(ext)) {
    fileError.value = 'Please select a .csv or .txt file.'
    return
  }

  uploadedFileName.value = file.name
  const reader = new FileReader()
  reader.onload = (evt) => {
    const text = evt.target?.result || ''
    rawInput.value = text  // a new file replaces the previous content, as the drop zone says
  }
  reader.onerror = () => {
    fileError.value = 'Failed to read file.'
  }
  reader.readAsText(file)
}

function clearNumbers() {
  rawInput.value = ''
  uploadedFileName.value = ''
  fileError.value = ''
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function resetResults() {
  hasRun.value = false
  result.value = { updated: 0, not_found: 0, invalid: 0 }
}

// ── Submit Bulk Consent ──────────────────────────────────────────────────────
async function executeBulkConsent() {
  if (parsedNumbers.value.length === 0) return

  isProcessing.value = true
  progressLabel.value = 'Preparing batches...'

  try {
    const chunks = chunkNumbers(parsedNumbers.value, 5000)
    const chunkResults = []

    for (let i = 0; i < chunks.length; i++) {
      progressLabel.value = `Processing batch ${i + 1} of ${chunks.length}...`
      const res = await frappeRequest({
        url: '/api/method/msuite_whatsapp.api.v1.app.consent.bulk_set_whatsapp_consent',
        method: 'POST',
        params: {
          numbers: JSON.stringify(chunks[i]),
          action: action.value,
        },
      })
      const data = res?.message || res || {}
      chunkResults.push(data)
    }

    const total = sumConsentResults(chunkResults)
    result.value = total
    executedAction.value = action.value
    hasRun.value = true
    showConfirm.value = false

    // RULE: Never show success when updated is 0
    if (total.updated > 0) {
      toast.success(`Updated consent for ${total.updated.toLocaleString()} contact(s)`)
      if (window.frappe?.show_alert) {
        window.frappe.show_alert({
          message: `Consent updated for ${total.updated.toLocaleString()} contact(s).`,
          indicator: 'green',
        })
      }
    } else {
      toast.warning(
        `No contacts were updated (0 updated, ${total.not_found.toLocaleString()} not found, ${total.invalid.toLocaleString()} invalid)`
      )
      if (window.frappe?.show_alert) {
        window.frappe.show_alert({
          message: 'No contacts were updated.',
          indicator: 'orange',
        })
      }
    }
  } catch (err) {
    console.error('Bulk consent update failed:', err)
    toast.error(prettifyFrappeError(err) || 'Failed to update consent')
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: prettifyFrappeError(err) || 'Failed to update consent.',
        indicator: 'red',
      })
    }
  } finally {
    isProcessing.value = false
    progressLabel.value = 'Processing...'
  }
}
</script>

<style scoped>
.wa-page {
  width: 100%;
  padding: 0;
  font-family: var(--font-stack, system-ui, -apple-system, sans-serif);
  color: var(--ink-900, #0f172a);
}

.wa-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.wa-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.wa-subtitle {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--ink-500);
}

/* Results section */
.result-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 12px;
  border: 1px solid;
}
.result-alert-success {
  background: var(--status-green-bg, #ecfdf5);
  border-color: var(--status-green-border, #a7f3d0);
  color: var(--status-green-fg, #065f46);
}
.result-alert-warning {
  background: var(--status-amber-bg, #fffbeb);
  border-color: var(--status-amber-border, #fde68a);
  color: var(--status-amber-fg, #92400e);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}
.metric-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: var(--bg-surface, #fff);
  border: 1px solid var(--ink-100, #e2e8f0);
  border-radius: 14px;
  transition: border-color 0.15s, box-shadow 0.2s;
}
.metric-card:hover {
  border-color: var(--brand-100, #c7d2fe);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}
.metric-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-500);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.metric-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}
.metric-icon-bg {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* Consent Main Card */
.consent-card {
  background: var(--bg-surface, #fff);
  border: 1px solid var(--ink-100, #e2e8f0);
  border-radius: 14px;
  padding: 24px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.05));
}

.form-group {
  margin-bottom: 24px;
}
.form-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-600);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 8px;
}
.form-control {
  width: 100%;
  border: 1.5px solid var(--ink-100, #e2e8f0);
  border-radius: 10px;
  font-size: 14px;
  color: var(--ink-900);
  background: var(--bg-surface, #fff);
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.form-control:focus {
  border-color: var(--brand);
}
.form-textarea {
  height: auto;
  padding: 12px 14px;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}
.input-helper {
  font-size: 12px;
  color: var(--ink-400, #94a3b8);
  margin-top: 6px;
}

/* Action selection */
.action-toggle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.action-option {
  padding: 16px;
  border: 1.5px solid var(--ink-100, #e2e8f0);
  border-radius: 12px;
  cursor: pointer;
  background: var(--bg-surface, #fff);
  transition: all 0.15s ease;
}
.action-option:hover {
  border-color: var(--ink-200, #cbd5e1);
  background: var(--ink-25, #f8fafc);
}
.action-option.active {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-50, #eef2ff);
  box-shadow: 0 0 0 1px var(--brand, #4f46e5);
}
.action-option-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.action-icon-circle {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.opt-in-icon {
  background: var(--status-green-bg, #ecfdf5);
}
.opt-out-icon {
  background: var(--status-red-bg, #fef2f2);
}
.action-option-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--ink-900);
}
.action-option-desc {
  font-size: 12px;
  color: var(--ink-500);
  margin: 0;
  line-height: 1.4;
}

/* Tabs */
.tab-pill-group {
  display: flex;
  background: var(--ink-50, #f1f5f9);
  padding: 3px;
  border-radius: 8px;
  gap: 4px;
}
.tab-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-600);
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.tab-pill.active {
  background: var(--bg-surface, #fff);
  color: var(--brand, #4f46e5);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* Upload zone */
.upload-zone {
  margin-top: 4px;
}
.upload-drop-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 20px;
  border: 2px dashed var(--ink-100, #e2e8f0);
  border-radius: 12px;
  background: var(--ink-25, #f8fafc);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  text-align: center;
}
.upload-drop-area:hover,
.upload-drag-over {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-50, #eef2ff);
}
.upload-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-900);
  margin: 6px 0 2px;
}
.upload-desc {
  font-size: 12px;
  color: var(--ink-500);
  margin: 0;
}
.upload-formats {
  font-size: 11px;
  color: var(--ink-400);
  margin: 4px 0 0;
}
.hidden-file-input {
  display: none;
}
.upload-error {
  color: var(--status-red-fg);
  font-size: 12px;
  margin: 8px 0 0;
}

/* Preview box */
.preview-box {
  padding: 16px;
  border: 1px solid var(--ink-100, #e2e8f0);
  border-radius: 12px;
  background: var(--ink-25, #f8fafc);
  margin-bottom: 24px;
}
.summary-pill {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
.summary-total {
  background: var(--ink-100, #e2e8f0);
  color: var(--ink-700, #334155);
}
.summary-valid {
  background: var(--status-green-bg, #ecfdf5);
  color: var(--status-green-fg, #065f46);
}
.preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.preview-number-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: var(--bg-surface, #fff);
  border: 1px solid var(--ink-100, #e2e8f0);
  border-radius: 6px;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: var(--ink-700);
}
.preview-more-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: var(--ink-100);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--ink-600);
}

/* Footer buttons */
.consent-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--ink-100, #e2e8f0);
  gap: 16px;
  flex-wrap: wrap;
}

.btn-create {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  background: var(--brand, #4f46e5);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.05));
  transition: opacity 0.15s ease;
}
.btn-create:hover:not(:disabled) {
  opacity: 0.95;
}
.btn-create:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 16px;
  border: 1.5px solid var(--ink-100, #e2e8f0);
  border-radius: 10px;
  background: var(--bg-surface, #fff);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-600);
  cursor: pointer;
}
.btn-secondary:hover {
  border-color: var(--ink-200);
}
.btn-sm {
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
}
</style>
