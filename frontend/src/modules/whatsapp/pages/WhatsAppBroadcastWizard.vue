<!--
  WhatsAppBroadcastWizard — 5-step wizard for sending WhatsApp broadcasts.

  Steps:
  1. Brief:    Broadcast name, description, WABA account selection.
  2. Audience: Select a Recipient List OR enter individual phone numbers with validation.
  3. Template: Pick an approved template and map dynamic variables.
  4. Schedule: Choose to send immediately or at a scheduled date/time.
  5. Review:   Full summary before submission.
-->
<template>
  <WizardShell
    :title="route.query.draft ? 'Edit WhatsApp Broadcast' : 'New WhatsApp Broadcast'"
    subtitle="Design and schedule a personalized WhatsApp campaign"
    :back-to="route.query.parent_campaign ? { path: '/campaign', query: { name: route.query.parent_campaign } } : { name: 'WhatsAppBulkMessages' }"
    :back-label="route.query.parent_campaign ? 'Back to Campaign' : 'Back to Bulk Messages'"
    :steps="['Brief', 'Audience', 'Template', 'Schedule', 'Review']"
    :current-step="currentStep"
    :completed-steps="completedSteps"
    @step-select="onStepSelect"
  >
    <!-- ─── Step 0: Brief ─────────────────────────────────────── -->
        <div v-if="currentStep === 0" class="step-content">
          <h2 class="step-title">Broadcast Brief</h2>
          <p class="step-description">
            Give your broadcast a name, an optional description, and select which
            WhatsApp Business Account to send from.
          </p>

          <div class="brief-grid">
            <div class="form-group">
              <label class="form-label">
                Broadcast Name <span class="req-star">*</span>
              </label>
              <input
                type="text"
                class="form-input"
                v-model="broadcastTitle"
                placeholder="e.g. June Product Update"
              />
            </div>

            <div class="form-group">
              <label class="form-label">
                WhatsApp Business Account <span class="req-star">*</span>
              </label>
              <select class="form-select" v-model="selectedAccount">
                <option value="">Select account…</option>
                <option v-for="acc in wabaAccounts" :key="acc.name" :value="acc.name">
                  {{ acc.account_name || acc.name }}
                </option>
              </select>
              <p v-if="wabaAccounts.length === 0" class="field-hint">
                No accounts found. Please configure a WhatsApp account first.
              </p>
            </div>

            <div class="form-group full-width">
              <label class="form-label">
                Broadcast Description
                <span class="optional-tag">optional — internal note</span>
              </label>
              <textarea
                class="form-textarea"
                v-model="broadcastDescription"
                rows="5"
                placeholder="Describe the purpose of this broadcast…"
              />
            </div>
          </div>
        </div>

        <!-- ─── Step 1: Audience ──────────────────────────────────── -->
        <div v-else-if="currentStep === 1" class="step-content">
          <h2 class="step-title">Select Audience</h2>
          <p class="step-description">
            Choose a saved recipient list or manually enter phone numbers to target.
          </p>

          <!-- Mode toggle -->
          <div class="audience-toggle">
            <button
              class="toggle-btn"
              :class="{ active: audienceMode === 'list' }"
              @click="audienceMode = 'list'"
            >
              <FeatherIcon name="list" class="w-4 h-4" />
              Choose a Recipient List
            </button>
            <button
              class="toggle-btn"
              :class="{ active: audienceMode === 'numbers' }"
              @click="audienceMode = 'numbers'"
            >
              <FeatherIcon name="user-plus" class="w-4 h-4" />
              Enter Phone Numbers
            </button>
          </div>

          <!-- List mode -->
          <div v-if="audienceMode === 'list'" class="audience-section">
            <Shimmer v-if="store.recipientListsLoading" variant="lines" :count="2" />
            <div v-else-if="!store.recipientLists.length" class="empty-inline">
              <p>No recipient lists found.</p>
              <button
                class="btn-secondary mt-2"
                @click="$router.push({ name: 'WhatsAppRecipients' })"
              >
                Create Recipient List
              </button>
            </div>
            <div v-else>
              <div class="form-group">
                <label class="form-label">
                  Recipient List <span class="req-star">*</span>
                </label>
                <select
                  class="form-select"
                  v-model="selectedListName"
                  @change="onListSelect"
                >
                  <option value="">Select a recipient list…</option>
                  <option
                    v-for="list in store.recipientLists"
                    :key="list.name"
                    :value="list.name"
                  >
                    {{ list.list_name }} ({{ list.recipient_count || 0 }} recipients)
                  </option>
                </select>
              </div>

              <div v-if="selectedList" class="selected-list-card">
                <div class="slc-row">
                  <FeatherIcon name="users" class="w-4 h-4 slc-icon" />
                  <span class="slc-title">{{ selectedList.list_name }}</span>
                  <span class="slc-count">
                    {{ selectedList.recipient_count || 0 }} recipients
                  </span>
                </div>
                <p v-if="selectedList.description" class="slc-desc">
                  {{ selectedList.description }}
                </p>
              </div>

              <!-- Recipients preview table -->
              <div v-if="selectedList" class="list-preview">
                <div class="list-preview-header">
                  <span class="list-preview-title">Recipients Preview</span>
                  <span class="list-preview-sub">
                    Showing {{ listPreviewRows.length }} of {{ listPreviewTotal }}
                  </span>
                </div>

                <Shimmer v-if="listPreviewLoading" class="shm-pad" variant="rows" :count="5" />

                <template v-else>
                  <div class="list-preview-table-wrap">
                    <table class="list-preview-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Name</th>
                          <th>Mobile Number</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, i) in listPreviewRows" :key="row.name">
                          <td class="td-idx">{{ (listPreviewPage - 1) * 50 + i + 1 }}</td>
                          <td>{{ row.recipient_name || '—' }}</td>
                          <td class="td-mono">{{ row.mobile_number }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Pagination -->
                  <div v-if="listPreviewTotal > 50" class="list-preview-pager">
                    <button
                      class="pager-btn"
                      :disabled="listPreviewPage === 1"
                      @click="changePreviewPage(listPreviewPage - 1)"
                    >
                      <FeatherIcon name="chevron-left" class="w-4 h-4" />
                    </button>
                    <span class="pager-info">
                      Page {{ listPreviewPage }} / {{ Math.ceil(listPreviewTotal / 50) }}
                    </span>
                    <button
                      class="pager-btn"
                      :disabled="listPreviewPage * 50 >= listPreviewTotal"
                      @click="changePreviewPage(listPreviewPage + 1)"
                    >
                      <FeatherIcon name="chevron-right" class="w-4 h-4" />
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- Individual numbers mode -->
          <div v-else class="audience-section">
            <div class="form-group">
              <label class="form-label">
                Phone Numbers <span class="req-star">*</span>
              </label>
              <p class="field-hint">
                Type a number with country code, optionally a name, and press
                <kbd>Enter</kbd> or click <strong>Add</strong> to build your list. You can
                also paste multiple numbers separated by commas or newlines.
              </p>

              <!-- Single-entry row -->
              <div class="number-entry-row">
                <input
                  type="tel"
                  class="form-input"
                  v-model="singleNumberInput"
                  :placeholder="EXAMPLE_PHONE_HINT"
                  @keydown.enter.prevent="addSingleNumber"
                  @paste.prevent="onNumberPaste"
                />
                <input
                  type="text"
                  class="form-input name-input"
                  v-model="singleNameInput"
                  placeholder="Name (optional)"
                  aria-label="Recipient name (optional)"
                  @keydown.enter.prevent="addSingleNumber"
                />
                <button class="btn-add-number" @click="addSingleNumber">
                  + Add
                </button>
              </div>

              <!-- Inline validation error for last typed number -->
              <p v-if="numberInputError" class="number-input-error">
                {{ numberInputError }}
              </p>
            </div>

            <!-- Running count badge -->
            <div v-if="parsedNumbers.length > 0" class="numbers-count-bar">
              <span class="badge badge-green">
                <FeatherIcon name="check" class="w-3 h-3" />
                {{ validNumbers.length }} number{{ validNumbers.length === 1 ? '' : 's' }} added
              </span>
              <span v-if="invalidNumbers.length" class="badge badge-red">
                <FeatherIcon name="x" class="w-3 h-3" />
                {{ invalidNumbers.length }} invalid
              </span>
              <button class="btn-clear-all" @click="clearAllNumbers">Clear all</button>
            </div>

            <!-- Tag chips list -->
            <div v-if="parsedNumbers.length > 0" class="numbers-tags">
              <span
                v-for="(n, i) in parsedNumbers"
                :key="i"
                class="number-tag"
                :class="{ invalid: !n.valid }"
                :title="n.valid ? 'Valid' : 'Invalid — will not be sent'"
              >
                <FeatherIcon
                  :name="n.valid ? 'check' : 'alert-circle'"
                  class="w-3 h-3 tag-icon"
                />
                <strong v-if="n.name" class="tag-name">{{ n.name }}</strong>
                {{ n.number }}
                <button class="tag-remove" @click="removeNumber(i)">×</button>
              </span>
            </div>

            <p v-if="invalidNumbers.length" class="invalid-hint">
              <Icon name="alert-triangle" :size="14" class="ei" /> Invalid numbers will not be sent. Numbers must start with
              <code>+</code> followed by 7–15 digits (no spaces).
            </p>
          </div>
        </div>

        <!-- ─── Step 2: Template ──────────────────────────────────── -->
        <div v-else-if="currentStep === 2" class="step-content split-layout">
          <div class="layout-left">
            <h2 class="step-title">Select Message Template</h2>
            <p class="step-description">
              Showing approved templates for
              <strong>{{ selectedAccountLabel }}</strong>.
              Only templates belonging to the selected WhatsApp account are listed.
            </p>

            <div class="form-group">
              <label class="form-label">
                Template <span class="req-star">*</span>
              </label>
              <select
                class="form-select"
                v-model="selectedTemplateName"
                @change="onTemplateChange"
                :disabled="approvedTemplates.length === 0"
              >
                <option value="">
                  {{ approvedTemplates.length === 0
                    ? 'No approved templates for this account'
                    : 'Choose an approved template…' }}
                </option>
                <option
                  v-for="tpl in approvedTemplates"
                  :key="tpl.name"
                  :value="tpl.name"
                >
                  {{ tpl.template_name }} ({{ tpl.language || 'en' }})
                </option>
              </select>
              <p v-if="approvedTemplates.length === 0" class="field-hint text-[var(--status-amber-fg)]">
                <Icon name="alert-triangle" :size="14" class="ei" /> No approved templates found for <strong>{{ selectedAccountLabel }}</strong>.
                Go to <RouterLink :to="{ name: 'WhatsAppTemplates' }" class="link-inline">Templates</RouterLink>
                to create or sync templates for this account.
              </p>
            </div>

            <!-- Dynamic Variables Configuration -->
            <div v-if="templateVariables.length > 0" class="variables-section">
              <h3 class="section-title">Configure Dynamic Variables</h3>
              <p class="section-desc">
                Map each template variable to a recipient field or use fixed text.
              </p>

              <div
                v-for="(variable, idx) in templateVariables"
                :key="variable"
                class="variable-row"
              >
                <span class="variable-badge" :title="varToken(variable)">
                  {{ varToken(variable) }}
                </span>
                <div class="variable-inputs">
                  <select
                    class="form-select select-sm"
                    v-model="variableMappings[idx].type"
                  >
                    <option value="field">Map to Recipient Field</option>
                    <option value="static">Use Static Text</option>
                  </select>
                  <select
                    v-if="variableMappings[idx].type === 'field'"
                    class="form-select select-sm"
                    v-model="variableMappings[idx].value"
                  >
                    <option value="recipient_name">Recipient Name</option>
                    <option value="mobile_number">Mobile Number</option>
                    <option
                      v-for="key in recipientDataKeys"
                      :key="key"
                      :value="key"
                    >{{ key }}</option>
                  </select>
                  <input
                    v-else
                    type="text"
                    class="form-input input-sm"
                    v-model="variableMappings[idx].staticText"
                    placeholder="Enter static text…"
                  />
                </div>
              </div>
            </div>

            <!-- Offer options (expiry / coupon / tap link) — only when the template needs them -->
            <div v-if="selectedTemplate && offerLoading" class="field-hint">Checking offer options…</div>
            <div v-else-if="selectedTemplate && offerLoadError" class="field-hint text-[var(--status-amber-fg)]" role="alert">
              <Icon name="alert-triangle" :size="14" class="ei" /> {{ offerLoadError }}
              <button type="button" class="link-inline" @click="retryOfferRequirements">Retry</button>
            </div>
            <WhatsAppOfferOptions
              v-else-if="selectedTemplate && needsOffer"
              v-model="offerValues"
              :requirements="offerRequirements"
              :errors="offerErrors"
            />

            <!-- Commerce product selection (MPM / Product Carousel) -->
            <div v-if="isCommerceTemplate" class="variables-section">
              <h3 class="section-title">
                {{ isMpmTemplate ? 'Select Products (Multi-Product Message)' : 'Select Products (Carousel)' }}
              </h3>
              <p class="section-desc">
                {{ isMpmTemplate
                  ? 'Pick the products to list. The first selected product is used as the thumbnail.'
                  : 'Pick 2–10 products, one per carousel card.' }}
              </p>

              <div v-if="commerceCatalogs.length > 1" class="form-group">
                <label class="form-label">Catalog</label>
                <select class="form-select" v-model="selectedCatalog" @change="loadCommerceItems">
                  <option v-for="c in commerceCatalogs" :key="c.name" :value="c.name">
                    {{ c.catalog_name || c.catalog_id || c.name }}
                  </option>
                </select>
              </div>

              <!-- MPM Section Title Input (Meta max 24 chars) -->
              <div v-if="isMpmTemplate" class="form-group mb-3">
                <div class="flex items-center justify-between mb-1">
                  <label class="form-label text-xs font-semibold text-[var(--text-primary)]">
                    Section Title / Header
                  </label>
                  <span
                    class="text-[11px] font-mono"
                    :class="mpmHeader.length > 24 ? 'text-red-500 font-bold' : 'text-[var(--text-tertiary)]'"
                  >
                    {{ mpmHeader.length }}/24
                  </span>
                </div>
                <input
                  v-model="mpmHeader"
                  type="text"
                  maxlength="24"
                  class="form-input input-sm w-full"
                  placeholder="e.g. Our Products"
                />
                <p class="field-hint text-[11px] text-[var(--text-tertiary)] mt-1">
                  Title for this product section in WhatsApp (max 24 characters, up to 30 products across sections).
                </p>
              </div>

              <p v-if="!commerceCatalogs.length" class="field-hint text-[var(--status-amber-fg)]">
                <Icon name="alert-triangle" :size="14" class="ei" /> No Meta Product Catalog is attached to this WhatsApp account.
              </p>

              <input
                v-if="commerceCatalogs.length"
                v-model="productQuery"
                type="text"
                class="form-input input-sm mb-2 w-full"
                placeholder="Search items…"
              />
              <Shimmer v-if="loadingProducts" class="shm-pad" variant="rows" :count="5" />
              <div
                v-else-if="filteredProducts.length"
                class="border border-[var(--border)] rounded-lg divide-y divide-[var(--border-soft)] overflow-y-auto"
                style="max-height: 320px;"
              >
                <div
                  v-for="it in filteredProducts"
                  :key="it.item_code"
                  class="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-[var(--bg-sunken)]"
                  :class="isProductSelected(it) ? 'bg-[var(--bg-sunken)]' : ''"
                  @click="toggleProduct(it)"
                >
                  <img
                    v-if="it.image"
                    :src="it.image"
                    class="w-9 h-9 rounded object-cover shrink-0 border border-[var(--border-soft)]"
                    alt=""
                  />
                  <div
                    v-else
                    class="w-9 h-9 rounded shrink-0 bg-[var(--bg-sunken)] border border-[var(--border-soft)] flex items-center justify-center"
                  >
                    <FeatherIcon name="image" class="w-4 h-4 text-[var(--text-tertiary)]" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-medium text-[var(--text-primary)] truncate">
                      {{ it.item_name || it.item_code }}
                    </div>
                    <div class="text-[11px] text-[var(--text-tertiary)] truncate">{{ it.item_code }}</div>
                  </div>
                  <span
                    v-if="isProductSelected(it)"
                    class="text-[11px] font-semibold px-1.5 py-0.5 rounded shrink-0"
                    :class="isMpmTemplate && selectedProducts[0] === it.item_code
                      ? 'text-[var(--text-on-brand)] bg-[var(--brand)]'
                      : 'text-[var(--brand)] bg-[var(--brand-subtle,rgba(37,99,235,0.12))]'"
                  >
                    {{ isMpmTemplate && selectedProducts[0] === it.item_code ? 'Thumbnail' : 'Selected' }}
                  </span>
                </div>
              </div>
              <p v-else-if="commerceCatalogs.length" class="section-desc">No items match.</p>

              <p class="section-desc mt-2">
                {{ selectedProducts.length }} selected{{ isMpmTemplate ? ' (1–30)' : ' (2–10)' }}
              </p>
            </div>
          </div>

          <!-- WhatsApp Preview (right column) -->
          <div class="layout-right">
            <div class="phone-preview-container">
              <div class="phone-header">
                <div class="phone-avatar">
                  <FeatherIcon name="message-circle" class="w-5 h-5 text-white" />
                </div>
                <div class="phone-header-info">
                  <span class="phone-sender-name">MSuite WhatsApp</span>
                  <span class="phone-sender-status">Online</span>
                </div>
              </div>
              <div class="phone-chat-bg">
                <div v-if="selectedTemplate" class="whatsapp-bubble">
                  <div v-if="selectedTemplate.header" class="bubble-header">
                    {{ selectedTemplate.header }}
                  </div>
                  <div class="bubble-body" v-html="renderedBody"></div>
                  <div v-if="selectedTemplate.footer" class="bubble-footer">
                    {{ selectedTemplate.footer }}
                  </div>
                  <div
                    v-if="selectedTemplate.buttons && selectedTemplate.buttons.length"
                    class="bubble-buttons"
                  >
                    <div
                      v-for="(btn, bidx) in selectedTemplate.buttons"
                      :key="bidx"
                      class="bubble-btn"
                    >
                      <FeatherIcon name="external-link" class="w-3 h-3" />
                      <span>{{ btn.button_label || btn.label || 'Button' }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="preview-empty">
                  <FeatherIcon name="smartphone" class="w-12 h-12 text-[var(--text-tertiary)]" />
                  <p>Select a template to preview</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ─── Step 3: Schedule ──────────────────────────────────── -->
        <div v-else-if="currentStep === 3" class="step-content">
          <h2 class="step-title">Scheduling Settings</h2>
          <p class="step-description">
            Choose when to send your bulk WhatsApp messages.
          </p>

          <div class="schedule-options">
            <div
              class="picker-card"
              :class="{ active: sendMode === 'now' }"
              @click="sendMode = 'now'"
            >
              <div class="picker-card-header">
                <div class="picker-card-title">Send Immediately</div>
                <span class="radio-dot" :class="{ filled: sendMode === 'now' }"></span>
              </div>
              <p class="picker-card-desc">
                Messages will be queued and sent right after you finish the wizard.
              </p>
            </div>

            <div
              class="picker-card"
              :class="{ active: sendMode === 'later' }"
              @click="sendMode = 'later'"
            >
              <div class="picker-card-header">
                <div class="picker-card-title">Schedule for Later</div>
                <span class="radio-dot" :class="{ filled: sendMode === 'later' }"></span>
              </div>
              <p class="picker-card-desc">
                Select a specific date and time to start sending the campaign.
              </p>

              <div v-if="sendMode === 'later'" class="schedule-inputs" @click.stop>
                <div class="form-group">
                  <label class="form-label label-sm">Date &amp; Time</label>
                  <input
                    type="datetime-local"
                    class="form-input"
                    v-model="scheduledDateTime"
                    :min="minDateTime"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ─── Step 4: Review ────────────────────────────────────── -->
        <div v-else-if="currentStep === 4" class="step-content split-layout">
          <div class="layout-left">
            <h2 class="step-title">Review &amp; Submit Campaign</h2>
            <p class="step-description">
              Verify all information before starting the WhatsApp broadcast.
            </p>

            <div class="summary-details">
              <!-- Brief summary -->
              <div class="summary-section-title">Brief</div>
              <div class="summary-row">
                <span class="summary-label">Broadcast Name</span>
                <span class="summary-value font-semibold">{{ broadcastTitle }}</span>
              </div>
              <div v-if="broadcastDescription" class="summary-row">
                <span class="summary-label">Description</span>
                <span class="summary-value text-[var(--text-secondary)]">{{ broadcastDescription }}</span>
              </div>
              <div class="summary-row">
                <span class="summary-label">WhatsApp Account</span>
                <span class="summary-value">{{ selectedAccountLabel }}</span>
              </div>

              <!-- Audience summary -->
              <div class="summary-section-title">Audience</div>
              <div class="summary-row">
                <span class="summary-label">Audience Type</span>
                <span class="summary-value">
                  {{ audienceMode === 'list' ? 'Recipient List' : 'Individual Numbers' }}
                </span>
              </div>
              <div class="summary-row">
                <span class="summary-label">Recipients</span>
                <span class="summary-value font-semibold text-[var(--text-primary)]">
                  <template v-if="audienceMode === 'list'">
                    {{ selectedList?.list_name || '—' }}
                    ({{ selectedListCount }} recipient{{ selectedListCount === 1 ? '' : 's' }})
                  </template>
                  <template v-else>
                    {{ validNumbers.length }} phone number{{ validNumbers.length === 1 ? '' : 's' }}
                  </template>
                </span>
              </div>

              <!-- Template summary -->
              <div class="summary-section-title">Template</div>
              <div class="summary-row">
                <span class="summary-label">Selected Template</span>
                <span class="summary-value text-[var(--status-violet-fg)] font-medium">
                  {{ selectedTemplate?.template_name || '—' }}
                </span>
              </div>
              <div v-if="offerSummary" class="summary-row">
                <span class="summary-label">Offer</span>
                <span class="summary-value text-[var(--text-primary)]">{{ offerSummary }}</span>
              </div>

              <!-- Schedule summary -->
              <div class="summary-section-title">Schedule</div>
              <div class="summary-row">
                <span class="summary-label">Send Time</span>
                <span class="summary-value text-[var(--text-primary)]">
                  {{ sendMode === 'now' ? 'Immediately after submission' : formatDate(scheduledDateTime) }}
                </span>
              </div>
            </div>

            <div class="alert-box bg-[var(--status-blue-bg)] border-[var(--status-blue-bg)] text-[var(--status-blue-fg)]">
              <FeatherIcon name="info" class="w-4 h-4 flex-shrink-0" />
              <p class="text-xs">
                Make sure your WhatsApp account is connected and in good standing.
                Messages already handed to WhatsApp can't be recalled, but you can
                pause or cancel the remaining sends from the Bulk Messages page.
              </p>
            </div>
          </div>

          <!-- Phone preview -->
          <div class="layout-right">
            <div class="phone-preview-container">
              <div class="phone-header">
                <div class="phone-avatar">
                  <FeatherIcon name="message-circle" class="w-5 h-5 text-white" />
                </div>
                <div class="phone-header-info">
                  <span class="phone-sender-name">MSuite WhatsApp</span>
                  <span class="phone-sender-status">Online</span>
                </div>
              </div>
              <div class="phone-chat-bg">
                <div v-if="selectedTemplate" class="whatsapp-bubble">
                  <div v-if="selectedTemplate.header" class="bubble-header">
                    {{ selectedTemplate.header }}
                  </div>
                  <div class="bubble-body" v-html="renderedBody"></div>
                  <div v-if="selectedTemplate.footer" class="bubble-footer">
                    {{ selectedTemplate.footer }}
                  </div>
                  <div
                    v-if="selectedTemplate.buttons && selectedTemplate.buttons.length"
                    class="bubble-buttons"
                  >
                    <div
                      v-for="(btn, bidx) in selectedTemplate.buttons"
                      :key="bidx"
                      class="bubble-btn"
                    >
                      <FeatherIcon name="external-link" class="w-3 h-3" />
                      <span>{{ btn.button_label || btn.label || 'Button' }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="preview-empty">
                  <FeatherIcon name="smartphone" class="w-12 h-12 text-[var(--text-tertiary)]" />
                  <p>No template selected</p>
                </div>
              </div>
            </div>
          </div>
        </div>

      <template #footer-left>
        <button
          class="l-btn l-btn--secondary"
          :disabled="currentStep === 0 || isSubmitting || isSavingDraft"
          @click="prevStep"
        >
          Back
        </button>
      </template>

      <template #footer-right>
        <button
          type="button"
          class="l-btn l-btn--secondary"
          :disabled="isSubmitting || isSavingDraft"
          @click="onSaveDraft"
          title="Save draft"
        >
          <LLoader inline :size="18" v-if="isSavingDraft" />
          <FeatherIcon v-else name="bookmark" class="w-3.5 h-3.5" />
          <span>{{ isSavingDraft ? 'Saving…' : 'Save Draft' }}</span>
        </button>

        <button
          v-if="currentStep < 4"
          class="l-btn l-btn--primary"
          :disabled="!canContinue || isSubmitting || isSavingDraft"
          @click="nextStep"
        >
          Continue
        </button>
        <button
          v-else
          class="l-btn l-btn--primary"
          :disabled="isSubmitting || isSavingDraft || offerBlocked"
          @click="confirmOpen = true"
        >
          {{ isSubmitting
            ? 'Scheduling…'
            : (sendMode === 'now' ? 'Send Broadcast Now' : 'Schedule Broadcast') }}
        </button>
      </template>
    </WizardShell>

    <ConfirmDialog
      :open="confirmOpen"
      :title="sendMode === 'now' ? 'Send this broadcast now?' : 'Schedule this broadcast?'"
      :message="confirmMessage"
      :confirm="sendMode === 'now' ? 'Send now' : 'Schedule'"
      tone="danger"
      :busy="isSubmitting"
      @confirm="onConfirmSend"
      @cancel="confirmOpen = false"
    />
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { FeatherIcon, toast } from 'frappe-ui'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import WizardShell from '@/shared/ui/WizardShell.vue'
import Stepper from '@/shared/ui/Stepper.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { callRpc } from '@/services/_factory'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'
import { validateMpmSectionTitle, MPM_LIMITS } from '../utils/mpmHelper'
import WhatsAppOfferOptions from '@/shared/ui/WhatsAppOfferOptions.vue'
import {
  buildOfferFields, emptyOfferValues, getSiteTimeZone, offerSummaryText,
  offerValuesFromDoc, sanitizeOfferValues, validateOffer, validateOfferSchedule,
} from '@/shared/ui/whatsappOffer.js'
import { useTemplateOfferRequirements } from '@/shared/ui/useTemplateOfferRequirements.js'
import { EXAMPLE_PHONE_HINT } from '@/shared/constants/inputExamples'
import { previewLabelFor } from '@/shared/utils/previewValues'
import { isAppInstalled } from '@/shared/store/installedApps'

const store = useWhatsApp()
const router = useRouter()
const route = useRoute()

// ────────────────────────────────────────────────────────────
// Stepper
// ────────────────────────────────────────────────────────────
const currentStep = ref(0)

// ────────────────────────────────────────────────────────────
// Step 0 — Brief
// ────────────────────────────────────────────────────────────
const broadcastTitle      = ref('')
const broadcastDescription = ref('')
const selectedAccount     = ref('')
const wabaAccounts        = ref([])

const selectedAccountLabel = computed(() => {
  if (!selectedAccount.value) return '—'
  const acc = wabaAccounts.value.find(a => a.name === selectedAccount.value)
  return acc ? (acc.account_name || acc.name) : selectedAccount.value
})

// ────────────────────────────────────────────────────────────
// Step 1 — Audience
// ────────────────────────────────────────────────────────────
const audienceMode     = ref('list') // 'list' | 'numbers'

// — List sub-mode —
const selectedListName    = ref('')
const selectedList        = ref(null)
const recipientDataKeys   = ref([])
const listPreviewRows     = ref([])
const listPreviewTotal    = ref(0)
const listPreviewLoading  = ref(false)
const listPreviewPage     = ref(1)

function onListSelect() {
  const list = store.recipientLists.find(l => l.name === selectedListName.value)
  selectedList.value = list || null
  listPreviewPage.value = 1
  listPreviewRows.value = []
  listPreviewTotal.value = 0
  if (list) {
    loadRecipientDataKeys(list.name)
    fetchListPreview(list.name, 1)
  }
}

async function fetchListPreview(listName, page = 1) {
  if (!listName) return
  listPreviewLoading.value = true
  try {
    const res = await callRpc(
      'msuite_whatsapp.api.v1.app.crud.list_recipients',
      { list_name: listName, start: (page - 1) * 50, page_length: 50 }
    )
    listPreviewRows.value  = res?.rows  || []
    listPreviewTotal.value = res?.total || 0
    listPreviewPage.value  = page
  } catch (e) {
    console.error('Failed to load recipients preview', e)
  } finally {
    listPreviewLoading.value = false
  }
}

function changePreviewPage(page) {
  if (selectedList.value) fetchListPreview(selectedList.value.name, page)
}

const selectedListCount = computed(() => selectedList.value?.recipient_count || 0)

async function loadRecipientDataKeys(listName) {
  recipientDataKeys.value = []
  try {
    const keys = await callRpc(
      'msuite_whatsapp.api.v1.app.bulk_messaging.get_recipient_data_keys',
      { list_name: listName }
    )
    recipientDataKeys.value = (keys || []).filter(
      k => k !== 'recipient_name' && k !== 'mobile_number'
    )
  } catch (e) {
    console.error('Failed to load recipient data keys', e)
  }
}

// — Individual numbers sub-mode —
const singleNumberInput = ref('')
const numberInputError  = ref('')
const singleNameInput   = ref('')
const parsedNumbers     = ref([])   // [{ number: string, valid: boolean, name: string }]

const validNumbers   = computed(() => parsedNumbers.value.filter(n => n.valid).map(n => n.number))
const invalidNumbers = computed(() => parsedNumbers.value.filter(n => !n.valid))

function isValidPhone(num) {
  // E.164: + followed by 7–15 digits, no spaces
  return /^\+[1-9]\d{6,14}$/.test(num.trim())
}

// Strip spaces/dashes/brackets/dots so phone numbers are normalised,
// and compare on digits only so duplicates count once.
const digitsOf = num => num.replace(/\D/g, '')

function pushNumber(raw, name = '') {
  const number = raw.replace(/[\s\-().]/g, '')
  if (!number || parsedNumbers.value.some(n => digitsOf(n.number) === digitsOf(number))) return false
  parsedNumbers.value.push({ number, valid: isValidPhone(number), name: name.trim() })
  return true
}

function addSingleNumber() {
  numberInputError.value = ''
  const raw = singleNumberInput.value.trim()
  if (!raw) return

  // Support pasting comma/newline list via the text field
  const parts = raw.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)

  let added = 0
  for (const part of parts) {
    // A name only makes sense for a single typed number, not a pasted batch.
    if (pushNumber(part, parts.length === 1 ? singleNameInput.value : '')) added++
  }

  if (added === 0 && parts.length === 1) {
    numberInputError.value = 'This number is already in the list.'
  } else if (!isValidPhone(parts[0]) && parts.length === 1) {
    // Already added but flag it — error shown via tag color
    numberInputError.value = ''
  }

  singleNumberInput.value = ''
  if (added) singleNameInput.value = ''
  saveState()
}

function onNumberPaste(event) {
  numberInputError.value = ''
  const text = event.clipboardData?.getData('text') || ''
  const parts = text.split(/[\n,;\t]+/).map(s => s.trim()).filter(Boolean)
  for (const part of parts) {
    pushNumber(part)
  }
  singleNumberInput.value = ''
  saveState()
}

function removeNumber(index) {
  parsedNumbers.value.splice(index, 1)
  saveState()
}

function clearAllNumbers() {
  parsedNumbers.value = []
  singleNumberInput.value = ''
  singleNameInput.value = ''
  numberInputError.value = ''
  saveState()
}

// ────────────────────────────────────────────────────────────
// Step 2 — Template
// ────────────────────────────────────────────────────────────
const approvedTemplates   = ref([])
const selectedTemplateName = ref('')
const selectedTemplate     = ref(null)
const templateVariables    = ref([])
const variableMappings     = ref([])

// Offer options (expiry / coupon / tap link) for templates that need them.
const offerValues = ref(emptyOfferValues())
const {
  requirements: offerRequirements, loading: offerLoading, error: offerLoadError,
  needsOffer, load: loadOfferRequirements, retry: retryOfferRequirements, reset: resetOfferRequirements,
} = useTemplateOfferRequirements()

// Purpose: forget offer values and requirements (template deselected / switched).
function clearOffer() {
  offerValues.value = emptyOfferValues()
  resetOfferRequirements()
}

async function fetchApprovedTemplates() {
  approvedTemplates.value = []
  try {
    // Build filters: always require APPROVED status
    const filters = [['status', '=', 'APPROVED']]
    // If a WABA account is selected, restrict to templates belonging to it
    if (selectedAccount.value) {
      filters.push(['whatsapp_account', '=', selectedAccount.value])
    }
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_templates', {
      filters: JSON.stringify(filters),
      limit: 500,
    })
    approvedTemplates.value = res?.rows || []
  } catch (e) {
    console.error('Failed to fetch approved templates', e)
    toast.error(prettifyFrappeError(e) || 'Failed to fetch approved templates')
  }
}

