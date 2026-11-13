<!--
  WhatsAppRecipientDetail — full-page view & edit editor for Recipient Lists.
  Full-width layout with inline form tabs for adding recipients (Upload File, From DocType, Manual Entry).
-->
<template>
  <div class="w-full text-[var(--text-primary)]">
    <!-- Topbar / Header -->
    <PageHeader
      :title="isNew ? 'New Recipient List' : (listName || 'Recipient List')"
      subtitle="Configure recipient list details and manage audience contacts"
      :back-to="{ name: 'WhatsAppRecipients' }"
      back-label="Recipients"
    >
      <template #actions>
        <button
          class="l-btn l-btn--secondary"
          @click="$router.push({ name: 'WhatsAppRecipients' })"
        >
          Cancel
        </button>
        <button
          class="l-btn l-btn--primary"
          :disabled="saving"
          @click="saveList"
        >
          <FeatherIcon v-if="!saving" name="save" class="w-4 h-4" />
          <span>{{ saving ? 'Saving…' : 'Save List' }}</span>
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <div v-if="validationError" class="w-full pt-4">
      <div class="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl flex items-center gap-3 text-red-600 dark:text-red-400 text-sm">
        <FeatherIcon name="alert-circle" class="w-5 h-5 flex-shrink-0" />
        <span>{{ validationError }}</span>
      </div>
    </div>

    <!-- Main Container -->
    <div class="w-full py-6 space-y-6">
      <!-- Card 1: List Details -->
      <div class="l-card p-6">
        <h2 class="text-sm font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-4">List Details</h2>
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
              List Name <span class="text-red-500">*</span>
            </label>
            <input
              type="text"
              v-model="listName"
              placeholder="e.g. Holiday Campaign 2025"
              class="l-input w-full"
              :disabled="loading"
            />
          </div>
          <div>
            <label class="block text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
              Description
            </label>
            <textarea
              v-model="description"
              rows="3"
              placeholder="Enter list description…"
              class="l-input w-full !h-auto py-2.5 resize-y"
              :disabled="loading"
            ></textarea>
          </div>
        </div>
      </div>

      <!-- Card 2: Add Recipients (Form Tabs) -->
      <div class="l-card p-6">
        <div class="flex flex-wrap items-center justify-between border-b border-[var(--border-base)] pb-4 mb-5 gap-3">
          <div>
            <h2 class="text-base font-bold text-[var(--text-primary)]">Add Recipients to List</h2>
            <p class="text-xs text-[var(--text-secondary)] mt-0.5">
              Choose a method to import or add recipients into your live recipient list below.
            </p>
          </div>
          <div class="flex items-center gap-1 bg-[var(--surface-page)] p-1 rounded-xl border border-[var(--border-base)] text-xs">
            <button
              type="button"
              class="flex items-center gap-1.5 px-3.5 py-2 font-semibold rounded-lg transition-all cursor-pointer border-none"
              :class="activeTab === 'upload' ? 'bg-[var(--surface-surface)] text-[var(--brand)] shadow-xs font-bold' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent'"
              @click="activeTab = 'upload'"
            >
              <FeatherIcon name="upload-cloud" class="w-3.5 h-3.5" />
              <span>CSV / Excel File</span>
            </button>
            <button
              type="button"
              class="flex items-center gap-1.5 px-3.5 py-2 font-semibold rounded-lg transition-all cursor-pointer border-none"
              :class="activeTab === 'doctype' ? 'bg-[var(--surface-surface)] text-[var(--brand)] shadow-xs font-bold' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent'"
              @click="activeTab = 'doctype'; onDoctypeTabActivated()"
            >
              <FeatherIcon name="database" class="w-3.5 h-3.5" />
              <span>DocType Import</span>
            </button>
            <button
              type="button"
              class="flex items-center gap-1.5 px-3.5 py-2 font-semibold rounded-lg transition-all cursor-pointer border-none"
              :class="activeTab === 'manual' ? 'bg-[var(--surface-surface)] text-[var(--brand)] shadow-xs font-bold' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent'"
              @click="activeTab = 'manual'"
            >
              <FeatherIcon name="plus-circle" class="w-3.5 h-3.5" />
              <span>Add Manually</span>
            </button>
          </div>
        </div>

        <!-- TAB 1: CSV / Excel Upload -->
        <div v-if="activeTab === 'upload'" class="space-y-4">
          <!-- Template Download & Guidance Bar -->
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-2xl">
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-xl bg-[var(--brand)]/10 text-[var(--brand)] shrink-0">
                <FeatherIcon name="file-text" class="w-5 h-5" />
              </div>
              <div>
                <p class="text-sm font-semibold text-[var(--text-primary)]">Need a template for bulk upload?</p>
                <p class="text-xs text-[var(--text-secondary)] mt-0.5">
                  Download our formatted CSV template with standard headers (<code class="font-mono text-[11px] bg-[var(--surface-surface)] px-1 py-0.5 rounded">mobile_number</code>, <code class="font-mono text-[11px] bg-[var(--surface-surface)] px-1 py-0.5 rounded">recipient_name</code>, custom variables).
                </p>
              </div>
            </div>
            <button
              type="button"
              class="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-[var(--brand)] bg-[var(--brand)]/10 hover:bg-[var(--brand)]/20 rounded-xl transition-colors cursor-pointer border-none shrink-0"
              @click="downloadSampleCsv"
              title="Download sample CSV template"
            >
              <FeatherIcon name="download" class="w-3.5 h-3.5" />
              <span>Download Sample CSV</span>
            </button>
          </div>

          <div
            class="border-2 border-dashed border-[var(--border-base)] hover:border-[var(--brand)] rounded-2xl p-6 text-center cursor-pointer transition-colors bg-[var(--surface-page)]/50"
            @click="csvFileInput?.click()"
            @dragover.prevent
            @drop.prevent="onCsvFileDrop"
          >
            <input
              ref="csvFileInput"
              type="file"
              accept=".csv,.xlsx,.xls"
              class="hidden"
              @change="onCsvFileChosen"
            />
            <FeatherIcon name="upload-cloud" class="w-10 h-10 text-[var(--brand)] mx-auto mb-2 opacity-80" />
            <p class="text-sm font-semibold text-[var(--text-primary)]">
              {{ csvBusy ? 'Parsing file…' : 'Click to browse or drag and drop CSV / Excel file' }}
            </p>
            <p class="text-xs text-[var(--text-tertiary)] mt-1">
              Supports .csv, .xlsx, and .xls spreadsheets with mobile numbers and names
            </p>
            <div class="mt-2 text-xs text-[var(--text-secondary)]">
              <span>Or </span>
              <button
                type="button"
                class="text-[var(--brand)] hover:underline font-semibold bg-transparent border-none cursor-pointer p-0"
                @click.stop="downloadSampleCsv"
              >
                download sample CSV template
              </button>
            </div>
          </div>

          <!-- CSV Preview & Column Mapping Box -->
          <div v-if="csvPreview" class="p-5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-2xl space-y-4">
            <div class="flex items-center justify-between border-b border-[var(--border-base)] pb-3">
              <div class="flex items-center gap-2">
                <FeatherIcon name="file-text" class="w-4 h-4 text-[var(--brand)]" />
                <span class="text-sm font-bold text-[var(--text-primary)]">Detected Columns & Mapping</span>
              </div>
              <span class="text-xs font-semibold px-2.5 py-1 bg-green-100 dark:bg-green-950/60 text-green-700 dark:text-green-400 rounded-full">
                {{ csvPreview.summary?.valid || csvPreview.rows?.length || 0 }} valid rows found
              </span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Mobile Number Column <span class="text-red-500">*</span>
                </label>
                <select
                  v-model="csvPreview.mobile_column"
                  class="w-full px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                >
                  <option v-for="col in csvPreview.columns" :key="col" :value="col">{{ col }}</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Recipient Name Column (Optional)
                </label>
                <select
                  v-model="csvPreview.name_column"
                  class="w-full px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                >
                  <option value="">— None —</option>
                  <option v-for="col in csvPreview.columns" :key="col" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>

            <div class="flex items-center justify-between pt-2">
              <div class="flex items-center gap-4 text-xs">
                <label class="inline-flex items-center gap-1.5 cursor-pointer">
                  <input type="radio" v-model="importMode" value="append" />
                  <span>Append to existing list</span>
                </label>
                <label class="inline-flex items-center gap-1.5 cursor-pointer">
                  <input type="radio" v-model="importMode" value="replace" />
                  <span>Replace current rows</span>
                </label>
              </div>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent border-none cursor-pointer"
                  @click="cancelCsv"
                >
                  Clear
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--brand)] text-white text-xs font-bold rounded-xl shadow-xs hover:opacity-90 transition-all border-none cursor-pointer"
                  @click="importCsvRecipients"
                >
                  <FeatherIcon name="download" class="w-3.5 h-3.5" />
                  <span>Import File Rows</span>
                </button>
              </div>
            </div>
          </div>

          <p v-if="csvError" class="text-xs text-red-500">{{ csvError }}</p>
        </div>

        <!-- TAB 2: DocType Import -->
        <div v-if="activeTab === 'doctype'" class="space-y-4">
          <!-- Preset Chips -->
          <div>
            <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-2">Select Source DocType</label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="p in CRM_PRESETS"
                :key="p.value"
                type="button"
                class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer"
                :class="selectedDoctype === p.value && !isCustomDoctype ? 'bg-[var(--brand)] text-white border-[var(--brand)] shadow-xs' : 'bg-[var(--surface-page)] text-[var(--text-secondary)] border-[var(--border-base)] hover:border-[var(--brand)]'"
                @click="selectDoctype(p.value)"
              >
                <FeatherIcon v-if="p.value.includes('Lead')" name="user" class="w-3 h-3" />
                <FeatherIcon v-else-if="p.value.includes('Deal')" name="briefcase" class="w-3 h-3" />
                <FeatherIcon v-else-if="p.value === 'Contact'" name="users" class="w-3 h-3" />
                <FeatherIcon v-else-if="p.value === 'Customer'" name="shopping-bag" class="w-3 h-3" />
                <FeatherIcon v-else name="database" class="w-3 h-3" />
                <span>{{ p.label }}</span>
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer"
                :class="isCustomDoctype ? 'bg-[var(--brand)] text-white border-[var(--brand)] shadow-xs' : 'bg-[var(--surface-page)] text-[var(--text-secondary)] border-[var(--border-base)] hover:border-[var(--brand)]'"
                @click="isCustomDoctype = true; showDoctypeDropdown = true"
              >
                <FeatherIcon name="search" class="w-3 h-3" />
                <span>Other DocType…</span>
              </button>
            </div>

            <!-- Custom DocType Search -->
            <div v-if="isCustomDoctype" class="relative mt-2">
              <input
                v-model="customDoctypeSearch"
                type="text"
                class="w-full px-3.5 py-2 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                placeholder="Type to search DocType (e.g. CRM Deal, Quotation)..."
                @input="searchCustomDoctypes"
                @focus="showDoctypeDropdown = true"
              />
              <div
                v-if="showDoctypeDropdown && customDoctypeResults.length"
                class="absolute left-0 right-0 top-full mt-1 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl shadow-lg max-h-48 overflow-y-auto z-40"
              >
                <div
                  v-for="dt in customDoctypeResults"
                  :key="dt"
                  class="px-3.5 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)] cursor-pointer"
                  @click="selectDoctype(dt)"
                >
                  {{ dt }}
                </div>
              </div>
            </div>
          </div>

          <!-- DocType Schema Loading -->
          <div v-if="doctypeLoading" class="p-6 text-center text-xs text-[var(--text-secondary)] flex items-center justify-center gap-2">
            <LLoader inline :size="18" />
            <span>Inspecting {{ selectedDoctype }} schema…</span>
          </div>

          <!-- Field Mapping & Filtering -->
          <div v-else class="p-5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-2xl space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Mobile Number Field <span class="text-red-500">*</span>
                </label>
                <select
                  v-model="selectedMobileField"
                  class="w-full px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                  @change="fetchDoctypePreview"
                >
                  <option value="" disabled>Select Phone Field</option>
                  <option v-for="f in doctypeFields" :key="f.fieldname" :value="f.fieldname">
                    {{ f.label }} ({{ f.fieldname }})
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Status Field
                </label>
                <select
                  v-model="selectedStatusField"
                  class="w-full px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                  @change="onStatusFieldChange"
                >
                  <option value="">— None —</option>
                  <option v-for="f in doctypeFields" :key="f.fieldname" :value="f.fieldname">
                    {{ f.label }} ({{ f.fieldname }})
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                  Recipient Name Field
                </label>
                <select
                  v-model="selectedNameField"
                  class="w-full px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                  @change="fetchDoctypePreview"
                >
                  <option value="">None (Doc Name / Blank)</option>
                  <option v-for="f in doctypeFields" :key="f.fieldname" :value="f.fieldname">
                    {{ f.label }} ({{ f.fieldname }})
                  </option>
                </select>
              </div>
            </div>

            <!-- Status Filter Pills -->
            <div v-if="statusOptions.length" class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-xs font-semibold text-[var(--text-secondary)]">Filter by Status ({{ selectedStatusField }})</label>
                <div class="flex items-center gap-2 text-xs">
                  <button type="button" class="text-[var(--brand)] hover:underline bg-transparent border-none cursor-pointer p-0" @click="selectAllStatuses">Select All</button>
                  <span class="text-[var(--text-tertiary)]">·</span>
                  <button type="button" class="text-[var(--text-secondary)] hover:underline bg-transparent border-none cursor-pointer p-0" @click="clearAllStatuses">Clear</button>
                </div>
              </div>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="st in statusOptions"
                  :key="st"
                  type="button"
                  class="px-3 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer"
                  :class="selectedStatuses.includes(st) ? 'bg-[var(--brand)] text-white border-[var(--brand)]' : 'bg-[var(--surface-surface)] text-[var(--text-secondary)] border-[var(--border-base)] hover:border-[var(--brand)]'"
                  @click="toggleStatus(st)"
                >
                  <span v-if="selectedStatuses.includes(st)" class="mr-1 font-bold"><Icon name="check" :size="14" class="ei" /></span>
                  <span>{{ st }}</span>
                </button>
              </div>
            </div>

            <!-- Additional Filter Conditions (Optional) -->
            <div class="space-y-3 pt-3 border-t border-[var(--border-base)]">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
                  Additional Filter Conditions (Optional)
                </span>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand)] hover:underline bg-transparent border-none cursor-pointer p-0"
                  @click="addDoctypeFilterRule"
                >
                  <FeatherIcon name="plus" class="w-3.5 h-3.5" />
                  <span>Add Condition</span>
                </button>
              </div>

              <div v-if="doctypeFilterRules.length" class="space-y-2">
                <div
                  v-for="(rule, rIdx) in doctypeFilterRules"
                  :key="rIdx"
                  class="flex items-center gap-2"
                >
                  <select
                    v-model="rule.field"
                    class="flex-1 px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                    @change="debouncePreview"
                  >
                    <option value="" disabled>Select Field...</option>
                    <option v-for="f in doctypeFields" :key="f.fieldname" :value="f.fieldname">
                      {{ f.label }} ({{ f.fieldname }})
                    </option>
                  </select>

                  <select
                    v-model="rule.operator"
                    class="w-28 px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                    @change="debouncePreview"
                  >
                    <option value="=">=</option>
                    <option value="!=">!=</option>
                    <option value="like">like</option>
                    <option value="not like">not like</option>
                    <option value=">">&gt;</option>
                    <option value="<">&lt;</option>
                    <option value=">=">&gt;=</option>
                    <option value="<=">&lt;=</option>
                  </select>

                  <input
                    v-model="rule.value"
                    type="text"
                    placeholder="Value"
                    class="flex-1 px-3 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                    @input="debouncePreview"
                  />

                  <button
                    type="button"
                    class="p-2 text-[var(--text-tertiary)] hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors border-none bg-transparent cursor-pointer"
                    @click="removeDoctypeFilterRule(rIdx)"
                    title="Remove condition"
                  >
                    <FeatherIcon name="trash-2" class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            <!-- Matching Record Count & Import Action -->
            <div class="flex items-center justify-between pt-3 border-t border-[var(--border-base)]">
              <div class="flex items-center gap-4 text-xs">
                <span class="font-bold text-[var(--text-primary)]">
                  {{ doctypePreviewBusy ? 'Calculating matching contacts…' : `${doctypePreview?.total_count || 0} matching records ready` }}
                </span>
                <label class="inline-flex items-center gap-1.5 cursor-pointer text-[var(--text-secondary)]">
                  <input type="radio" v-model="importMode" value="append" />
                  <span>Append</span>
                </label>
                <label class="inline-flex items-center gap-1.5 cursor-pointer text-[var(--text-secondary)]">
                  <input type="radio" v-model="importMode" value="replace" />
                  <span>Replace</span>
                </label>
              </div>
              <button
                type="button"
                class="inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--brand)] text-white text-xs font-bold rounded-xl shadow-xs hover:opacity-90 transition-all border-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="doctypeLoading || doctypeImporting || doctypePreviewBusy || !doctypePreview?.total_count"
                @click="executeDoctypeImport"
              >
                <FeatherIcon v-if="!doctypeImporting" name="download" class="w-3.5 h-3.5" />
                <span>{{ doctypeImporting ? 'Importing…' : `Import ${doctypePreview?.total_count || 0} Contacts` }}</span>
              </button>
            </div>
          </div>

          <p v-if="doctypeError" class="text-xs text-red-500">{{ doctypeError }}</p>
        </div>

        <!-- TAB 3: Manual Entry -->
        <div v-if="activeTab === 'manual'" class="space-y-4">
          <div class="p-5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-2xl space-y-3">
            <p class="text-xs text-[var(--text-secondary)]">
              Add a contact directly to the table below, or paste a quick contact row.
            </p>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                v-model="quickMobile"
                type="text"
                :placeholder="`Mobile Number (${EXAMPLE_PHONE_HINT}) *`"
                class="px-3.5 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                @keydown.enter="addQuickRow"
              />
              <input
                v-model="quickName"
                type="text"
                placeholder="Recipient Name (Optional)"
                class="px-3.5 py-2 bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]"
                @keydown.enter="addQuickRow"
              />
            </div>
            <div class="flex justify-end gap-2 pt-2">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--brand)] text-white text-xs font-bold rounded-xl shadow-xs hover:opacity-90 transition-all border-none cursor-pointer"
                @click="addQuickRow"
              >
                <FeatherIcon name="plus" class="w-3.5 h-3.5" />
                <span>Add to List</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Card 3: Recipients Table & Review -->
      <div class="bg-[var(--surface-surface)] border border-[var(--border-base)] rounded-2xl p-6 shadow-xs space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold text-[var(--text-primary)]">
            Recipients ({{ filteredRecipients.length }} shown / {{ recipients.length }} total)
          </h2>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--surface-page)] border border-[var(--border-base)] rounded-xl transition-all cursor-pointer"
            @click="addRow"
          >
            <FeatherIcon name="plus" class="w-3.5 h-3.5" />
            <span>Add Row</span>
          </button>
        </div>

        <!-- Search Bar -->
        <div class="relative">
          <FeatherIcon name="search" class="w-4 h-4 text-[var(--text-tertiary)] absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            v-model="search"
            type="text"
            placeholder="Search within this list by name or number…"
            class="w-full pl-10 pr-4 py-2 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-xl text-sm text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)] transition-all"
            @input="currentPage = 1"
          />
        </div>

        <!-- Loading State -->
        <Shimmer v-if="loading" variant="rows" :count="4" />

        <!-- Empty Table State -->
        <div
          v-else-if="!filteredRecipients.length"
          class="border-2 border-dashed border-[var(--border-base)] rounded-2xl p-10 text-center bg-[var(--surface-page)]/40"
        >
          <FeatherIcon name="users" class="w-10 h-10 text-[var(--text-tertiary)] mx-auto mb-2 opacity-70" />
          <p class="text-sm font-semibold text-[var(--text-primary)]">
            {{ search ? 'No rows match your search query.' : 'No recipients in this list' }}
          </p>
          <p class="text-xs text-[var(--text-tertiary)] mt-1">
            {{ search ? 'Try a different search keyword.' : 'Use the tabs above to upload a CSV file, import from DocTypes, or add rows manually.' }}
          </p>
        </div>

        <!-- Populated Interactive Table -->
        <div v-else class="overflow-x-auto border border-[var(--border-base)] rounded-xl">
          <table class="w-full text-left text-sm border-collapse">
            <thead class="bg-[var(--surface-page)] border-b border-[var(--border-base)] text-xs font-bold text-[var(--text-secondary)] uppercase">
              <tr>
                <th class="py-3 px-4 w-16">No.</th>
                <th class="py-3 px-4">Mobile Number *</th>
                <th class="py-3 px-4">Recipient Name</th>
                <th class="py-3 px-4 w-20 text-right">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-[var(--border-base)]">
              <tr
                v-for="(r, idx) in paginatedRecipients"
                :key="r.local_id"
                class="hover:bg-[var(--surface-page)]/60 transition-colors"
              >
                <td class="py-2.5 px-4 font-mono text-xs text-[var(--text-tertiary)]">
                  {{ (currentPage - 1) * pageSize + idx + 1 }}
                </td>
                <td class="py-2 px-4">
                  <input
                    type="text"
                    v-model="r.mobile_number"
                    :placeholder="EXAMPLE_PHONE_HINT"
                    class="w-full px-3 py-1.5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-lg text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--brand)] font-mono"
                  />
                </td>
                <td class="py-2 px-4">
                  <input
                    type="text"
                    v-model="r.recipient_name"
                    placeholder="Optional name"
                    class="w-full px-3 py-1.5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-lg text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--brand)]"
                  />
                </td>
                <td class="py-2 px-4 text-right">
                  <button
                    type="button"
                    class="p-1.5 text-[var(--text-tertiary)] hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors border-none bg-transparent cursor-pointer"
                    @click="deleteRow(idx)"
                    title="Delete row"
                  >
                    <FeatherIcon name="trash-2" class="w-4 h-4" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination Controls -->
        <div v-if="totalPages > 1" class="flex items-center justify-between pt-3 text-xs text-[var(--text-secondary)]">
          <span>Showing {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, totalFiltered) }} of {{ totalFiltered }}</span>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              :disabled="currentPage === 1"
              @click="goToPage(currentPage - 1)"
            >
              Previous
            </button>
            <button
              class="px-3 py-1.5 bg-[var(--surface-page)] border border-[var(--border-base)] rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              :disabled="currentPage === totalPages"
              @click="goToPage(currentPage + 1)"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { FeatherIcon, frappeRequest, toast } from 'frappe-ui'