function varToken(v) { return '{{' + v + '}}' }

function extractVariables(bodyText) {
  const names = []
  const re = /\{\{(\w+)\}\}/g
  let m
  while ((m = re.exec(bodyText || '')) !== null) {
    if (!names.includes(m[1])) names.push(m[1])
  }
  return names
}

// Purpose: load the picked template, extract its {{variables}}, and (for MPM/product
// carousels) preload the catalog so the product picker can render.
// WhatsApp-only: yes — part of the WhatsApp broadcast wizard.
async function onTemplateChange() {
  clearOffer()
  if (!selectedTemplateName.value) {
    selectedTemplate.value = null
    templateVariables.value = []
    variableMappings.value  = []
    return
  }
  try {
    const tpl = await callRpc(
      'msuite_whatsapp.api.v1.app.crud.get_whatsapp_template',
      { name: selectedTemplateName.value }
    )
    selectedTemplate.value = tpl
    loadOfferRequirements(selectedTemplateName.value)
    const vars = extractVariables(tpl.template)
    templateVariables.value = vars
    variableMappings.value  = vars.map(() => ({
      type: 'field',
      value: 'recipient_name',
      staticText: '',
    }))
    selectedProducts.value = []
    if (isCommerceTemplate.value) await loadCommerceCatalogs()
  } catch (e) {
    console.error('Failed to load template', e)
  }
}