import PageHeader from '@/shared/ui/PageHeader.vue'
import { uploadFile } from '@/modules/inbox/services/inboxApi'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'
import { EXAMPLE_PHONE_HINT } from '@/shared/constants/inputExamples'
import { WHATSAPP_RECIPIENTS_CSV_TEMPLATE } from '@/shared/constants/csvTemplates'

const props = defineProps({
  id: { type: String, default: '' },
  isNew: { type: Boolean, default: false }
})

const router = useRouter()

// Form states
const listName = ref('')
const description = ref('')
const recipients = ref([]) // array of { name: '', mobile_number: '', recipient_name: '', recipient_data: '{}' }
const originalListName = ref('')
const modifiedTime = ref('')
const creationTime = ref('')
const ownerUser = ref('')

const loading = ref(false)
const saving = ref(false)
const validationError = ref('')

// Tabs
const activeTab = ref('upload') // 'upload' | 'doctype' | 'manual'
const importMode = ref('append') // 'append' | 'replace'

// Manual / Quick Row states
const quickMobile = ref('')
const quickName = ref('')
const search = ref('')
const currentPage = ref(1)
const pageSize = 25

// CSV import states
const csvFileInput = ref(null)
const csvBusy = ref(false)
const csvError = ref('')
const csvPreview = ref(null)
const csvFileUrl = ref('')