// ── Commerce (MPM / Product Carousel) product selection ──────────────
const isMpmTemplate = computed(() => selectedTemplate.value?.template_type === 'MPM')
const isCarouselTemplate = computed(() => !!selectedTemplate.value?.is_carousel)
// Only PRODUCT-header carousels need a catalog + product picker. Media Card
// Carousels (IMAGE/VIDEO headers) carry their own media in the template.
const isProductCarousel = computed(() =>
  isCarouselTemplate.value &&
  (selectedTemplate.value?.carousel_cards || []).some((c) => c.header_format === 'PRODUCT')
)
const isCommerceTemplate = computed(() => isMpmTemplate.value || isProductCarousel.value)

const commerceCatalogs = ref([])
const selectedCatalog  = ref('')   // Meta Product Catalog doc name
const commerceItems    = ref([])
const selectedProducts = ref([])   // item_codes, selection order preserved
const mpmHeader        = ref('Our Products')
const productQuery     = ref('')
const loadingProducts  = ref(false)

const filteredProducts = computed(() => {
  const q = productQuery.value.trim().toLowerCase()
  if (!q) return commerceItems.value
  return commerceItems.value.filter(
    (it) => (it.item_name || '').toLowerCase().includes(q) || (it.item_code || '').toLowerCase().includes(q)
  )
})