// DocType import states
const doctypeLoading = ref(false)
const doctypePreviewBusy = ref(false)
const doctypeImporting = ref(false)
const doctypeError = ref('')

const CRM_PRESETS = [
  { label: 'CRM Lead', value: 'CRM Lead' },
  { label: 'CRM Deal', value: 'CRM Deal' },
  { label: 'Lead', value: 'Lead' },
  { label: 'Contact', value: 'Contact' },
  { label: 'Customer', value: 'Customer' },
  { label: 'Opportunity', value: 'Opportunity' }
]

const selectedDoctype = ref('CRM Lead')
const isCustomDoctype = ref(false)
const customDoctypeSearch = ref('')
const customDoctypeResults = ref([])
const showDoctypeDropdown = ref(false)

const doctypeFields = ref([])
const selectedMobileField = ref('')
const selectedNameField = ref('')
const selectedStatusField = ref('status')
const statusOptions = ref([])
const selectedStatuses = ref([])
const doctypeFilterRules = ref([])
const doctypePreview = ref(null)

function notify(message, indicator = 'green') {
  if (window.frappe?.show_alert) {
    window.frappe.show_alert({ message, indicator })
  }
}

async function loadListData() {
  if (props.isNew) {
    listName.value = ''
    description.value = ''
    recipients.value = []
    originalListName.value = ''
    modifiedTime.value = ''
    creationTime.value = ''
    ownerUser.value = ''
    return
  }

  loading.value = true
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_recipient_list',
      method: 'POST',
      params: { name: props.id },
    })
    if (res) {
      listName.value = res.list_name || res.name || ''
      description.value = res.description || ''
      recipients.value = (res.recipients || []).map(r => ({
        ...r,
        local_id: r.name || Math.random().toString(36).slice(2, 11)
      }))
      originalListName.value = res.name || ''
      modifiedTime.value = res.modified || ''
      creationTime.value = res.creation || ''
      ownerUser.value = res.owner || ''
    }
  } catch (e) {
    console.error('Failed to load list details', e)
    notify('Failed to load recipient list details.', 'red')
  } finally {
    loading.value = false
  }
}