const commerceSelectionValid = computed(() => {
  if (!isCommerceTemplate.value) return true
  const n = selectedProducts.value.length
  if (isMpmTemplate.value) {
    const titleValid = validateMpmSectionTitle(mpmHeader.value).valid
    return n >= 1 && n <= 30 && titleValid
  }
  return n >= 2 && n <= 10 && !!selectedCatalog.value
})

// Purpose: fetch the Meta Product Catalogs linked to the selected WhatsApp account,
// pick the first, and load its products.
// WhatsApp-only: yes — scopes catalogs by the wizard's WhatsApp account.
async function loadCommerceCatalogs() {
  if (!isAppInstalled('msuite_commerce')) return
  const rows = await callRpc('msuite_commerce.meta_ecommerce.api.v1.catalog.list_catalogs',
    selectedAccount.value ? { whatsapp_account: selectedAccount.value } : {})
  commerceCatalogs.value = rows || []
  selectedCatalog.value = commerceCatalogs.value[0]?.name || ''
  if (selectedCatalog.value) await loadCommerceItems()
}

// Purpose: load the products of the currently-selected catalog into the picker.
// WhatsApp-only: yes — feeds the MPM/product-carousel selection UI.
async function loadCommerceItems() {
  if (!selectedCatalog.value) return
  loadingProducts.value = true
  selectedProducts.value = []
  try {
    const catalogId = commerceCatalogs.value.find((c) => c.name === selectedCatalog.value)?.catalog_id
    const rows = await callRpc('msuite_commerce.meta_ecommerce.api.v1.catalog.list_catalog_products', {
      whatsapp_account: selectedAccount.value || undefined,
      catalog_id: catalogId || undefined,
    })
    commerceItems.value = rows || []
  } finally {
    loadingProducts.value = false
  }
}

// Purpose: whether a catalog product is currently selected.
// WhatsApp-only: yes — product picker state for the WhatsApp broadcast.
function isProductSelected(it) {
  return selectedProducts.value.includes(it.item_code)
}

// Purpose: toggle a product in/out of the selection (order preserved; first = MPM thumbnail).
// WhatsApp-only: yes — product picker state for the WhatsApp broadcast.
function toggleProduct(it) {
  const i = selectedProducts.value.indexOf(it.item_code)
  if (i >= 0) {
    selectedProducts.value.splice(i, 1)
  } else {
    const maxLimit = isMpmTemplate.value ? MPM_LIMITS.MAX_PRODUCTS : 10
    if (selectedProducts.value.length >= maxLimit) {
      toast.warning(`Cannot select more than ${maxLimit} products.`)
      return
    }
    selectedProducts.value.push(it.item_code)
  }
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const renderedBody = computed(() => {
  if (!selectedTemplate.value) return ''
  let body = escapeHtml(selectedTemplate.value.template || '')
  variableMappings.value.forEach((mapping, idx) => {
    const varName = templateVariables.value[idx]
    if (!varName) return
    let replacement = `[${varName}]`
    if (mapping.type === 'static') {
      replacement = mapping.staticText || `[${varName}]`
    } else if (mapping.type === 'field') {
      replacement = previewLabelFor(mapping.value) || `[${mapping.value}]`
    }
    const safeReplacement = escapeHtml(replacement)
    body = body.replace(
      new RegExp(`\\{\\{${varName}\\}\\}`, 'g'),
      `<strong>${safeReplacement}</strong>`
    )
  })
  return body.replace(/\n/g, '<br>')
})

// ────────────────────────────────────────────────────────────
// Step 3 — Schedule
// ────────────────────────────────────────────────────────────
const sendMode         = ref('now')
const scheduledDateTime = ref('')

const minDateTime = computed(() => {
  const now = new Date()
  now.setMinutes(now.getMinutes() + 5)
  return now.toISOString().slice(0, 16)
})

// ────────────────────────────────────────────────────────────
// Step 4 — Review / Submit
// ────────────────────────────────────────────────────────────
const isSubmitting = ref(false)
const isSavingDraft = ref(false)
// Name of the draft this wizard saved, so later saves/sends update it (BUG-021).
const draftDocName = ref('')
const confirmOpen  = ref(false)

const confirmMessage = computed(() => {
  const count =
    audienceMode.value === 'list'
      ? `${selectedListCount.value} recipient${selectedListCount.value === 1 ? '' : 's'} in '${selectedList.value?.list_name || ''}'`
      : `${validNumbers.value.length} individual number${validNumbers.value.length === 1 ? '' : 's'}`
  return `This will message ${count} using the '${selectedTemplate.value?.template_name || ''}' template. This can't be cancelled once sending starts.`
})

// ────────────────────────────────────────────────────────────
// canContinue & completedSteps (5 steps)
// ────────────────────────────────────────────────────────────
const siteTimeZone = getSiteTimeZone()

// Offer field errors (format, required, past expiry, expiry before the scheduled start).
const offerErrors = computed(() => {
  const errors = validateOffer(offerRequirements.value, offerValues.value, Date.now(), siteTimeZone)
  if (!errors.expiresAt && sendMode.value === 'later' && offerValues.value.expiresAt) {
    const conflict = validateOfferSchedule(offerValues.value.expiresAt, scheduledDateTime.value)
    if (conflict) errors.expiresAt = conflict
  }
  return errors
})
// A failed requirements fetch also blocks (Retry is shown) so mandatory offer fields cannot be skipped.
const offerBlocked = computed(() => offerLoading.value || !!offerLoadError.value || Object.keys(offerErrors.value).length > 0)
const offerSummary = computed(() => (needsOffer.value ? offerSummaryText(offerValues.value) : ''))

const canContinue = computed(() => {
  if (currentStep.value === 0) return !!(broadcastTitle.value.trim() && selectedAccount.value)
  if (currentStep.value === 1) {
    return audienceMode.value === 'list'
      ? !!selectedList.value
      : validNumbers.value.length > 0
  }
  if (currentStep.value === 2) return !!selectedTemplate.value && commerceSelectionValid.value && !offerBlocked.value
  if (currentStep.value === 3) return (sendMode.value === 'now' || !!scheduledDateTime.value) && !offerBlocked.value
  return true
})

const completedSteps = computed(() => [
  !!(broadcastTitle.value.trim() && selectedAccount.value),
  audienceMode.value === 'list' ? !!selectedList.value : validNumbers.value.length > 0,
  !!selectedTemplate.value,
  sendMode.value === 'now' || !!scheduledDateTime.value,
  false,
])

// ────────────────────────────────────────────────────────────
// Navigation helpers
// ────────────────────────────────────────────────────────────
function prevStep() {
  if (currentStep.value > 0) currentStep.value--
}

function nextStep() {
  if (canContinue.value && currentStep.value < 4) currentStep.value++
}

function onStepSelect(index) {
  if (index < currentStep.value) {
    currentStep.value = index
  } else {
    let allowed = true
    for (let i = 0; i < index; i++) {
      if (!completedSteps.value[i]) allowed = false
    }
    if (allowed) currentStep.value = index
  }
}

function goBack() {
  const parentCampaign = route.query.parent_campaign
  if (parentCampaign) {
    router.push({ path: '/campaign', query: { name: parentCampaign } })
    return
  }
  router.push({ name: 'WhatsAppBulkMessages' })
}

// ────────────────────────────────────────────────────────────
// Payload serialization & submit
// ────────────────────────────────────────────────────────────
function serializeVariableMappings() {
  if (!variableMappings.value.length) return ''
  return JSON.stringify(
    variableMappings.value.map(m =>
      m.type === 'static'
        ? { mode: 'common', value: m.staticText || '' }
        : { mode: 'unique', key: m.value }
    )
  )
}

async function onConfirmSend() {
  await submitBroadcast()
  confirmOpen.value = false
}

// Purpose: the Bulk WhatsApp Message payload shared by Save Draft and Send.
// Fields that only apply to some choices start blank, so re-saving an existing
// draft clears values from a choice the user switched away from.
function buildBroadcastDoc() {
  const doc = {
    doctype: 'Bulk WhatsApp Message',
    title: broadcastTitle.value.trim(),
    description: broadcastDescription.value.trim(),
    whatsapp_account: selectedAccount.value || undefined,
    delivery_engine: 'AWS',
    template: selectedTemplate.value?.name || null,
    template_variables: serializeVariableMappings(),
    scheduled_time:
      sendMode.value === 'later' && scheduledDateTime.value
        ? scheduledDateTime.value.replace('T', ' ')
        : null,
    campaign: route.query.parent_campaign || undefined,
    recipient_list: null,
    recipients: [],
    product_ids: [],
    is_mpm: 0,
    thumbnail_product_retailer_id: null,
    carousel_catalog: null,
    // Blank offer fields are sent (as null) only when updating a draft, so a
    // template switch clears stale values; plain new sends stay unchanged.
    ...buildOfferFields(offerValues.value, { includeEmpty: !!draftDocName.value }),
  }

  if (isCommerceTemplate.value && selectedProducts.value.length) {
    doc.product_ids = selectedProducts.value.map((code) => ({
      doctype: 'Bulk WhatsApp Message Product',
      item_code: code,
    }))
    if (isMpmTemplate.value) {
      doc.is_mpm = 1
      doc.thumbnail_product_retailer_id = selectedProducts.value[0]
      doc.mpm_header = (mpmHeader.value || '').trim() || 'Our Products'
    } else {
      // Product Carousel: is_carousel_template is auto-fetched from the template;
      // the send needs the source Meta Product Catalog.
      doc.carousel_catalog = selectedCatalog.value
    }
  }

  if (audienceMode.value === 'list') {
    doc.recipient_type = 'Recipient List'
    doc.recipient_list = selectedList.value?.name || null
  } else {
    doc.recipient_type = 'Individual'
    doc.recipients = parsedNumbers.value.filter(n => n.valid).map(n => ({
      doctype: 'WhatsApp Recipient',
      mobile_number: n.number,
      recipient_name: n.name || null,
    }))
  }
  return doc
}

// Purpose: build the Bulk WhatsApp Message doc (adding MPM/carousel product fields when
// applicable) and submit it to start/schedule the broadcast.
// WhatsApp-only: yes — creates a WhatsApp bulk broadcast.
async function submitBroadcast() {
  if (offerBlocked.value) return
  isSubmitting.value = true
  try {
    const doc = buildBroadcastDoc()

    // Pass the saved draft (if any) so sending submits it instead of
    // creating a second broadcast next to it.
    await callRpc('msuite_whatsapp.api.v1.app.crud.insert_bulk_message', {
      doc: JSON.stringify(doc),
      submit: 1,
      name: draftDocName.value || undefined,
    })

    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: sendMode.value === 'now' ? 'Broadcast sending queued.' : 'Broadcast scheduled.',
        indicator: 'green',
      })
    }

    await store.fetchBulkMessages()
    await store.fetchBulkMetrics()

    // Clear persisted draft now that it's submitted
    draftDocName.value = ''
    clearState()

    const parentCampaign = route.query.parent_campaign
    if (parentCampaign) {
      router.push({ path: '/campaign', query: { name: parentCampaign } })
    } else {
      router.push({ name: 'WhatsAppBulkMessages' })
    }
  } catch (e) {
    console.error('Failed to create broadcast', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: e?.messages?.[0] || e?.message || 'Failed to create broadcast.',
        indicator: 'red',
      })
    }
  } finally {
    isSubmitting.value = false
  }
}