// Search & Pagination
const filteredRecipients = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return recipients.value
  return recipients.value.filter(r => 
    (r.recipient_name || '').toLowerCase().includes(query) ||
    (r.mobile_number || '').toLowerCase().includes(query)
  )
})

const paginatedRecipients = computed(() => {
  const startIdx = (currentPage.value - 1) * pageSize
  const endIdx = startIdx + pageSize
  return filteredRecipients.value.slice(startIdx, endIdx)
})

const totalFiltered = computed(() => filteredRecipients.value.length)
const totalPages = computed(() => Math.ceil(totalFiltered.value / pageSize) || 1)

function goToPage(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
  }
}

// Table Editing
function addRow() {
  search.value = ''
  currentPage.value = 1
  recipients.value.unshift({
    mobile_number: '',
    recipient_name: '',
    name: '',
    local_id: Math.random().toString(36).slice(2, 11)
  })
}

function addQuickRow() {
  if (!quickMobile.value.trim()) {
    toast.error('Mobile number is required')
    return
  }
  recipients.value.unshift({
    mobile_number: quickMobile.value.trim(),
    recipient_name: quickName.value.trim(),
    name: '',
    local_id: Math.random().toString(36).slice(2, 11)
  })
  quickMobile.value = ''
  quickName.value = ''
  currentPage.value = 1
  notify('Recipient added to list.')
}

function deleteRow(idxInPaginated) {
  const rowObj = paginatedRecipients.value[idxInPaginated]
  const originalIdx = recipients.value.indexOf(rowObj)
  if (originalIdx > -1) {
    recipients.value.splice(originalIdx, 1)
  }
}

// CSV Importer
function onCsvFileDrop(ev) {
  const file = ev.dataTransfer?.files?.[0]
  if (file) handleCsvUpload(file)
}

function onCsvFileChosen(ev) {
  const file = ev.target.files?.[0]
  if (file) handleCsvUpload(file)
  ev.target.value = ''
}

async function handleCsvUpload(file) {
  csvError.value = ''
  csvBusy.value = true
  csvPreview.value = null
  try {
    const uploaded = await uploadFile(file, { folder: 'Home/Attachments' })
    csvFileUrl.value = uploaded.file_url
    const preview = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.bulk_messaging.parse_recipient_file',
      method: 'POST',
      params: { file_url: uploaded.file_url },
    })
    if (preview) {
      if (!preview.columns && preview.rows?.length) {
        preview.columns = Object.keys(preview.rows[0].data || {})
      }
      csvPreview.value = preview
    }
  } catch (e) {
    console.error('Failed to parse CSV file', e)
    csvError.value = e?.messages?.[0] || 'Failed to read this file. Use CSV or Excel (.xlsx/.xls).'
    toast.error(prettifyFrappeError(e) || 'Failed to parse CSV file')
  } finally {
    csvBusy.value = false
  }
}