async function onSaveDraft() {
  if (!broadcastTitle.value.trim()) {
    toast.warning('Please enter a Broadcast Name in Step 1 (Brief) to save a draft.')
    currentStep.value = 0
    return
  }

  const enteredOfferErrors = Object.keys(offerErrors.value).filter((key) => offerValues.value[key])
  if (enteredOfferErrors.length) {
    toast.error(offerErrors.value[enteredOfferErrors[0]])
    return
  }
  isSavingDraft.value = true
  try {
    saveState()

    // BUG-021 follow-up: save to the database from any step (Brief included);
    // an incomplete draft is allowed and fully validated when it's sent.
    const doc = buildBroadcastDoc()

    // BUG-021: first save inserts, later saves update the same draft.
    const saved = await callRpc('msuite_whatsapp.api.v1.app.crud.insert_bulk_message', {
      doc: JSON.stringify(doc),
      submit: 0,
      name: draftDocName.value || undefined,
    })
    draftDocName.value = saved?.name || draftDocName.value
    saveState()

    await store.fetchBulkMessages()
    await store.fetchBulkMetrics()
    toast.success('Draft saved.')
  } catch (e) {
    console.error('Failed to save draft:', e)
    toast.error(prettifyFrappeError(e) || 'Failed to save draft.')
  } finally {
    isSavingDraft.value = false
  }
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ────────────────────────────────────────────────────────────
// Data loaders
// ────────────────────────────────────────────────────────────
async function fetchWabaAccounts() {
  try {
    const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_waba_accounts')
    wabaAccounts.value = res || []
  } catch (e) {
    console.error('Failed to fetch WhatsApp accounts', e)
  }
}

// Prefill the wizard from an existing broadcast: ?duplicate=<name> starts a
// copy; ?draft=<name> reopens that draft so saves/send update it in place.
// True while prefillFromBroadcast restores account + template, so the
// account watcher below doesn't wipe the template it just loaded.
let prefilling = false

async function prefillFromBroadcast(sourceName, { asCopy }) {
  prefilling = true
  try {
    const src = await callRpc(
      'msuite_whatsapp.api.v1.app.crud.get_bulk_message',
      { name: sourceName }
    )
    if (!src) return
    if (!asCopy && src.docstatus !== 0) {
      toast.error('This broadcast was already sent or scheduled, so it can\'t be edited. Duplicate it instead.')
      router.push({ name: 'WhatsAppBulkMessages' })
      return
    }

    // ── Reset all wizard state to prevent sessionStorage / prior-run bleed ──
    broadcastTitle.value       = ''
    broadcastDescription.value = ''
    selectedAccount.value      = ''
    audienceMode.value         = 'list'
    selectedListName.value     = ''
    selectedList.value         = null
    parsedNumbers.value        = []
    selectedTemplateName.value = ''
    selectedTemplate.value     = null
    templateVariables.value    = []
    variableMappings.value     = []
    clearOffer()
    sendMode.value             = 'now'
    scheduledDateTime.value    = ''
    currentStep.value          = 0

    // ── Prefill Brief ──
    draftDocName.value   = asCopy ? '' : src.name
    broadcastTitle.value = asCopy ? (src.title ? `${src.title} (copy)` : '') : (src.title || '')
    broadcastDescription.value = src.description || ''
    if (src.whatsapp_account) selectedAccount.value = src.whatsapp_account

    // ── Prefill Audience ──
    if (src.recipient_type === 'Recipient List' && src.recipient_list) {
      audienceMode.value     = 'list'
      selectedListName.value = src.recipient_list
      parsedNumbers.value    = []
      onListSelect()
    } else if (src.recipient_type === 'Individual') {
      audienceMode.value     = 'numbers'
      selectedListName.value = ''
      selectedList.value     = null
      // Map inline recipients into the parsedNumbers reactive array
      const recipients = src.recipients || []
      parsedNumbers.value = recipients.map(r => ({
        number: r.mobile_number || '',
        valid: isValidPhone(r.mobile_number || ''),
        name: r.recipient_name || '',
      }))
    }

    // ── Prefill Template ──
    if (src.template) {
      selectedTemplateName.value = src.template
      await onTemplateChange()
    }

    // Editing keeps the draft's own schedule; a duplicate starts as "now".
    if (!asCopy && src.scheduled_time) {
      sendMode.value          = 'later'
      scheduledDateTime.value = String(src.scheduled_time).replace(' ', 'T').slice(0, 16)
    }

    // Template change cleared the offer; restore the draft's own values.
    if (src.template) offerValues.value = offerValuesFromDoc(src)

    // Restore variable mappings when they're in the unified format
    if (src.template_variables) {
      try {
        const mapping = JSON.parse(src.template_variables)
        if (Array.isArray(mapping)) {
          variableMappings.value = templateVariables.value.map((v, i) => {
            const entry = mapping[i]
            if (entry && typeof entry === 'object' && entry.mode === 'common') {
              return { type: 'static', value: 'recipient_name', staticText: entry.value || '' }
            }
            if (entry && typeof entry === 'object' && entry.mode === 'unique') {
              return { type: 'field', value: entry.key || 'recipient_name', staticText: '' }
            }
            return { type: 'field', value: 'recipient_name', staticText: '' }
          })
        }
      } catch (_) { /* legacy formats — leave defaults */ }
    }

    if (src.is_mpm) {
      if (src.mpm_header) mpmHeader.value = src.mpm_header
      if (src.product_ids?.length) {
        selectedProducts.value = src.product_ids.map((p) => p.item_code).filter(Boolean)
      }
    }
  } catch (e) {
    console.error('Failed to load broadcast', e)
    toast.error(prettifyFrappeError(e) || 'Failed to load broadcast')
  } finally {
    prefilling = false
  }
}

// ────────────────────────────────────────────────────────────
// sessionStorage state persistence
// ────────────────────────────────────────────────────────────
const STORAGE_KEY = `wa_broadcast_wizard_${route.query.parent_campaign || 'default'}`

function saveState() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      currentStep:          currentStep.value,
      broadcastTitle:       broadcastTitle.value,
      broadcastDescription: broadcastDescription.value,
      selectedAccount:      selectedAccount.value,
      audienceMode:         audienceMode.value,
      selectedListName:     selectedListName.value,
      parsedNumbers:        parsedNumbers.value,
      selectedTemplateName: selectedTemplateName.value,
      sendMode:             sendMode.value,
      scheduledDateTime:    scheduledDateTime.value,
      draftDocName:         draftDocName.value,
      // Only the four user-typed offer fields (no secrets); dropped whenever the template changes.
      offerValues:          offerValues.value,
    }))
  } catch (_) {}
}