function importCsvRecipients() {
  if (!csvPreview.value) return
  const validRows = (csvPreview.value.rows || []).filter(r => r.is_valid)
  if (!validRows.length) {
    csvError.value = 'No valid rows to import.'
    return
  }

  const allColumns = csvPreview.value.columns || Object.keys(validRows[0]?.data || {})
  const selectedMobile = csvPreview.value.mobile_column
  const selectedName = csvPreview.value.name_column
  const variableCols = allColumns.filter(c => c !== selectedMobile && c !== selectedName)

  const newRecipients = validRows.map(r => {
    const data = {}
    for (const col of variableCols) {
      const val = r.data[col]
      if (val !== undefined && val !== null && String(val).trim()) {
        data[col] = String(val).trim()
      }
    }
    return {
      mobile_number: r.data[selectedMobile],
      recipient_name: selectedName ? r.data[selectedName] : '',
      recipient_data: Object.keys(data).length ? JSON.stringify(data) : '{}',
      name: '',
      local_id: Math.random().toString(36).slice(2, 11)
    }
  })

  if (importMode.value === 'replace') {
    recipients.value = newRecipients
  } else {
    const existingMobiles = new Set(recipients.value.map(r => String(r.mobile_number || '').replace(/[^\d+]/g, '')))
    const deduped = []
    for (const item of newRecipients) {
      const norm = String(item.mobile_number || '').replace(/[^\d+]/g, '')
      if (!existingMobiles.has(norm)) {
        existingMobiles.add(norm)
        deduped.push(item)
      }
    }
    recipients.value = [...deduped, ...recipients.value]
  }

  notify(`Imported ${newRecipients.length} recipients from file.`)
  csvPreview.value = null
  csvFileUrl.value = ''
  currentPage.value = 1
}

function cancelCsv() {
  csvPreview.value = null
  csvFileUrl.value = ''
  csvError.value = ''
}

function downloadSampleCsv() {
  const blob = new Blob(['\uFEFF' + WHATSAPP_RECIPIENTS_CSV_TEMPLATE], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.setAttribute('href', url)
  link.setAttribute('download', 'whatsapp_recipients_sample.csv')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  notify('Sample CSV template downloaded.')
}

// DocType Importer
function onDoctypeTabActivated() {
  if (!doctypeFields.value.length) {
    loadDoctypeMeta(selectedDoctype.value)
  }
}

async function selectDoctype(dtName) {
  selectedDoctype.value = dtName
  isCustomDoctype.value = !CRM_PRESETS.some(p => p.value === dtName)
  showDoctypeDropdown.value = false
  await loadDoctypeMeta(dtName)
}

async function searchCustomDoctypes() {
  if (!customDoctypeSearch.value.trim()) {
    customDoctypeResults.value = []
    return
  }
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.recipients.search_importable_doctypes',
      method: 'POST',
      params: { query: customDoctypeSearch.value.trim() }
    })
    customDoctypeResults.value = res || []
  } catch (e) {
    console.error('Failed to search doctypes', e)
  }
}

async function loadDoctypeMeta(dtName) {
  if (!dtName) return
  doctypeLoading.value = true
  doctypeError.value = ''
  doctypePreview.value = null
  selectedStatuses.value = []
  doctypeFilterRules.value = []

  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.recipients.get_doctype_import_meta',
      method: 'POST',
      params: { doctype: dtName }
    })
    if (res) {
      doctypeFields.value = res.fields || []
      selectedMobileField.value = res.defaults?.mobile_field || ''
      selectedNameField.value = res.defaults?.name_field || ''
      selectedStatusField.value = res.defaults?.status_field || ''
      statusOptions.value = res.status_options || []
      await fetchDoctypePreview()
    }
  } catch (e) {
    console.error('Failed to load doctype meta', e)
    doctypeError.value = e?.messages?.[0] || 'Failed to inspect DocType schema.'
  } finally {
    doctypeLoading.value = false
  }
}

function onStatusFieldChange() {
  selectedStatuses.value = []
  if (!selectedStatusField.value) {
    statusOptions.value = []
    fetchDoctypePreview()
    return
  }
  const f = doctypeFields.value.find(field => field.fieldname === selectedStatusField.value)
  if (f && f.options && typeof f.options === 'string') {
    statusOptions.value = f.options.split('\n').map(s => s.trim()).filter(Boolean)
  } else {
    statusOptions.value = []
  }
  fetchDoctypePreview()
}

function addDoctypeFilterRule() {
  doctypeFilterRules.value.push({ field: '', operator: '=', value: '' })
}

function removeDoctypeFilterRule(idx) {
  doctypeFilterRules.value.splice(idx, 1)
  fetchDoctypePreview()
}

function buildCustomFilters() {
  const out = {}
  for (const rule of doctypeFilterRules.value) {
    if (rule.field && rule.field.trim() && rule.value !== undefined && rule.value !== null && String(rule.value).trim()) {
      const val = String(rule.value).trim()
      out[rule.field.trim()] = rule.operator === '=' ? val : [rule.operator, val]
    }
  }
  return out
}

let previewDebounceTimer = null
function debouncePreview() {
  clearTimeout(previewDebounceTimer)
  previewDebounceTimer = setTimeout(() => {
    fetchDoctypePreview()
  }, 300)
}

function toggleStatus(status) {
  const idx = selectedStatuses.value.indexOf(status)
  if (idx > -1) {
    selectedStatuses.value.splice(idx, 1)
  } else {
    selectedStatuses.value.push(status)
  }
  fetchDoctypePreview()
}

function selectAllStatuses() {
  selectedStatuses.value = [...statusOptions.value]
  fetchDoctypePreview()
}

function clearAllStatuses() {
  selectedStatuses.value = []
  fetchDoctypePreview()
}

async function fetchDoctypePreview() {
  if (!selectedDoctype.value || !selectedMobileField.value) {
    doctypePreview.value = null
    return
  }
  doctypePreviewBusy.value = true
  doctypeError.value = ''
  try {
    const customFilters = buildCustomFilters()
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.recipients.preview_doctype_recipients',
      method: 'POST',
      params: {
        doctype: selectedDoctype.value,
        mobile_field: selectedMobileField.value,
        name_field: selectedNameField.value || '',
        status_values: JSON.stringify(selectedStatuses.value),
        status_field: selectedStatusField.value || '',
        filters: JSON.stringify(customFilters),
        limit: 5,
      }
    })
    doctypePreview.value = res || { total_count: 0, sample_rows: [] }
  } catch (e) {
    console.error('Failed to preview recipients', e)
    doctypeError.value = e?.messages?.[0] || 'Error evaluating preview.'
  } finally {
    doctypePreviewBusy.value = false
  }
}