function clearState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch (_) {}
}

async function restorePersistedState() {
  // The selectedAccount watcher (below) resets the template; hold it off until it has run, or the
  // restored template, and the offer values typed for it, would be wiped right after being restored.
  prefilling = true
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const s = JSON.parse(raw)

    broadcastTitle.value       = s.broadcastTitle       || ''
    broadcastDescription.value = s.broadcastDescription || ''
    selectedAccount.value      = s.selectedAccount      || ''
    audienceMode.value         = s.audienceMode         || 'list'
    parsedNumbers.value        = s.parsedNumbers        || []
    sendMode.value             = s.sendMode             || 'now'
    scheduledDateTime.value    = s.scheduledDateTime    || ''
    draftDocName.value         = s.draftDocName         || ''
    await nextTick()

    if (s.selectedListName) {
      selectedListName.value = s.selectedListName
      onListSelect()
    }

    if (s.selectedTemplateName) {
      selectedTemplateName.value = s.selectedTemplateName
      await onTemplateChange()
      // onTemplateChange clears the offer; put back what was typed for this same template.
      offerValues.value = sanitizeOfferValues(s.offerValues)
    }

    // Always start at step 0 (Brief) so user begins from the start of the wizard
    currentStep.value = 0
  } catch (_) {
  } finally {
    prefilling = false
  }
}

// Auto-save whenever key state changes
watch(
  [
    currentStep, broadcastTitle, broadcastDescription, selectedAccount,
    audienceMode, selectedListName, parsedNumbers, selectedTemplateName,
    sendMode, scheduledDateTime, offerValues,
  ],
  saveState,
  { deep: true }
)

// When the WABA account changes, re-fetch templates scoped to that account
// and clear any previously selected template (it may belong to a different account).
watch(selectedAccount, async (newAccount, oldAccount) => {
  if (newAccount === oldAccount || prefilling) return
  // Reset template selection so user picks from the correct account's list
  selectedTemplateName.value = ''
  selectedTemplate.value = null
  templateVariables.value = []
  variableMappings.value = []
  clearOffer()
  await fetchApprovedTemplates()
})

onMounted(async () => {
  await Promise.all([
    store.fetchRecipientLists(),
    fetchWabaAccounts(),
  ])
  // Templates are fetched after WABA accounts load so fetchApprovedTemplates
  // can filter by the restored selectedAccount value.
  if (route.query.draft) {
    await prefillFromBroadcast(route.query.draft, { asCopy: false })
  } else if (route.query.duplicate) {
    // Duplicate mode takes priority over persisted state
    await prefillFromBroadcast(route.query.duplicate, { asCopy: true })
  } else {
    await restorePersistedState()
  }
  // Fetch templates now that selectedAccount may be restored
  await fetchApprovedTemplates()
})
</script>

<style scoped>
/* ── Shell & Page ──────────────────────────────────────────── */
.wizard-shell {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 0;
  color: var(--ink-900, var(--ink-900));
}

/* ── Topbar ────────────────────────────────────────────────── */
.wizard-topbar {
  margin-bottom: 24px;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  padding: 6px 12px;
  margin-left: -12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s, color .12s;
}
.back-link:hover {
  background: var(--border-soft);
  color: var(--brand-500);
}
.wizard-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.wizard-subtitle {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
}

/* ── Content Card ──────────────────────────────────────────── */
.wizard-card {
  background: var(--surface-surface);
  border: 1px solid var(--border-base);
  border-radius: 14px;
  padding: 32px 36px;
  box-shadow: 0 1px 2px rgba(0,0,0,.02), 0 4px 16px rgba(0,0,0,.04);
  margin-top: 24px;
  min-height: 420px;
}

/* ── Step content ──────────────────────────────────────────── */
.step-content {
  width: 100%;
}
.step-title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
.step-description {
  margin: 0 0 24px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.55;
}

/* ── Form primitives ───────────────────────────────────────── */
.form-group {
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-500);
  display: flex;
  align-items: center;
  gap: 4px;
}
.req-star {
  color: var(--status-red-dot);
  font-size: 13px;
  line-height: 1;
}
.optional-tag {
  font-size: var(--fs-2xs);
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--border-soft);
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.field-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}
.form-select,
.form-input {
  height: 40px;
  padding: 0 12px;
  border: 1.5px solid var(--border-base);
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  background: var(--surface-surface);
  color: var(--text-primary);
  transition: border-color .15s;
}
.form-select:focus,
.form-input:focus {
  border-color: var(--brand-500);
}
.form-textarea {
  padding: 10px 12px;
  border: 1.5px solid var(--border-base);
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  background: var(--surface-surface);
  color: var(--text-primary);
  resize: vertical;
  line-height: 1.5;
  transition: border-color .15s;
  font-family: inherit;
}
.form-textarea:focus {
  border-color: var(--brand-500);
}
.select-sm,
.input-sm {
  height: 34px !important;
  font-size: 12px !important;
  padding: 0 8px !important;
}
.full-width {
  grid-column: 1 / -1;
}

/* ── Step 0: Brief grid ────────────────────────────────────── */
.brief-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
}
@media (max-width: 640px) {
  .brief-grid { grid-template-columns: 1fr; }
}

/* ── Step 1: Audience ──────────────────────────────────────── */
.audience-toggle {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1.5px solid var(--border-base);
  background: var(--surface-surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .15s;
}
.toggle-btn:hover {
  border-color: var(--brand-400);
  color: var(--brand-500);
}
.toggle-btn.active {
  border-color: var(--brand-500);
  background: var(--brand-lighter, var(--brand-50));
  color: var(--brand-600);
  font-weight: 600;
}

.audience-section {
  max-width: 620px;
}

/* Selected list card */
.selected-list-card {
  border: 1.5px solid var(--brand-500);
  border-radius: 10px;
  padding: 14px 16px;
  background: var(--brand-lighter, var(--brand-50));
  margin-top: 12px;
}
.slc-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.slc-icon { color: var(--brand-500); }
.slc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}
.slc-count {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-600);
  background: var(--surface-surface);
  border-radius: 20px;
  padding: 2px 8px;
  border: 1px solid var(--brand-200, #c7d2fe);
}
.slc-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

/* Recipient list preview table */
.list-preview {
  margin-top: 16px;
  border: 1px solid var(--border-base);
  border-radius: 10px;
  overflow: hidden;
}
.list-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--surface-gray-1, #f8fafc);
  border-bottom: 1px solid var(--border-base);
}
.list-preview-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
}
.list-preview-sub {
  font-size: 11px;
  color: var(--text-secondary);
}
.list-preview-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 20px 14px;
  font-size: 13px;
  color: var(--text-secondary);
}
.list-preview-table-wrap {
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}
.list-preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.list-preview-table thead tr {
  position: sticky;
  top: 0;
  background: var(--surface-gray-1, #f8fafc);
  z-index: 1;
}
.list-preview-table th {
  text-align: left;
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-base);
}
.list-preview-table td {
  padding: 7px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-soft, #f1f5f9);
}
.list-preview-table tbody tr:last-child td { border-bottom: none; }
.list-preview-table tbody tr:hover td { background: var(--surface-gray-1, #f8fafc); }
.td-idx {
  width: 40px;
  color: var(--text-secondary);
  font-size: 11px;
}
.td-mono {
  font-family: 'Roboto Mono', monospace, inherit;
  font-size: 12px;
}
.list-preview-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-base);
  background: var(--surface-gray-1, #f8fafc);
}
.pager-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid var(--border-base);
  background: var(--surface-surface);
  color: var(--text-primary);
  cursor: pointer;
  transition: all .12s;
}
.pager-btn:disabled { opacity: 0.4; cursor: default; }
.pager-btn:not(:disabled):hover { background: var(--brand); color: white; border-color: var(--brand-500); }
.pager-info {
  font-size: 12px;
  color: var(--text-secondary);
}
@keyframes spin { to { transform: rotate(360deg); } }
.spin { animation: spin 0.8s linear infinite; }