async function executeDoctypeImport() {
  if (!selectedDoctype.value || !selectedMobileField.value) return
  doctypeImporting.value = true
  doctypeError.value = ''
  try {
    const customFilters = buildCustomFilters()
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.recipients.fetch_doctype_recipients',
      method: 'POST',
      params: {
        doctype: selectedDoctype.value,
        mobile_field: selectedMobileField.value,
        name_field: selectedNameField.value || '',
        status_values: JSON.stringify(selectedStatuses.value),
        status_field: selectedStatusField.value || '',
        filters: JSON.stringify(customFilters),
        limit: 0,
      }
    })

    const fetched = (res?.recipients || []).map(r => ({
      ...r,
      local_id: r.local_id || Math.random().toString(36).slice(2, 11)
    }))

    if (!fetched.length) {
      doctypeError.value = 'No valid recipients with mobile numbers found matching the selected filters.'
      return
    }

    if (importMode.value === 'replace') {
      recipients.value = fetched
    } else {
      const existingMobiles = new Set(recipients.value.map(r => String(r.mobile_number || '').replace(/[^\d+]/g, '')))
      const newItems = []
      for (const item of fetched) {
        const norm = String(item.mobile_number || '').replace(/[^\d+]/g, '')
        if (!existingMobiles.has(norm)) {
          existingMobiles.add(norm)
          newItems.push(item)
        }
      }
      recipients.value = [...newItems, ...recipients.value]
    }

    notify(`Imported ${fetched.length} recipients from ${selectedDoctype.value}.`)
    currentPage.value = 1
  } catch (e) {
    console.error('Failed to import recipients from DocType', e)
    doctypeError.value = e?.messages?.[0] || 'Failed to import from DocType.'
    toast.error(prettifyFrappeError(e) || 'Failed to import from DocType')
  } finally {
    doctypeImporting.value = false
  }
}

// Save Document
async function saveList() {
  validationError.value = ''
  
  const nameVal = listName.value.trim()
  if (!nameVal) {
    validationError.value = 'List Name is required.'
    return
  }

  if (recipients.value.length === 0) {
    validationError.value = 'At least one recipient is required.'
    return
  }

  const seenMobiles = new Set()
  for (let i = 0; i < recipients.value.length; i++) {
    const r = recipients.value[i]
    const rawMobile = r.mobile_number !== undefined && r.mobile_number !== null ? String(r.mobile_number) : ''
    if (!rawMobile.trim()) {
      validationError.value = `Row ${i + 1}: Mobile Number is required.`
      return
    }
    
    const cleanedMobile = rawMobile.replace(/[^\d+]/g, '')
    if (!/^\+?\d{7,15}$/.test(cleanedMobile)) {
      validationError.value = `Row ${i + 1}: Invalid mobile number format (${r.mobile_number}).`
      return
    }

    if (seenMobiles.has(cleanedMobile)) {
      validationError.value = `Row ${i + 1}: Duplicate mobile number (${r.mobile_number}) found in the list.`
      return
    }
    seenMobiles.add(cleanedMobile)
  }

  saving.value = true
  try {
    await persistList(nameVal)
    notify(props.isNew && !originalListName.value
      ? 'Recipient list created successfully.'
      : 'Recipient list saved successfully.')
    router.push({ name: 'WhatsAppRecipients' })
  } catch (e) {
    console.error('Failed to save list', e)
    validationError.value = e?.messages?.[0] || 'Failed to save recipient list.'
    toast.error(prettifyFrappeError(e) || 'Failed to save list')
  } finally {
    saving.value = false
  }
}

function serializeRecipientRow(r) {
  const rawMobile = r.mobile_number !== undefined && r.mobile_number !== null ? String(r.mobile_number) : ''
  const rawName = r.recipient_name !== undefined && r.recipient_name !== null ? String(r.recipient_name) : ''
  return {
    doctype: 'WhatsApp Recipient',
    name: r.name || undefined,
    mobile_number: rawMobile.trim(),
    recipient_name: rawName.trim(),
    recipient_data: r.recipient_data || '{}',
    country_code: r.country_code || '',
    creation: r.creation || undefined,
    owner: r.owner || undefined
  }
}

async function persistList(nameVal) {
  if (props.isNew && !originalListName.value) {
    const docPayload = {
      doctype: 'WhatsApp Recipient List',
      list_name: nameVal,
      description: description.value.trim(),
      recipients: recipients.value.map(serializeRecipientRow)
    }

    const created = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.insert_recipient_list',
      method: 'POST',
      params: { doc: JSON.stringify(docPayload) }
    })
    originalListName.value = created?.name || nameVal
    modifiedTime.value = created?.modified || ''
    creationTime.value = created?.creation || ''
    ownerUser.value = created?.owner || ''
    return originalListName.value
  }

  const targetName = originalListName.value

  if (nameVal !== targetName) {
    await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.rename_recipient_list',
      method: 'POST',
      params: { name: targetName, new_name: nameVal }
    })
    originalListName.value = nameVal
  }

  const docPayload = {
    doctype: 'WhatsApp Recipient List',
    name: originalListName.value,
    list_name: nameVal,
    description: description.value.trim(),
    modified: modifiedTime.value || undefined,
    creation: creationTime.value || undefined,
    owner: ownerUser.value || undefined,
    recipients: recipients.value.map(serializeRecipientRow)
  }

  const saved = await frappeRequest({
    url: '/api/method/frappe.client.save',
    method: 'POST',
    params: { doc: JSON.stringify(docPayload) }
  })
  if (saved) {
    originalListName.value = saved.name || originalListName.value
    modifiedTime.value = saved.modified || ''
    creationTime.value = saved.creation || ''
    ownerUser.value = saved.owner || ''
  }
  return originalListName.value
}

onMounted(() => {
  loadListData()
})
</script>