/* Numbers one-by-one entry */
.number-entry-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.number-entry-row .form-input {
  flex: 1;
  font-family: 'Roboto Mono', monospace, inherit;
}
.number-entry-row .name-input {
  flex: 0 1 220px;
  min-width: 0;
  font-family: inherit;
}
.tag-name {
  font-weight: 600;
  margin-right: 2px;
}
.btn-add-number {
  flex-shrink: 0;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  border: 1.5px solid var(--brand-500);
  background: var(--brand);
  color: white;
  cursor: pointer;
  transition: all .12s;
  white-space: nowrap;
}
.btn-add-number:hover { background: var(--brand); border-color: var(--brand-600); }
.number-input-error {
  font-size: 11px;
  color: var(--red-500);
  margin: 4px 0 0;
}
kbd {
  display: inline-block;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--border-base);
  background: var(--surface-surface);
  font-size: var(--fs-2xs);
  font-family: monospace;
}
.numbers-count-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.btn-clear-all {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color .12s, background .12s;
}
.btn-clear-all:hover { color: var(--red-500); background: var(--status-red-bg); }
.tag-icon { flex-shrink: 0; }

.numbers-results { margin-top: 4px; }
.numbers-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}
.badge-green {
  background: var(--status-green-bg);
  color: var(--green-700);
  border: 1px solid var(--status-green-dot);
}
.badge-red {
  background: var(--status-red-bg);
  color: var(--red-500);
  border: 1px solid var(--red-300);
}
.numbers-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.number-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  background: var(--border-soft, var(--ink-50));
  color: var(--text-primary);
  border: 1px solid var(--border-base);
}
.number-tag.invalid {
  background: var(--status-red-bg);
  color: var(--red-700);
  border-color: var(--red-300);
}
.tag-remove {
  background: none;
  border: none;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  color: inherit;
  opacity: .6;
  padding: 0 2px;
}
.tag-remove:hover { opacity: 1; }
.invalid-hint {
  font-size: 11px;
  color: var(--red-500);
  margin: 0;
}
.invalid-hint code {
  font-family: monospace;
  background: var(--status-red-bg);
  padding: 1px 3px;
  border-radius: 3px;
}

/* ── Step 2 & 4: Split layout ──────────────────────────────── */
.split-layout {
  display: flex;
  gap: 40px;
}
.layout-left {
  flex: 1;
  min-width: 0;
}
.layout-right {
  width: 300px;
  max-width: 100%;
  flex-shrink: 0;
}
/* Stack the form above the preview on narrow screens; side by side left no room for the form. */
@media (max-width: 768px) {
  .split-layout {
    flex-direction: column;
    gap: 24px;
  }
  .layout-right {
    width: 100%;
  }
}

/* Variables */
.variables-section {
  margin-top: 24px;
  border-top: 1px dashed var(--border-base);
  padding-top: 20px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 4px;
}
.section-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 16px;
}
.variable-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.variable-badge {
  font-size: 11px;
  font-weight: 600;
  background: var(--border-soft);
  color: var(--ink-500);
  padding: 4px 8px;
  border-radius: 6px;
  width: 90px;
  flex-shrink: 0;
  text-align: center;
}
.variable-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1 1 200px;
  min-width: 0;
}
.variable-inputs > * { flex: 1 1 140px; min-width: 0; }

/* ── WhatsApp Phone Preview ────────────────────────────────── */
.phone-preview-container {
  width: 100%;
  border: 1px solid var(--ink-200);
  border-radius: 24px;
  overflow: hidden;
  background: #efeae2;
  box-shadow: 0 8px 30px rgba(0,0,0,.08);
}
.phone-header {
  background: #075e54;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.phone-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: rgba(255,255,255,.15);
  display: flex;
  align-items: center;
  justify-content: center;
}
.phone-header-info {
  display: flex;
  flex-direction: column;
}
.phone-sender-name  { color: white; font-size: 12.5px; font-weight: 600; }
.phone-sender-status { color: rgba(255,255,255,.7); font-size: var(--fs-2xs); }
.phone-chat-bg {
  min-height: 280px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}
.whatsapp-bubble {
  background: var(--surface-surface);
  border-radius: 8.5px;
  box-shadow: 0 1px .5px rgba(0,0,0,.13);
  padding: 8px 10px;
  max-width: 90%;
  font-size: 12px;
  line-height: 1.5;
  color: #111b21;
  margin-top: 10px;
  position: relative;
}
.whatsapp-bubble::before {
  content: '';
  position: absolute;
  top: 0; left: -8px;
  width: 8px; height: 13px;
  background: radial-gradient(circle at top left, transparent 70%, white 70%);
}
.bubble-header {
  font-weight: 600;
  color: #128c7e;
  margin-bottom: 4px;
  font-size: 11px;
}
.bubble-footer {
  color: #667781;
  font-size: var(--fs-2xs);
  margin-top: 4px;
}
.bubble-buttons {
  border-top: 1px solid var(--border-soft);
  margin: 6px -10px -8px;
  display: flex;
  flex-direction: column;
}
.bubble-btn {
  padding: 8px 12px;
  text-align: center;
  font-weight: 500;
  color: #008069;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-bottom: 1px solid var(--border-soft);
  cursor: pointer;
}
.bubble-btn:last-child { border-bottom: none; }
.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  height: 220px;
  gap: 12px;
  padding: 0 20px;
}
.preview-empty p { font-size: 11px; color: var(--text-secondary); }

/* ── Step 1 Picker Card (list selection grid) ──────────────── */
.picker-card {
  border: 1.5px solid var(--border-base);
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  background: var(--surface-surface);
  transition: border-color .15s, box-shadow .15s;
}
.picker-card:hover {
  border-color: var(--ink-200);
  box-shadow: 0 2px 8px rgba(0,0,0,.02);
}
.picker-card.active {
  border-color: var(--brand-500);
  background: var(--brand-lighter);
  box-shadow: 0 0 0 1px var(--brand-500);
}
.picker-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.picker-card-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.radio-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid var(--ink-200);
  display: flex;
  align-items: center;
  justify-content: center;
}
.radio-dot.filled::after {
  content: '';
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--brand);
}
.picker-card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 0;
  line-height: 1.5;
}

/* ── Step 3: Schedule ──────────────────────────────────────── */
.schedule-options {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 12px;
  max-width: 580px;
}
.schedule-inputs {
  margin-top: 16px;
  border-top: 1.5px dashed var(--ink-200);
  padding-top: 16px;
}
.label-sm { font-size: 11px; }

/* ── Step 4: Review ────────────────────────────────────────── */
.summary-details {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 24px;
}
.summary-section-title {
  font-size: var(--fs-2xs);
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: .08em;
  margin: 16px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border-soft);
}
.summary-section-title:first-child { margin-top: 0; }
.summary-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-soft);
}
.summary-row:last-child { border-bottom: none; }
.summary-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: .04em;
}
.summary-value {
  font-size: 13.5px;
  color: var(--text-primary);
}

.alert-box {
  display: flex;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid;
  align-items: flex-start;
}

/* ── Footer ────────────────────────────────────────────────── */
.wizard-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 0 0;
  margin-top: 32px;
}
.wizard-footer-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.btn-nav {
  height: 42px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: all .12s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.btn-secondary {
  background: var(--surface-surface);
  border: 1.5px solid var(--border-base);
  color: var(--text-primary);
}
.btn-secondary:hover:not(:disabled) {
  border-color: var(--brand-500);
}
.btn-primary {
  background: var(--brand);
  border: 1.5px solid var(--brand-500);
  color: white;
  box-shadow: 0 2px 6px rgba(52, 65, 156,.25);
}
.btn-primary:hover:not(:disabled) {
  background: var(--brand);
  border-color: var(--brand-600);
}
.btn-nav:disabled {
  opacity: .5;
  cursor: not-allowed;
}
.flex-grow { flex-grow: 1; }

/* ── Misc helpers ──────────────────────────────────────────── */
.loading-inline,
.empty-inline {
  padding: 20px;
  border: 1.5px dashed var(--ink-200);
  border-radius: 8px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
.mt-2 { margin-top: 8px; }
.font-semibold { font-weight: 600; }
.text-slate-600 { color: var(--ink-600); }
.text-slate-700 { color: var(--ink-700); }
.text-slate-800 { color: var(--ink-800); }
.text-indigo-600 { color: var(--brand-600); }
.font-medium { font-weight: 500; }
.text-xs { font-size: 11px; line-height: 1.5; }
.text-amber-600 { color: var(--status-amber-fg); }
.link-inline {
  color: var(--brand-500);
  text-decoration: underline;
  font-weight: 500;
}
</style>
