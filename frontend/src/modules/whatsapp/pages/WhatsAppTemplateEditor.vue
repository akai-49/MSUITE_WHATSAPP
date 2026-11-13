<!--
  WhatsAppTemplateEditor — template creation/editing form with live preview.

  Split layout: form on left, WhatsApp-style preview on right.
  Connected to Frappe backend: saves & submits to database and Meta API.
-->
<template>
  <div class="editor-page">
    <!-- Header -->
    <PageHeader
      :title="editName ? 'Edit Template' : 'New Template'"
      subtitle="Create and submit Meta-compliant WhatsApp message templates"
      :back-to="{ name: 'WhatsAppTemplates' }"
      back-label="Templates"
    />

    <div class="editor-layout">
      <!-- Form Panel -->
      <div class="form-panel">
        <h2 class="form-heading">{{ editName ? 'Edit Template Details' : 'Template Details' }}</h2>

        <!-- First Four Fields Responsive Grid -->
        <div class="editor-fields-grid">
          <!-- WhatsApp Business Account (WABA) Selection -->
          <div class="form-group">
            <label class="form-label">WhatsApp Business Account <span class="text-[var(--status-red-fg)]">*</span></label>
            <select class="form-control" v-model="form.waba" @change="onWabaChange">
              <option value="">Select WhatsApp Business Account</option>
              <option v-for="wa in wabaAccounts" :key="wa.name" :value="wa.name">
                {{ (wa.account_name || wa.name) + (wa.number ? ` (${wa.number})` : '') }}
              </option>
            </select>
          </div>

          <!-- Category -->
          <div class="form-group">
            <label class="form-label">Category <span class="text-[var(--status-red-fg)]">*</span></label>
            <select class="form-control" v-model="form.category" @change="onCategoryChange">
              <option value="">Select category</option>
              <option value="MARKETING">Marketing</option>
              <option value="UTILITY">Utility</option>
              <option value="AUTHENTICATION">Authentication</option>
              <!-- Legacy categories (pre-v16 Meta API) so synced templates display -->
              <option v-if="form.category === 'TRANSACTIONAL'" value="TRANSACTIONAL">Transactional (legacy)</option>
              <option v-if="form.category === 'OTP'" value="OTP">OTP (legacy)</option>
            </select>
          </div>


          <!-- Template Type / Subtype Dropdown -->
          <div class="form-group">
            <label class="form-label">Template Type</label>
            <select class="form-control" v-model="form.template_type" @change="onTemplateTypeChange">
              <option v-for="t in availableTemplateTypes" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
          </div>

          <!-- Catalogue & Product Selector -->
          <div v-if="form.template_type === 'CATALOGUE' || form.template_type === 'MPM' || form.header_type === 'PRODUCT'" class="form-section col-span-2 border border-[var(--status-blue-bg)] bg-[var(--status-blue-bg)] p-4 rounded-xl mt-2 mb-2">
            <div class="flex items-center gap-2 mb-3">
              <FeatherIcon name="shopping-bag" class="w-5 h-5 text-[var(--status-blue-fg)]" />
              <div>
                <h3 class="text-sm font-bold text-[var(--text-primary)]">Catalogue Configuration</h3>
                <p v-if="form.template_type === 'CATALOGUE'" class="text-xs text-[var(--text-secondary)]">Optionally choose which catalogue to showcase. The header thumbnail is the first catalog item (or a product you pick per-send) — nothing else is needed here.</p>
                <p v-else class="text-xs text-[var(--text-secondary)]">Select the Meta Product Catalogue linked to your WhatsApp Business Account and pick a Product from the catalogue.</p>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <!-- Catalogue Dropdown -->
              <div class="form-group mb-0">
                <label class="form-label font-semibold text-[var(--text-primary)]">Meta Product Catalogue <span v-if="form.header_type === 'PRODUCT'" class="text-[var(--status-red-fg)]">*</span><span v-else class="text-[var(--text-tertiary)] font-normal text-xs">(optional)</span></label>
                <select class="form-control bg-[var(--bg-surface)]" v-model="form.catalog_id" @change="fetchCatalogProducts">
                  <option value="">-- Select Catalogue --</option>
                  <option
                    v-for="cat in availableCatalogs"
                    :key="cat.catalog_id || cat.name"
                    :value="cat.catalog_id || cat.name"
                  >
                    {{ cat.catalog_name || cat.name }} (ID: {{ cat.catalog_id || 'N/A' }})
                  </option>
                </select>
                <p v-if="loadingCatalogs" class="text-xs text-[var(--status-blue-fg)] mt-1">Loading catalogues...</p>
                <p v-else-if="!availableCatalogs.length" class="text-xs text-[var(--text-tertiary)] mt-1">No Meta Product Catalogs found for this account. Configure catalogues under E-Commerce > Meta Commerce Sync.</p>
              </div>

              <!-- Product Dropdown — only for a Single Product Message header; a catalog template's thumbnail is chosen at send time -->
              <div v-if="form.header_type === 'PRODUCT'" class="form-group mb-0">
                <label class="form-label font-semibold text-[var(--text-primary)]">Catalogue Product (Sample / Thumbnail) <span class="text-[var(--status-red-fg)]">*</span></label>
                <select class="form-control bg-[var(--bg-surface)]" v-model="form.thumbnail_product_retailer_id">
                  <option value="">-- Select Product --</option>
                  <option
                    v-for="prod in catalogProducts"
                    :key="prod.item_code"
                    :value="prod.item_code"
                  >
                    {{ prod.item_name }} (SKU: {{ prod.item_code }}) {{ prod.price ? ' - ' + prod.price : '' }}
                  </option>
                </select>
                <p v-if="loadingProducts" class="text-xs text-[var(--status-blue-fg)] mt-1">Loading products from catalogue...</p>
              </div>
            </div>

            <!-- Product Card Preview Box -->
            <div v-if="selectedProductDetails" class="mt-3 p-3 bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg flex items-center gap-3">
              <img v-if="selectedProductDetails.image" :src="selectedProductDetails.image" class="w-12 h-12 rounded object-cover border border-[var(--border)]" alt="Image" />
              <div v-else class="w-12 h-12 rounded bg-[var(--bg-sunken)] flex items-center justify-center text-[var(--text-tertiary)] shrink-0">
                <FeatherIcon name="package" class="w-6 h-6" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="text-xs font-bold text-[var(--text-primary)] truncate">{{ selectedProductDetails.item_name }}</div>
                <div class="text-[11px] text-[var(--text-secondary)] font-mono">Retailer ID: {{ selectedProductDetails.item_code }}</div>
                <div v-if="selectedProductDetails.price" class="text-xs font-semibold text-[var(--status-green-fg)] mt-0.5">{{ selectedProductDetails.price }}</div>
              </div>
            </div>
          </div>

          <!-- Template Name -->
          <div class="form-group">
            <label class="form-label">Template Name <span class="text-[var(--status-red-fg)]">*</span></label>
            <input
              type="text"
              class="form-control"
              :value="form.template_name"
              @input="onTemplateNameInput"
              @blur="onTemplateNameBlur"
              placeholder="e.g. order_confirmation"
            />
            <p class="form-hint">Lowercase with underscores. This will be the identifier sent to WhatsApp.</p>
          </div>

          <!-- Language -->
          <div class="form-group">
            <label class="form-label">Language <span class="text-[var(--status-red-fg)]">*</span></label>
            <select class="form-control" v-model="form.language">
              <option value="">Select language</option>
              <option
                v-for="lang in languagesList"
                :key="lang.name"
                :value="lang.name"
              >
                {{ lang.language_name }} ({{ lang.name }})
              </option>
            </select>
          </div>

          <!-- Variable Format -->
          <div class="form-group">
            <label class="form-label">Variable Format</label>
            <select class="form-control" v-model="form.parameter_format">
              <option value="POSITIONAL">Positional — &#123;&#123;1&#125;&#125;, &#123;&#123;2&#125;&#125;</option>
              <option value="NAMED">Named — &#123;&#123;first_name&#125;&#125;, &#123;&#123;order_id&#125;&#125;</option>
            </select>
            <p class="form-hint">Named variables use readable placeholders; each needs a sample value below.</p>
          </div>
        </div>

        <!-- Header — a catalog template has a fixed product-thumbnail header, so no header config.
             Authentication templates do NOT support headers — Meta rejects them. -->
        <div v-if="!form.is_carousel && form.template_type !== 'CATALOGUE' && form.category !== 'AUTHENTICATION'" class="form-section">
          <h3 class="form-section-title">Header <span class="text-[var(--text-tertiary)] font-normal text-sm">· Optional</span></h3>
          <div class="form-group">
            <label class="form-label">Header Type</label>
            <select class="form-control" v-model="form.header_type">
              <option value="">None / Text</option>
              <option value="IMAGE">Image</option>
              <option value="VIDEO">Video</option>
              <option value="DOCUMENT">Document</option>
              <option value="LOCATION">Location</option>
              <option value="PRODUCT">Product (Single Product Message)</option>
            </select>
          </div>

          <!-- Media Sample Uploader -->
          <div v-if="['IMAGE', 'VIDEO', 'DOCUMENT'].includes(form.header_type)" class="form-group mt-2">
            <div>
              <div v-if="!form.media_sample" class="upload-placeholder" @click="openMediaLibrary">
                <p class="upload-text text-sm">Drag and drop to upload</p>
                <p class="upload-text text-sm">Or <span class="text-[var(--status-blue-fg)] cursor-pointer hover:underline">choose files on your device</span></p>
                <p class="text-xs text-[var(--text-tertiary)] mt-2">
                  Accepted:
                  <span v-if="form.header_type === 'IMAGE'">jpg, png, jpeg, webp</span>
                  <span v-else-if="form.header_type === 'VIDEO'">mp4, 3gp, mov (max 16 MB)</span>
                  <span v-else-if="form.header_type === 'DOCUMENT'">pdf</span>
                </p>
              </div>
              <div v-else class="media-preview-container">
                <div class="media-preview-box">
                  <img v-if="form.header_type === 'IMAGE'" :src="form.media_sample" class="preview-media img" alt="Preview" />
                  <video v-else-if="form.header_type === 'VIDEO'" :src="form.media_sample" controls class="preview-media video"></video>
                  <div v-else-if="form.header_type === 'DOCUMENT'" class="preview-media doc-box">
                    <FeatherIcon name="file-text" class="w-12 h-12 text-[var(--text-tertiary)]" />
                    <span class="doc-name">{{ getFileName(form.media_sample) }}</span>
                  </div>
                </div>
                <div class="media-preview-actions">
                  <button class="btn btn-default btn-sm" @click="openMediaLibrary">Replace Media</button>
                  <button class="btn btn-default btn-sm text-[var(--status-red-fg)] border-[var(--status-red-bg)] hover:border-red-500 ml-2" @click="removeMediaSample">Remove</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Location info -->
          <div v-if="form.header_type === 'LOCATION'" class="form-group mt-2">
            <p class="text-xs text-[var(--text-secondary)]">The location (name, address, coordinates) is provided when each message is sent — nothing to configure here.</p>
          </div>

          <!-- Product info -->
          <div v-if="form.header_type === 'PRODUCT'" class="form-group mt-2">
            <p class="text-xs text-[var(--text-secondary)]">The product (image, title, price) is pulled live from your connected Meta catalog when each message is sent — requires the button below to be a Single Product Message button. Choose a specific product per-send, not here.</p>
          </div>

          <!-- Header Text -->
          <div v-if="!['IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION', 'PRODUCT'].includes(form.header_type)" class="form-group mt-2">
            <label class="form-label">Header Text</label>
            <div class="relative">
              <input
                type="text"
                class="form-control pr-12"
                v-model="form.header"
                @keydown="onHeaderKeydown"
                @input="onHeaderInput"
                placeholder="Add a short line of text to the header of your message in English"
                maxlength="60"
              />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-tertiary)]">
                {{ form.header ? form.header.length : 0 }}/60
              </span>
            </div>
          </div>
        </div>

        <!-- Carousel section (temporarily disabled)
        <div v-if="form.template_type !== 'CATALOGUE' && form.template_type !== 'MPM' && form.header_type !== 'PRODUCT' && form.category !== 'AUTHENTICATION'" class="form-section">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="form-section-title">Carousel <span class="text-[var(--text-tertiary)] font-normal text-sm">· Optional</span></h3>
              <p class="text-xs text-[var(--text-secondary)]">Attach a horizontally scrollable set of cards. Meta doesn't allow a top-level Header, Footer, or Buttons on a carousel — each card carries its own.</p>
            </div>
            <label class="flex items-center gap-2 cursor-pointer select-none shrink-0 ml-4">
              <input type="checkbox" v-model="form.is_carousel" class="w-4 h-4 cursor-pointer" />
              <span class="text-sm font-medium text-[var(--text-primary)]">Is Carousel</span>
            </label>
          </div>

          <div v-if="form.is_carousel" class="mt-4 space-y-4">
            <div class="flex gap-2">
              <button type="button" class="btn btn-sm" :class="form.carousel_type === 'Product' ? 'btn-primary' : 'btn-default'" @click="setCarouselType('Product')">Product cards (catalog)</button>
              <button type="button" class="btn btn-sm" :class="form.carousel_type === 'Media' ? 'btn-primary' : 'btn-default'" @click="setCarouselType('Media')">Media cards (image/video)</button>
            </div>

            <template v-if="form.carousel_type === 'Product'">
              <div v-for="(card, idx) in form.carousel_cards" :key="idx" class="border border-[var(--border)] rounded-lg p-4 bg-[var(--bg-surface)] shadow-sm">
                <span class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Card #{{ idx + 1 }}</span>
                <div class="grid grid-cols-1 md:grid-cols-12 gap-4 mt-2">
                  <div class="md:col-span-3">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button type</label>
                    <select class="form-control" v-model="card.button_type">
                      <option value="SPM">Single Product Message</option>
                      <option value="URL">Visit website</option>
                    </select>
                  </div>
                  <div v-if="card.button_type === 'URL'" class="md:col-span-4">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button label</label>
                    <input type="text" v-model="card.button_label" class="form-control" placeholder="View" maxlength="25" />
                  </div>
                  <div v-else class="md:col-span-4">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button label</label>
                    <input type="text" value="View" class="form-control bg-[var(--bg-sunken)] text-[var(--text-tertiary)]" disabled title="Meta requires SPM buttons to read exactly &quot;View&quot;." />
                  </div>
                  <div v-if="card.button_type === 'URL'" class="md:col-span-5">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Website URL</label>
                    <input type="text" v-model="card.website_url" class="form-control" :placeholder="EXAMPLE_URL" maxlength="2000" />
                  </div>
                </div>
              </div>
            </template>

            <template v-else>
              <p class="text-xs text-[var(--status-amber-fg)]">All cards must have the same button combination and (if used) a body — Meta rejects mixed cards.</p>
              <div v-for="(card, idx) in form.carousel_cards" :key="idx" class="border border-[var(--border)] rounded-lg p-4 bg-[var(--bg-surface)] shadow-sm space-y-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Card #{{ idx + 1 }}</span>
                  <button v-if="form.carousel_cards.length > 2" type="button" class="text-xs text-[var(--status-red-fg)] hover:underline" @click="removeCarouselCard(idx)">Remove</button>
                </div>
                <div>
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Header image / video <span class="text-[var(--status-red-fg)]">*</span></label>
                  <div class="flex items-center gap-3">
                    <div class="w-20 h-20 rounded bg-[var(--bg-sunken)] border border-[var(--border)] flex items-center justify-center overflow-hidden shrink-0">
                      <img v-if="card.media_sample && card.header_format === 'IMAGE'" :src="card.media_sample" class="w-full h-full object-cover" alt="Image" />
                      <video v-else-if="card.media_sample && card.header_format === 'VIDEO'" :src="card.media_sample" class="w-full h-full object-cover"></video>
                      <FeatherIcon v-else name="image" class="w-6 h-6 text-[var(--text-tertiary)]" />
                    </div>
                    <button type="button" class="btn btn-default btn-sm" @click="openCardMedia(idx)">{{ card.media_sample ? 'Replace' : 'Upload' }}</button>
                  </div>
                </div>
                <div>
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Card body <span class="text-[var(--text-tertiary)] font-normal normal-case">· optional, max 160</span></label>
                  <input type="text" v-model="card.card_body" class="form-control" maxlength="160" placeholder="Optional card text" />
                </div>
                <div class="grid grid-cols-1 md:grid-cols-12 gap-3">
                  <div class="md:col-span-3">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button 1</label>
                    <select class="form-control" v-model="card.button_type">
                      <option value="Quick Reply">Quick Reply</option>
                      <option value="URL">Visit website</option>
                      <option value="Call Phone">Call phone</option>
                    </select>
                  </div>
                  <div class="md:col-span-4">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Label</label>
                    <input type="text" v-model="card.button_label" class="form-control" maxlength="25" placeholder="Button text" />
                  </div>
                  <div v-if="card.button_type === 'URL'" class="md:col-span-5">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Website URL <span class="text-[var(--text-tertiary)] font-normal normal-case">· supports one variable</span></label>
                    <input type="text" v-model="card.website_url" class="form-control" maxlength="2000" :placeholder="`${EXAMPLE_URL}/{{1}}`" />
                    <input v-if="card.website_url && card.website_url.includes('{{')" type="text" v-model="card.example_url" class="form-control mt-1" placeholder="URL variable example (e.g. blue-elf)" />
                  </div>
                  <div v-else-if="card.button_type === 'Call Phone'" class="md:col-span-5">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Phone number</label>
                    <input type="text" v-model="card.phone_number" class="form-control" maxlength="20" :placeholder="EXAMPLE_PHONE_HINT" />
                  </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-12 gap-3">
                  <div class="md:col-span-3">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button 2 <span class="text-[var(--text-tertiary)] font-normal normal-case">· optional</span></label>
                    <select class="form-control" v-model="card.button2_type">
                      <option value="">None</option>
                      <option value="Quick Reply">Quick Reply</option>
                      <option value="URL">Visit website</option>
                      <option value="Call Phone">Call phone</option>
                    </select>
                  </div>
                  <div v-if="card.button2_type" class="md:col-span-4">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Label</label>
                    <input type="text" v-model="card.button2_label" class="form-control" maxlength="25" placeholder="Button text" />
                  </div>
                  <div v-if="card.button2_type === 'URL'" class="md:col-span-5">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Website URL</label>
                    <input type="text" v-model="card.button2_website_url" class="form-control" maxlength="2000" :placeholder="`${EXAMPLE_URL}/{{1}}`" />
                    <input v-if="card.button2_website_url && card.button2_website_url.includes('{{')" type="text" v-model="card.button2_example_url" class="form-control mt-1" placeholder="URL variable example" />
                  </div>
                  <div v-else-if="card.button2_type === 'Call Phone'" class="md:col-span-5">
                    <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Phone number</label>
                    <input type="text" v-model="card.button2_phone_number" class="form-control" maxlength="20" :placeholder="EXAMPLE_PHONE_HINT" />
                  </div>
                </div>
              </div>
              <button v-if="form.carousel_cards.length < 10" type="button" class="btn btn-default btn-sm" @click="addCarouselCard">+ Add card ({{ form.carousel_cards.length }}/10)</button>
            </template>
          </div>
        </div>
        -->

        <!-- Body -->
        <div class="form-section">
          <h3 class="form-section-title">Body</h3>
          <div class="form-group">
            <div class="flex items-center justify-between mb-1.5">
              <label class="form-label mb-0">Message Body <span class="text-[var(--status-red-fg)]">*</span></label>
              <button
                type="button"
                class="px-2.5 py-1 bg-[var(--status-blue-bg)] text-[var(--status-blue-fg)] border border-[var(--status-blue-bg)] hover:bg-blue-100 rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer"
                @click="addVariableToBody"
              >
                <FeatherIcon name="plus" class="w-3.5 h-3.5" />
                <span>Add variable</span>
              </button>
            </div>
            <textarea
              ref="bodyTextareaRef"
              class="form-control form-textarea"
              v-model="form.body"
              @keydown="onBodyKeydown"
              @input="onBodyInput"
              :placeholder="form.parameter_format === 'NAMED'
                ? 'Hello {{first_name}}, your order {{order_id}} has been shipped!'
                : 'Hello {{1}}, your order {{2}} has been shipped!'"
              rows="6"
            ></textarea>
            <p class="form-hint" v-if="form.parameter_format === 'NAMED'">Use &#123;&#123;first_name&#125;&#125;, &#123;&#123;order_id&#125;&#125; etc. for variables.</p>
            <p class="form-hint" v-else>Use &#123;&#123;1&#125;&#125;, &#123;&#123;2&#125;&#125; etc. for variables.</p>
          </div>

          <!-- Variable Samples Section -->
          <div v-if="extractedVariables.length > 0" class="variable-samples-section mt-4 p-4 bg-[var(--bg-sunken)] rounded-xl border border-[var(--border)]">
            <h4 class="text-sm font-semibold text-[var(--text-primary)] mb-1">Variable samples</h4>
            <p class="text-xs text-[var(--text-secondary)] mb-3">
              Include samples of all variables in your message to help Meta review your template. Remember not to include any customer information to protect your customer's privacy.
            </p>
            <div class="form-group mb-0">
              <label class="form-label text-[11px] text-[var(--text-tertiary)]">Body</label>
              <div v-for="num in extractedVariables" :key="num" class="flex items-center mb-2 last:mb-0">
                <div class="bg-[var(--bg-sunken)] border border-[var(--border)] border-r-0 rounded-l-lg px-4 h-10 flex items-center text-sm font-mono text-[var(--text-secondary)] min-w-[60px] justify-center select-none">
                  &#123;&#123;{{ num }}&#125;&#125;
                </div>
                <input
                  type="text"
                  v-model="variableSamples[num]"
                  class="form-control rounded-l-none rounded-r-lg"
                  placeholder="Sample value"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Footer — hidden for carousels (cards carry own footer) and
             Authentication templates (Meta auto-generates the footer from code_expiration_minutes). -->
        <div v-if="!form.is_carousel && form.category !== 'AUTHENTICATION' && !form.limited_time_offer_enabled" class="form-section">
          <h3 class="form-section-title">Footer</h3>
          <div class="form-group">
            <input type="text" class="form-control" v-model="form.footer" placeholder="Optional footer text" />
          </div>
        </div>

        <!-- Limited-time offer — Marketing + image/video header only (Meta rule).
             Turning it on removes the footer (Meta disallows both). -->
        <div v-if="isLtoEligible || form.limited_time_offer_enabled" class="form-section">
          <h3 class="form-section-title">Limited-time offer</h3>
          <div class="form-group flex items-center gap-2">
            <input type="checkbox" id="lto-enabled" v-model="form.limited_time_offer_enabled" @change="onLtoToggle" class="w-4 h-4 cursor-pointer" />
            <label for="lto-enabled" class="text-sm text-[var(--text-primary)] cursor-pointer select-none">
              Add a limited-time offer to this template
            </label>
          </div>
          <p v-if="ltoNotice" class="form-hint text-[var(--status-amber-fg)]" role="status">{{ ltoNotice }}</p>
          <template v-if="form.limited_time_offer_enabled">
            <div class="form-group">
              <label class="form-label" for="lto-text">
                Offer text
                <span v-if="ltoTextMax" class="text-[var(--text-tertiary)] font-normal text-xs ml-1" aria-live="polite">{{ ltoRemaining }} characters left</span>
              </label>
              <input id="lto-text" type="text" class="form-control" v-model="form.lto_text" placeholder="e.g. Summer offer" />
              <p v-if="ltoTextError" class="form-hint text-[var(--status-red-fg)]" role="alert">{{ ltoTextError }}</p>
            </div>
            <div class="form-group flex items-center gap-2">
              <input type="checkbox" id="lto-has-expiration" v-model="form.lto_has_expiration" class="w-4 h-4 cursor-pointer" />
              <label for="lto-has-expiration" class="text-sm text-[var(--text-primary)] cursor-pointer select-none">
                Show a countdown (the end time is set when you send)
              </label>
            </div>
          </template>
        </div>

        <!-- Authentication extras -->
        <div v-if="form.category === 'AUTHENTICATION'" class="form-section">
          <h3 class="form-section-title">Authentication Options</h3>
          <div class="form-group flex items-center gap-2">
            <input type="checkbox" id="add-security-recommendation" v-model="form.add_security_recommendation" class="w-4 h-4 cursor-pointer" />
            <label for="add-security-recommendation" class="text-sm text-[var(--text-primary)] cursor-pointer select-none">
              Add security recommendation ("For your security, do not share this code")
            </label>
          </div>
          <div class="form-group">
            <label class="form-label">Code Expiration (Minutes)</label>
            <input type="number" min="1" max="90" class="form-control" v-model.number="form.code_expiration_minutes" placeholder="e.g. 10" />
            <p class="form-hint">Adds a footer like "This code expires in N minutes". Leave empty to skip.</p>
          </div>
        </div>

        <!-- SPM / MPM: single fixed button, added automatically -->
        <div v-if="form.header_type === 'PRODUCT' || form.template_type === 'MPM'" class="form-section">
          <h3 class="form-section-title">Button</h3>
          <p class="text-xs text-[var(--text-secondary)]">
            <template v-if="form.header_type === 'PRODUCT'">A single <strong>View</strong> button is added automatically — this is a Single-Product Message template.</template>
            <template v-else>A single <strong>View items</strong> button is added automatically — this is a Multi-Product Message template.</template>
          </p>
        </div>

        <!-- Authentication: OTP button is auto-added — no user-configurable buttons -->
        <div v-else-if="form.category === 'AUTHENTICATION'" class="form-section">
          <h3 class="form-section-title">Button</h3>
          <p class="text-xs text-[var(--text-secondary)]">
            A <strong>Copy code</strong> button is added automatically for Authentication (OTP) templates. The one-time passcode is provided at send time.
          </p>
        </div>

        <!-- Buttons Section — hidden when the button is fixed (catalog / SPM / MPM / Auth) -->
        <div v-else-if="!form.is_carousel && form.template_type !== 'CATALOGUE'" class="form-section">
          <h3 class="form-section-title">Buttons <span class="text-[var(--text-tertiary)] font-normal text-sm">· Optional</span></h3>
          <p class="text-xs text-[var(--text-secondary)] mb-4">Create buttons that let customers respond to your message or take action. You can add up to ten buttons. If you add more than three buttons, they will appear in a list.</p>

          <!-- Add Button Dropdown -->
          <div class="relative inline-block text-left mb-4">
            <button
              type="button"
              class="btn btn-default flex items-center gap-1.5 px-4 h-10 border border-[var(--border)] rounded-lg hover:bg-[var(--bg-sunken)] transition"
              @click="showAddButtonDropdown = !showAddButtonDropdown"
            >
              + Add button
              <FeatherIcon name="chevron-down" class="w-4 h-4 text-[var(--text-secondary)]" />
            </button>
            <div
              v-if="showAddButtonDropdown"
              class="absolute left-0 mt-1 w-64 rounded-xl shadow-xl bg-[var(--bg-surface)] border border-[var(--border)] divide-y divide-[var(--border-soft)] focus:outline-none z-30 overflow-hidden"
            >
              <div class="py-1">
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('QUICK_REPLY')">
                  <FeatherIcon name="corner-up-left" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Custom</div>
                    <div class="text-xs text-[var(--text-tertiary)]">Quick reply</div>
                  </div>
                </a>
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('URL')">
                  <FeatherIcon name="external-link" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Visit website</div>
                    <div class="text-xs text-[var(--text-tertiary)]">2 buttons maximum</div>
                  </div>
                </a>
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('VOICE_CALL')">
                  <FeatherIcon name="phone-call" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Call on WhatsApp</div>
                    <div class="text-xs text-[var(--text-tertiary)]">1 button maximum</div>
                  </div>
                </a>
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('PHONE_NUMBER')">
                  <FeatherIcon name="phone" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Call Phone Number</div>
                    <div class="text-xs text-[var(--text-tertiary)]">1 button maximum</div>
                  </div>
                </a>
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('FLOW')">
                  <FeatherIcon name="file-text" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Complete flow</div>
                    <div class="text-xs text-[var(--text-tertiary)]">1 button maximum</div>
                  </div>
                </a>
                <a href="#" class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-sunken)] transition cursor-pointer" @click.prevent="addButton('COPY_CODE')">
                  <FeatherIcon name="copy" class="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
                  <div>
                    <div class="text-sm font-medium text-[var(--text-primary)]">Copy offer code</div>
                    <div class="text-xs text-[var(--text-tertiary)]">1 button maximum</div>
                  </div>
                </a>
              </div>
            </div>
          </div>

          <!-- Buttons Card List -->
          <div v-for="(btn, idx) in form.buttons" :key="btn.local_id" class="button-row-card border border-[var(--border)] rounded-lg p-4 mb-4 bg-[var(--bg-surface)] shadow-sm relative">
            
            <!-- Drag Handle & Actions Toolbar -->
            <div class="flex items-center justify-between border-b border-[var(--border-soft)] pb-3 mb-3">
              <div class="flex items-center gap-2">
                <div class="text-[var(--text-tertiary)] cursor-grab hover:text-[var(--text-secondary)] flex items-center select-none font-bold" title="Drag to reorder">
                  ⠿
                </div>
                <span class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
                  Button #{{ idx + 1 }}
                </span>
              </div>
              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  class="p-1 hover:bg-[var(--bg-sunken)] rounded text-[var(--text-secondary)] disabled:opacity-30"
                  :disabled="idx === 0"
                  @click="moveButtonUp(idx)"
                  title="Move Up"
                >
                  <FeatherIcon name="chevron-up" class="w-4 h-4" />
                </button>
                <button
                  type="button"
                  class="p-1 hover:bg-[var(--bg-sunken)] rounded text-[var(--text-secondary)] disabled:opacity-30"
                  :disabled="idx === form.buttons.length - 1"
                  @click="moveButtonDown(idx)"
                  title="Move Down"
                >
                  <FeatherIcon name="chevron-down" class="w-4 h-4" />
                </button>
                <button
                  type="button"
                  class="p-1 hover:bg-[var(--bg-sunken)] rounded text-[var(--text-secondary)]"
                  @click="duplicateButton(idx)"
                  title="Duplicate"
                >
                  <FeatherIcon name="copy" class="w-4 h-4" />
                </button>
                <button
                  type="button"
                  class="p-1 hover:bg-[var(--status-red-bg)] rounded text-[var(--status-red-fg)] hover:text-[var(--status-red-fg)] ml-1"
                  @click="removeButton(idx)"
                  title="Delete"
                >
                  <FeatherIcon name="x" class="w-4 h-4" />
                </button>
              </div>
            </div>

            <!-- Card Form Fields Grid -->
            <div class="grid grid-cols-1 md:grid-cols-12 gap-4">
              <!-- Type of Action Select -->
              <div class="md:col-span-3">
                <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Type of action</label>
                <select
                  class="form-control"
                  :value="btn.type"
                  @change="onButtonTypeChange(idx, $event.target.value)"
                >
                  <option value="VOICE_CALL">Call on WhatsApp</option>
                  <option value="URL">Visit website</option>
                  <option value="PHONE_NUMBER">Call Phone Number</option>
                  <option value="QUICK_REPLY">Quick Reply</option>
                  <option value="FLOW">Flow</option>
                  <option value="COPY_CODE">Offer Code</option>
                </select>
              </div>

              <!-- Button Text Input -->
              <div class="md:col-span-3">
                <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Button text</label>
                <div class="relative">
                  <input
                    type="text"
                    v-model="btn.text"
                    class="form-control pr-12"
                    placeholder="Button label"
                    :maxlength="btn.type === 'QUICK_REPLY' ? 25 : 40"
                  />
                  <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-tertiary)]">
                    {{ btn.text ? btn.text.length : 0 }}/{{ btn.type === 'QUICK_REPLY' ? 25 : 40 }}
                  </span>
                </div>
              </div>

              <!-- URL options -->
              <template v-if="btn.type === 'URL'">
                <div class="md:col-span-2">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">URL type</label>
                  <select class="form-control" v-model="btn.url_type">
                    <option value="Static">Static</option>
                    <option value="Dynamic">Dynamic</option>
                  </select>
                </div>
                <div class="md:col-span-4">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Website URL</label>
                  <div class="relative">
                    <input
                      type="text"
                      v-model="btn.url"
                      class="form-control pr-16"
                      :placeholder="EXAMPLE_URL"
                      maxlength="2000"
                    />
                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-tertiary)]">
                      {{ btn.url ? btn.url.length : 0 }}/2000
                    </span>
                  </div>
                </div>
              </template>

              <!-- PHONE_NUMBER options -->
              <template v-else-if="btn.type === 'PHONE_NUMBER'">
                <div class="md:col-span-2 relative">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Country</label>
                  <button
                    type="button"
                    class="form-control flex items-center justify-between text-left"
                    @click="openCountryDropdown(idx)"
                  >
                    <span class="truncate">{{ btn.country || 'US +1' }}</span>
                    <FeatherIcon name="chevron-down" class="w-4 h-4 text-[var(--text-secondary)] flex-shrink-0" />
                  </button>

                  <!-- Backdrop to close dropdown on click outside -->
                  <div
                    v-if="activeCountryDropdownIdx === idx"
                    class="fixed inset-0 z-40"
                    @click="activeCountryDropdownIdx = null"
                  ></div>

                  <!-- Dropdown List Panel -->
                  <div
                    v-if="activeCountryDropdownIdx === idx"
                    class="absolute left-0 mt-1 w-64 rounded-xl shadow-xl bg-[var(--bg-surface)] border border-[var(--border)] z-50 flex flex-col overflow-hidden"
                  >
                    <!-- Search Input -->
                    <div class="relative border-b border-[var(--border-soft)] p-2">
                      <FeatherIcon name="search" class="w-4 h-4 text-[var(--text-tertiary)] absolute left-5 top-1/2 -translate-y-1/2" />
                      <input
                        v-model="countrySearchQuery"
                        type="text"
                        class="w-full pl-9 pr-3 py-1.5 text-sm bg-[var(--bg-sunken)] border border-[var(--border)] rounded-lg focus:outline-none focus:ring-1 focus:ring-[var(--brand)] focus:bg-[var(--bg-surface)]"
                        placeholder="Search"
                        autofocus
                      />
                    </div>

                    <!-- Scrollable Countries -->
                    <div class="max-h-60 overflow-y-auto py-1">
                      <div
                        v-for="c in filteredCountries"
                        :key="c.code"
                        class="flex items-center gap-3 px-4 py-2 hover:bg-[var(--bg-sunken)] cursor-pointer transition"
                        @click="selectCountry(idx, c)"
                      >
                        <!-- Custom Check/Radio Dot -->
                        <div
                          class="w-4.5 h-4.5 rounded-full border flex items-center justify-center flex-shrink-0"
                          :class="btn.country === (c.code + ' ' + c.isd) ? 'border-[var(--brand)] bg-[var(--brand)] text-white' : 'border-[var(--border)] bg-[var(--bg-surface)]'"
                        >
                          <div
                            v-if="btn.country === (c.code + ' ' + c.isd)"
                            class="w-1.5 h-1.5 rounded-full bg-[var(--bg-surface)]"
                          ></div>
                        </div>
                        <div class="flex flex-col text-left">
                          <span class="text-sm font-semibold text-[var(--text-primary)] leading-tight">
                            {{ c.code }} {{ c.isd }}
                          </span>
                          <span class="text-xs text-[var(--text-tertiary)] mt-0.5 leading-none">
                            {{ c.name }}
                          </span>
                        </div>
                      </div>
                      <div v-if="filteredCountries.length === 0" class="px-4 py-3 text-xs text-[var(--text-tertiary)] text-center">
                        No countries found
                      </div>
                    </div>
                  </div>
                </div>
                <div class="md:col-span-4">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Phone number</label>
                  <div class="relative">
                    <input
                      type="text"
                      v-model="btn.phone"
                      class="form-control pr-12"
                      placeholder="Phone number"
                      maxlength="20"
                      :class="{'border-red-500 focus:border-red-500': !btn.phone}"
                    />
                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-tertiary)]">
                      {{ btn.phone ? btn.phone.length : 0 }}/20
                    </span>
                  </div>
                </div>
              </template>

              <!-- VOICE_CALL options -->
              <template v-else-if="btn.type === 'VOICE_CALL'">
                <div class="md:col-span-3">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Active for</label>
                  <select class="form-control" v-model="btn.active_for">
                    <option value="7 days">7 days</option>
                    <option value="15 days">15 days</option>
                    <option value="30 days">30 days</option>
                  </select>
                </div>
              </template>

              <!-- FLOW options -->
              <template v-else-if="btn.type === 'FLOW'">
                <div class="md:col-span-3">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Flow Name / link</label>
                  <select class="form-control" v-model="btn.flow_name" @change="onFlowChange(btn)">
                    <option value="">Select a flow</option>
                    <option v-for="f in whatsappStore.flows" :key="f.name" :value="f.name || f.flow_name">
                      {{ f.flow_name || f.name }} ({{ f.flow_id }})
                    </option>
                    <option v-if="btn.flow_name && !whatsappStore.flows.some(f => (f.name === btn.flow_name || f.flow_name === btn.flow_name))" :value="btn.flow_name">
                      {{ btn.flow_name }} (Current)
                    </option>
                    <option value="__NEW_FLOW__">+ Create New Flow</option>
                  </select>
                </div>
                <div class="md:col-span-3">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Flow ID</label>
                  <input type="text" v-model="btn.flow_id" class="form-control" placeholder="Meta Flow ID" />
                </div>
              </template>

              <!-- COPY_CODE options -->
              <template v-else-if="btn.type === 'COPY_CODE'">
                <div class="md:col-span-4">
                  <label class="form-label text-[11px] text-[var(--text-secondary)] font-bold uppercase mb-1">Coupon / Offer Code</label>
                  <div class="relative">
                    <input
                      type="text"
                      v-model="btn.coupon_code"
                      class="form-control pr-12"
                      placeholder="e.g. SAVE50"
                      maxlength="15"
                    />
                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-tertiary)]">
                      {{ btn.coupon_code ? btn.coupon_code.length : 0 }}/15
                    </span>
                  </div>
                </div>
              </template>
            </div>

            <!-- Under Card Row Notices & Checkboxes -->
            <!-- Visit website conversion checkbox -->
            <div v-if="btn.type === 'URL'" class="mt-3 flex items-center gap-2 pl-1">
              <input type="checkbox" :id="'track-app-conversions-' + idx" v-model="btn.track_conversions" class="rounded border-[var(--border)] text-[var(--status-blue-fg)] focus:ring-[var(--brand)] w-4 h-4 cursor-pointer" />
              <label :for="'track-app-conversions-' + idx" class="text-xs text-[var(--text-secondary)] cursor-pointer select-none">
                Track app conversions (Marketing Messages API for WhatsApp only)
              </label>
            </div>

            <!-- Voice Call info notice -->
            <div v-if="btn.type === 'VOICE_CALL'" class="mt-3 bg-[var(--status-blue-bg)] border border-[var(--status-blue-bg)] rounded-lg p-3 text-xs text-[var(--status-blue-fg)] flex items-start gap-2.5">
              <FeatherIcon name="info" class="w-4 h-4 text-[var(--status-blue-fg)] mt-0.5 flex-shrink-0" />
              <div>
                Turn on calling in the <a :href="WHATSAPP_MANAGER_URL" target="_blank" class="text-[var(--status-blue-fg)] hover:underline font-medium">WhatsApp Manager portal</a>. Alternatively, you can use the Phone Number Settings API. <a :href="WHATSAPP_DOCS_CALLING_URL" target="_blank" class="text-[var(--status-blue-fg)] hover:underline">About calling on WhatsApp</a>
              </div>
            </div>

            <!-- Phone Number Validation notice -->
            <div v-if="btn.type === 'PHONE_NUMBER' && !btn.phone" class="mt-2 text-xs text-[var(--status-red-fg)] pl-1 font-medium">
              You need to enter a phone number. Please add a valid phone number.
            </div>

          </div>

          <!-- Global Link Tracking Checkbox -->
          <div v-if="hasWebsiteButton" class="mt-4 flex items-start gap-2.5 p-3 bg-[var(--bg-sunken)] border border-[var(--border)] rounded-lg">
            <input type="checkbox" id="use-link-tracking" v-model="form.use_link_tracking" class="rounded border-[var(--border)] text-[var(--status-blue-fg)] focus:ring-[var(--brand)] w-4.5 h-4.5 cursor-pointer mt-0.5" />
            <label for="use-link-tracking" class="text-xs text-[var(--text-primary)] leading-normal cursor-pointer select-none">
              You direct Meta to use link tracking to report website clicks. When this box is unticked, you will not see insights for website clicks.
            </label>
          </div>
        </div>

        <!-- Validation Error Panel -->
        <p v-if="validationError" class="validation-err">{{ validationError }}</p>

        <!-- Footer actions inside the form card -->
        <footer class="editor-footer">
          <button class="btn btn-default" :disabled="isSaving || isSubmitting" @click="onCancel">Cancel</button>
          <div class="grow"></div>
          <button class="btn btn-default" :disabled="isSaving || isSubmitting" @click="saveDraft">
            {{ isSaving ? 'Saving…' : 'Save as Draft' }}
          </button>
          <button class="btn btn-primary" :disabled="isSaving || isSubmitting" @click="submitForApproval">
            {{ isSubmitting ? 'Submitting…' : 'Submit for Approval' }}
          </button>
        </footer>
      </div>

      <!-- Preview Panel -->
      <aside class="preview-panel">
        <h3 class="preview-heading">Preview</h3>
        <div class="phone-frame">
          <!-- WhatsApp-style chat header -->
          <div class="wa-preview-header">
            <div class="wa-preview-avatar">
              <FeatherIcon name="message-circle" class="w-4 h-4" />
            </div>
            <div class="wa-preview-header-info">
              <span class="wa-preview-sender">{{ businessPreviewName }}</span>
              <span class="wa-preview-status">Template preview</span>
            </div>
          </div>

          <!-- Chat area -->
          <div class="wa-chat-bg">
            <div class="wa-message-card">
              <!-- Content block -->
              <div class="wa-message-content">
                <!-- Header preview — header_type '' means "None / Text";
                     TEXT is only inferred at save time, so match both. -->
                <div v-if="(!form.header_type || form.header_type === 'TEXT') && form.header" class="wa-msg-header">{{ previewHeader }}</div>
                <div v-else-if="form.header_type === 'IMAGE'" class="wa-msg-media">
                  <img v-if="form.media_sample" :src="form.media_sample" class="img-preview" alt="Preview" />
                  <template v-else>
                    <FeatherIcon name="image" class="w-10 h-10 text-[var(--text-tertiary)]" />
                    <span class="media-placeholder-text">Image</span>
                  </template>
                </div>
                <div v-else-if="form.header_type === 'VIDEO'" class="wa-msg-media">
                  <video v-if="form.media_sample" :src="form.media_sample" class="img-preview" controls></video>
                  <template v-else>
                    <FeatherIcon name="video" class="w-10 h-10 text-[var(--text-tertiary)]" />
                    <span class="media-placeholder-text">Video</span>
                  </template>
                </div>
                <div v-else-if="form.header_type === 'DOCUMENT'" class="wa-msg-media wa-msg-doc">
                  <FeatherIcon name="file-text" class="w-6 h-6 text-[var(--ink-600)] shrink-0" />
                  <span class="media-placeholder-text font-medium text-[var(--ink-800)] text-xs break-all leading-snug">
                    {{ form.media_sample ? getFileName(form.media_sample) : 'Document.pdf' }}
                  </span>
                </div>
                <div v-else-if="form.header_type === 'LOCATION'" class="wa-msg-media">
                  <FeatherIcon name="map-pin" class="w-10 h-10 text-[var(--text-tertiary)]" />
                  <span class="media-placeholder-text">Location (set at send time)</span>
                </div>
                <div v-else-if="form.header_type === 'PRODUCT'" class="wa-msg-media">
                  <FeatherIcon name="shopping-bag" class="w-10 h-10 text-[var(--text-tertiary)]" />
                  <span class="media-placeholder-text">Product (set at send time)</span>
                </div>

                <!-- Catalog template: product-thumbnail header image, then WhatsApp's fixed text header + sub-header -->
                <template v-if="form.template_type === 'CATALOGUE'">
                  <div class="wa-msg-media">
                    <img v-if="selectedProductDetails && selectedProductDetails.image" :src="selectedProductDetails.image" class="img-preview" alt="Preview" />
                    <template v-else>
                      <FeatherIcon name="shopping-bag" class="w-10 h-10 text-[var(--text-tertiary)]" />
                      <span class="media-placeholder-text">Catalog thumbnail</span>
                    </template>
                  </div>
                  <div class="wa-msg-catalog-title">View {{ businessPreviewName }}'s Catalog on WhatsApp</div>
                  <div class="wa-msg-catalog-sub">Browse pictures and details of their offerings.</div>
                </template>

                <!-- Limited-time offer: static labels only, no sample date -->
                <div v-if="form.limited_time_offer_enabled" class="wa-msg-offer">
                  <div v-if="form.lto_text" class="wa-msg-offer-text">{{ form.lto_text }}</div>
                  <div v-if="form.lto_has_expiration" class="wa-msg-offer-ends">Offer ends in ...</div>
                </div>

                <!-- Body -->
                <div class="wa-msg-body">{{ previewBody }}</div>

                <!-- Footer -->
                <div v-if="form.footer" class="wa-msg-footer">{{ form.footer }}</div>

                <!-- Template Type Specific Previews -->
                <div v-if="form.template_type === 'FLOW'" class="mt-2 p-2 bg-[var(--status-purple-bg)] rounded-lg text-xs text-[var(--status-purple-fg)] flex items-center justify-between border border-[var(--status-purple-bg)]">
                  <div class="flex items-center gap-1.5 font-medium">
                    <FeatherIcon name="layers" class="w-3.5 h-3.5 text-[var(--status-purple-fg)]" />
                    <span>Interactive Form</span>
                  </div>
                  <span class="text-[11px] text-[var(--status-purple-fg)] font-semibold">Open Flow</span>
                </div>

                <div v-else-if="form.template_type === 'ORDER_DETAILS'" class="mt-2 p-2 bg-[var(--status-amber-bg)] rounded-lg text-xs text-[var(--status-amber-fg)] flex items-center justify-between border border-[var(--status-amber-bg)]">
                  <div class="flex items-center gap-1.5 font-medium">
                    <FeatherIcon name="shopping-cart" class="w-3.5 h-3.5 text-[var(--status-amber-fg)]" />
                    <span>Order & Payment Info</span>
                  </div>
                  <span class="text-[11px] text-[var(--status-amber-fg)] font-semibold">Review Order</span>
                </div>

                <div v-else-if="form.template_type === 'ORDER_STATUS'" class="mt-2 p-2 bg-[var(--status-blue-bg)] rounded-lg text-xs text-[var(--status-blue-fg)] flex items-center justify-between border border-[var(--status-blue-bg)]">
                  <div class="flex items-center gap-1.5 font-medium">
                    <FeatherIcon name="truck" class="w-3.5 h-3.5 text-[var(--status-blue-fg)]" />
                    <span>Order Status & Tracking</span>
                  </div>
                  <span class="text-[11px] text-[var(--status-blue-fg)] font-semibold">Track Shipment</span>
                </div>

                <div v-else-if="form.template_type === 'CALL_PERMISSION_REQUEST' || form.is_call_permission" class="mt-2 p-2 bg-[var(--status-green-bg)] rounded-lg text-xs text-[var(--status-green-fg)] flex items-center gap-1.5 border border-[var(--status-green-bg)]">
                  <FeatherIcon name="phone-call" class="w-3.5 h-3.5 text-[var(--status-green-fg)] shrink-0" />
                  <span>Call permission request attached</span>
                </div>

                <!-- Offer Code Coupon Visual -->
                <div v-if="hasCopyCodeButton" class="offer-code-badge">
                  <span>{{ getCopyCodeVal }}</span>
                </div>

                <!-- Time -->
                <div class="wa-msg-time">{{ currentTime }}</div>
              </div>

              <!-- Buttons inside the bubble card -->
              <div v-if="form.buttons.length" class="wa-card-buttons">
                <div v-for="(btn, idx) in form.buttons" :key="btn.local_id" class="wa-card-button-row">
                  <FeatherIcon v-if="btn.type === 'URL'" name="external-link" class="w-4 h-4 wa-btn-icon" />
                  <FeatherIcon v-else-if="btn.type === 'PHONE_NUMBER'" name="phone" class="w-4 h-4 wa-btn-icon" />
                  <FeatherIcon v-else-if="btn.type === 'VOICE_CALL'" name="phone" class="w-4 h-4 wa-btn-icon" />
                  <FeatherIcon v-else-if="btn.type === 'FLOW'" name="shuffle" class="w-4 h-4 wa-btn-icon" />
                  <FeatherIcon v-else-if="btn.type === 'COPY_CODE'" name="copy" class="w-4 h-4 wa-btn-icon" />
                  <FeatherIcon v-else name="corner-up-right" class="w-4 h-4 wa-btn-icon" />
                  <span class="wa-btn-text">{{ btn.text || 'Button' }}</span>
                </div>
              </div>

              <!-- Fixed buttons injected by backend at push (catalog / SPM / MPM) -->
              <div v-if="form.template_type === 'CATALOGUE'" class="wa-card-buttons">
                <div class="wa-card-button-row">
                  <FeatherIcon name="shopping-bag" class="w-4 h-4 wa-btn-icon" />
                  <span class="wa-btn-text">View catalog</span>
                </div>
              </div>
              <div v-else-if="form.header_type === 'PRODUCT'" class="wa-card-buttons">
                <div class="wa-card-button-row">
                  <FeatherIcon name="external-link" class="w-4 h-4 wa-btn-icon" />
                  <span class="wa-btn-text">View</span>
                </div>
              </div>
              <div v-else-if="form.template_type === 'MPM'" class="wa-card-buttons">
                <div class="wa-card-button-row">
                  <FeatherIcon name="grid" class="w-4 h-4 wa-btn-icon" />
                  <span class="wa-btn-text">View items</span>
                </div>
              </div>
            </div>

            <!-- Media Card Carousel preview -->
            <div v-if="form.is_carousel && form.carousel_type === 'Media'" class="wa-carousel-row">
              <div v-for="(card, idx) in form.carousel_cards" :key="idx" class="wa-carousel-card">
                <div class="wa-carousel-img">
                  <img v-if="card.media_sample && card.header_format === 'IMAGE'" :src="card.media_sample" class="w-full h-full object-cover" alt="Image" />
                  <video v-else-if="card.media_sample && card.header_format === 'VIDEO'" :src="card.media_sample" class="w-full h-full object-cover"></video>
                  <FeatherIcon v-else name="image" class="w-8 h-8 text-[var(--text-tertiary)]" />
                </div>
                <div v-if="card.card_body" class="wa-carousel-body">
                  <span class="wa-carousel-title" style="white-space: normal;">{{ card.card_body }}</span>
                </div>
                <div v-if="card.button_type" class="wa-carousel-btn">
                  <span>{{ card.button_label || 'Button' }}</span>
                </div>
                <div v-if="card.button2_type" class="wa-carousel-btn">
                  <span>{{ card.button2_label || 'Button' }}</span>
                </div>
              </div>
            </div>

            <!-- Product Card Carousel preview -->
            <div v-else-if="form.is_carousel" class="wa-carousel-row">
              <div v-for="(card, idx) in form.carousel_cards" :key="idx" class="wa-carousel-card">
                <div class="wa-carousel-img">
                  <FeatherIcon name="image" class="w-8 h-8 text-[var(--text-tertiary)]" />
                </div>
                <div class="wa-carousel-body">
                  <span class="wa-carousel-title">Product name</span>
                  <span class="wa-carousel-price">$0.00</span>
                </div>
                <div class="wa-carousel-btn">
                  <FeatherIcon v-if="card.button_type === 'URL'" name="external-link" class="w-3.5 h-3.5 wa-btn-icon" />
                  <FeatherIcon v-else name="shopping-bag" class="w-3.5 h-3.5 wa-btn-icon" />
                  <span>{{ card.button_label || 'View' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Centralized Media Picker Modal -->
      <MediaLibraryPickerModal
        v-if="showMediaPicker"
        :accept="form.header_type === 'IMAGE' ? 'image/*' : form.header_type === 'VIDEO' ? 'video/*' : form.header_type === 'DOCUMENT' ? 'pdf' : 'any'"
        @close="showMediaPicker = false"
        @pick="onMediaPicked"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { FeatherIcon, frappeRequest, toast } from 'frappe-ui'
import PageHeader from '@/shared/ui/PageHeader.vue'
import MediaLibraryPickerModal from '@/shared/ui/MediaLibraryPickerModal.vue'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'
import {
  isLimitedTimeOfferEligible, mergeButtonConfiguration, parseLimitedTimeOffer, validateLimitedTimeOfferText,
} from '@/modules/whatsapp/utils/templateExtras'
import { charLength } from '@/shared/ui/whatsappOffer'
import { EXAMPLE_URL, EXAMPLE_PHONE_HINT } from '@/shared/constants/inputExamples'
import { previewLabelFor } from '@/shared/utils/previewValues'
import { WHATSAPP_MANAGER_URL, WHATSAPP_DOCS_CALLING_URL } from '@/shared/constants/externalLinks'
import { isAppInstalled } from '@/shared/store/installedApps'

const props = defineProps({
  name: { type: String, default: '' }
})

const whatsappStore = useWhatsApp()

const router = useRouter()
const route = useRoute()
const editName = computed(() => props.name || route.query.name || '')

const form = ref({
  waba: '',
  template_name: '',
  category: '',
  dlt_template_id: '',
  template_type: 'DEFAULT',
  is_call_permission: false,
  language: 'en',
  header_type: '',
  header: '',
  body: '',
  footer: '',
  buttons: [],
  type_of_variable: 'Name',
  media_sample: '',
  button_type: '',
  button_configuration: '',
  limited_time_offer_enabled: false,
  lto_text: '',
  lto_has_expiration: false,
  url_type: '',
  flow_id: '',
  offer_code: '',
  phone_number: '',
  country: '',
  quick_replies: '',
  button_order: '',
  sample_values: '',
  use_link_tracking: true,
  parameter_format: 'POSITIONAL',
  add_security_recommendation: false,
  code_expiration_minutes: null,
  is_carousel: false,
  carousel_type: 'Product', // 'Product' (SPM/catalog) | 'Media' (image/video cards)
  catalog_id: '',
  thumbnail_product_retailer_id: '',
  carousel_cards: [
    newCarouselCard('Product'),
    newCarouselCard('Product')
  ]
})

function newCarouselCard(type = 'Product') {
  if (type === 'Media') {
    return {
      header_format: 'IMAGE', media_sample: '', card_body: '',
      button_type: 'Quick Reply', button_label: 'Send me more like this!', website_url: '', example_url: '', phone_number: '',
      button2_type: '', button2_label: '', button2_website_url: '', button2_example_url: '', button2_phone_number: ''
    }
  }
  return { header_format: 'PRODUCT', button_type: 'SPM', button_label: 'View', website_url: '' }
}

const availableTemplateTypes = computed(() => {
  if (form.value.category === 'AUTHENTICATION' || form.value.category === 'OTP') {
    return [
      { value: 'OTP', label: 'One-time passcode (OTP)' }
    ]
  }
  if (form.value.category === 'UTILITY') {
    return [
      { value: 'DEFAULT', label: 'Default' },
      { value: 'MPM', label: 'Multi-Product Message' },
      { value: 'FLOW', label: 'Flows' },
      { value: 'ORDER_STATUS', label: 'Order status' },
      { value: 'ORDER_DETAILS', label: 'Order details' },
      { value: 'CALL_PERMISSION_REQUEST', label: 'Calling permissions request' }
    ]
  }
  return [
    { value: 'DEFAULT', label: 'Default' },
    { value: 'CATALOGUE', label: 'Catalogue' },
    { value: 'MPM', label: 'Multi-Product Message' },
    { value: 'FLOW', label: 'Flows' },
    { value: 'ORDER_DETAILS', label: 'Order details' },
    { value: 'CALL_PERMISSION_REQUEST', label: 'Calling permissions request' }
  ]
})

function onCategoryChange() {
  if (form.value.category === 'AUTHENTICATION' || form.value.category === 'OTP') {
    form.value.template_type = 'OTP'
    // Auth templates don't support header, carousel, footer, or custom buttons.
    // Clear incompatible fields so stale values aren't sent to Meta.
    form.value.header_type = ''
    form.value.header = ''
    form.value.media_sample = ''
    form.value.is_carousel = false
    form.value.footer = ''
    form.value.buttons = []
  } else {
    const validValues = availableTemplateTypes.value.map(t => t.value)
    if (!validValues.includes(form.value.template_type)) {
      form.value.template_type = 'DEFAULT'
    }
  }
}

const showAddButtonDropdown = ref(false)
const bodyTextareaRef = ref(null)

function addVariableToBody() {
  const named = form.value.parameter_format === 'NAMED'
  let token = ''
  let cursorOffset = 0

  if (named) {
    token = '{{}}'
    cursorOffset = 2
  } else {
    const bodyText = form.value.body || ''
    const matches = [...bodyText.matchAll(/\{\{(\d+)\}\}/g)].map(m => parseInt(m[1]))
    const maxNum = matches.length ? Math.max(...matches) : 0
    token = `{{${maxNum + 1}}}`
    cursorOffset = token.length
  }

  const textarea = bodyTextareaRef.value
  if (textarea) {
    const start = textarea.selectionStart ?? (form.value.body || '').length
    const end = textarea.selectionEnd ?? (form.value.body || '').length
    const currentVal = form.value.body || ''
    form.value.body = currentVal.substring(0, start) + token + currentVal.substring(end)

    nextTick(() => {
      textarea.focus()
      const newCursorPos = start + cursorOffset
      textarea.setSelectionRange(newCursorPos, newCursorPos)
    })
  } else {
    form.value.body = (form.value.body || '') + token
  }
}

function isInsideVariable(val, pos) {
  const before = val.slice(0, pos)
  const lastOpen = before.lastIndexOf('{{')
  const lastClose = before.lastIndexOf('}}')
  return lastOpen !== -1 && lastOpen > lastClose
}

function sanitizeNamedVariables(text) {
  if (!text) return text
  return text.replace(/\{\{([^{}]*)\}\}/g, (_, inner) => {
    return '{{' + inner.replace(/\s+/g, '_').toLowerCase() + '}}'
  })
}

function handleVariableKeydown(e, getValue, setValue) {
  const target = e.target
  const pos = target.selectionStart
  const val = target.value || ''

  if (isInsideVariable(val, pos)) {
    // 1. Space -> replace with underscore
    if (e.key === ' ' || e.code === 'Space') {
      e.preventDefault()
      const start = target.selectionStart
      const end = target.selectionEnd
      const currentVal = getValue() || ''
      setValue(currentVal.substring(0, start) + '_' + currentVal.substring(end))
      nextTick(() => {
        target.setSelectionRange(start + 1, start + 1)
      })
      return
    }

    // 2. Uppercase letter -> force small letter (lowercase)
    if (e.key && e.key.length === 1 && /[A-Z]/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault()
      const start = target.selectionStart
      const end = target.selectionEnd
      const currentVal = getValue() || ''
      const lowerChar = e.key.toLowerCase()
      setValue(currentVal.substring(0, start) + lowerChar + currentVal.substring(end))
      nextTick(() => {
        target.setSelectionRange(start + 1, start + 1)
      })
      return
    }
  }
}

function onBodyKeydown(e) {
  handleVariableKeydown(
    e,
    () => form.value.body,
    (val) => { form.value.body = val }
  )
}

function onBodyInput(e) {
  const textarea = e.target
  const val = textarea.value || ''
  const newVal = sanitizeNamedVariables(val)
  if (newVal !== val) {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    form.value.body = newVal
    nextTick(() => {
      textarea.setSelectionRange(start, end)
    })
  }
}

function onHeaderKeydown(e) {
  handleVariableKeydown(
    e,
    () => form.value.header,
    (val) => { form.value.header = val }
  )
}

function onHeaderInput(e) {
  const input = e.target
  const val = input.value || ''
  const newVal = sanitizeNamedVariables(val)
  if (newVal !== val) {
    const start = input.selectionStart
    const end = input.selectionEnd
    form.value.header = newVal
    nextTick(() => {
      input.setSelectionRange(start, end)
    })
  }
}

// Variable extraction and samples handling.
// POSITIONAL matches {{1}}, {{2}}; NAMED matches {{first_name}} etc.
const extractedVariables = computed(() => {
  const bodyText = form.value.body || ''
  const named = form.value.parameter_format === 'NAMED'
  const regex = named ? /\{\{([a-zA-Z_]\w*)\}\}/g : /\{\{(\d+)\}\}/g
  const matches = []
  let match
  while ((match = regex.exec(bodyText)) !== null) {
    if (!matches.includes(match[1])) {
      matches.push(match[1])
    }
  }
  if (!named) matches.sort((a, b) => parseInt(a) - parseInt(b))
  return matches
})

const variableSamples = ref({})

// Parse a stored sample_values string into {var: sample} — NAMED uses
// "key=value,key2=value2", POSITIONAL uses plain "value1,value2".
function parseSampleValues(sampleStr, vars, named) {
  const out = {}
  const parts = (sampleStr || '').split(',')
  if (named) {
    const byKey = {}
    for (const p of parts) {
      const idx = p.indexOf('=')
      if (idx > 0) byKey[p.slice(0, idx).trim()] = p.slice(idx + 1).trim()
    }
    vars.forEach(v => { out[v] = byKey[v] || '' })
  } else {
    vars.forEach((v, idx) => { out[v] = (parts[idx] || '').trim() })
  }
  return out
}

watch([extractedVariables, () => form.value.parameter_format], ([newVars]) => {
  const named = form.value.parameter_format === 'NAMED'
  const parsed = parseSampleValues(form.value.sample_values, newVars, named)
  const newSamples = {}
  newVars.forEach((v) => {
    newSamples[v] = variableSamples.value[v] !== undefined ? variableSamples.value[v] : parsed[v] || ''
  })
  variableSamples.value = newSamples
}, { immediate: true })

watch(variableSamples, (newVal) => {
  const named = form.value.parameter_format === 'NAMED'
  const parts = extractedVariables.value.map(v =>
    named ? `${v}=${newVal[v] || ''}` : (newVal[v] || '')
  )
  form.value.sample_values = parts.join(',')
}, { deep: true })

const hasWebsiteButton = computed(() => {
  return form.value.buttons.some(b => b.type === 'URL')
})

function addButton(type) {
  addNewButton(type)
  showAddButtonDropdown.value = false
}

function onButtonTypeChange(idx, newType) {
  const buttons = form.value.buttons
  const otherButtons = buttons.filter((_, i) => i !== idx)

  const numUrl = otherButtons.filter(b => b.type === 'URL').length
  const numPhone = otherButtons.filter(b => b.type === 'PHONE_NUMBER').length
  const numVoice = otherButtons.filter(b => b.type === 'VOICE_CALL').length
  const numFlow = otherButtons.filter(b => b.type === 'FLOW').length
  const numCopy = otherButtons.filter(b => b.type === 'COPY_CODE').length

  if (newType === 'URL' && numUrl >= 2) {
    validationError.value = 'Maximum of 2 Visit website buttons is allowed.'
    return
  }
  if (newType === 'PHONE_NUMBER' && numPhone >= 1) {
    validationError.value = 'Maximum of 1 Call Phone Number button is allowed.'
    return
  }
  if (newType === 'VOICE_CALL' && numVoice >= 1) {
    validationError.value = 'Maximum of 1 Call on WhatsApp button is allowed.'
    return
  }
  if (newType === 'FLOW' && numFlow >= 1) {
    validationError.value = 'Maximum of 1 Complete flow button is allowed.'
    return
  }
  if (newType === 'COPY_CODE' && numCopy >= 1) {
    validationError.value = 'Maximum of 1 Copy offer code button is allowed.'
    return
  }

  validationError.value = ''
  const btn = form.value.buttons[idx]
  btn.type = newType
  
  if (newType === 'VOICE_CALL') {
    btn.text = 'Call on WhatsApp'
    btn.active_for = '7 days'
    btn.voice_call_phone = ''
  } else if (newType === 'URL') {
    btn.text = 'Visit website'
    btn.url_type = 'Static'
    btn.url = ''
    btn.track_conversions = true
  } else if (newType === 'PHONE_NUMBER') {
    btn.text = 'Call phone number'
    btn.country = 'US +1'
    btn.phone = ''
  } else if (newType === 'QUICK_REPLY') {
    btn.text = 'Custom'
  } else if (newType === 'FLOW') {
    btn.text = 'View flow'
    btn.flow_name = ''
    btn.flow_id = ''
  } else if (newType === 'COPY_CODE') {
    btn.text = 'Copy offer code'
    btn.coupon_code = ''
  }
}

// Catalogue & Product selection logic
const availableCatalogs = ref([])
const catalogProducts = ref([])
const loadingCatalogs = ref(false)
const loadingProducts = ref(false)

async function fetchAvailableCatalogs() {
  if (!form.value.waba || !isAppInstalled('msuite_commerce')) {
    availableCatalogs.value = []
    return
  }
  loadingCatalogs.value = true
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_commerce.meta_ecommerce.api.v1.catalog.list_catalogs',
      method: 'GET',
      params: { whatsapp_account: form.value.waba }
    })
    availableCatalogs.value = res?.message || res || []
    if (availableCatalogs.value.length > 0 && !form.value.catalog_id) {
      form.value.catalog_id = availableCatalogs.value[0].catalog_id || availableCatalogs.value[0].name
      await fetchCatalogProducts()
    }
  } catch (err) {
    console.error('Failed to fetch catalogs:', err)
  } finally {
    loadingCatalogs.value = false
  }
}

async function fetchCatalogProducts() {
  if (!form.value.catalog_id) {
    catalogProducts.value = []
    return
  }
  loadingProducts.value = true
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_commerce.meta_ecommerce.api.v1.catalog.list_catalog_products',
      method: 'GET',
      params: { whatsapp_account: form.value.waba, catalog_id: form.value.catalog_id }
    })
    catalogProducts.value = res?.message || res || []
    if (catalogProducts.value.length > 0 && !form.value.thumbnail_product_retailer_id) {
      form.value.thumbnail_product_retailer_id = catalogProducts.value[0].item_code || ''
    }
  } catch (err) {
    console.error('Failed to fetch catalog products:', err)
  } finally {
    loadingProducts.value = false
  }
}

const selectedProductDetails = computed(() => {
  if (!form.value.thumbnail_product_retailer_id || !catalogProducts.value.length) return null
  return catalogProducts.value.find(p => p.item_code === form.value.thumbnail_product_retailer_id) || catalogProducts.value[0]
})

// Purpose: react to a Template Type change — set call-permission/category defaults and
// clear the carousel flag for types that can't be carousels (MPM / SPM PRODUCT header).
// WhatsApp-only: yes — edits a WhatsApp template.
function onTemplateTypeChange() {
  if (form.value.template_type === 'CALL_PERMISSION_REQUEST') {
    form.value.is_call_permission = true
  } else {
    form.value.is_call_permission = false
  }
  if (form.value.template_type === 'CATALOGUE' || form.value.template_type === 'MPM' || form.value.header_type === 'PRODUCT') {
    // Meta only accepts catalog/MPM templates in the MARKETING category.
    if (form.value.template_type === 'CATALOGUE' || form.value.template_type === 'MPM') form.value.category = 'MARKETING'
    fetchAvailableCatalogs()
  }
  // Carousel is mutually exclusive with MPM/SPM/Catalog — never carry a stale flag.
  if (form.value.template_type === 'MPM' || form.value.header_type === 'PRODUCT') {
    form.value.is_carousel = false
  }
}

const wabaAccounts = ref([])
const languagesList = ref([])
const phoneNumbers = ref([])
const validationError = ref('')
const showMediaPicker = ref(false)
const collapsedButtons = ref([])
const isSaving = ref(false)
const isSubmitting = ref(false)

// Sender name shown in the WhatsApp-style preview header
const businessPreviewName = computed(() => {
  const acc = Array.isArray(wabaAccounts.value) ? wabaAccounts.value.find(a => a.name === form.value.waba) : null
  return acc?.account_name || acc?.name || 'Your Business'
})

// Errors were only rendered in a panel at the very bottom of the form —
// off-screen when the user clicks Submit, so a failed validation looked
// like the button did nothing. Surface every error as a toast and scroll
// the panel into view.
watch(validationError, async (msg) => {
  if (!msg) return
  if (window.frappe?.show_alert) {
    window.frappe.show_alert({ message: msg, indicator: 'red' })
  }
  await nextTick()
  document.querySelector('.validation-err')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})

const countryDialingCodes = ref([])
const countrySearchQuery = ref('')
const activeCountryDropdownIdx = ref(null)

const filteredCountries = computed(() => {
  const query = (countrySearchQuery.value || '').trim().toLowerCase()
  if (!query) return countryDialingCodes.value
  return countryDialingCodes.value.filter(c => 
    c.name.toLowerCase().includes(query) ||
    c.code.toLowerCase().includes(query) ||
    c.isd.includes(query)
  )
})

function openCountryDropdown(idx) {
  countrySearchQuery.value = ''
  activeCountryDropdownIdx.value = idx
}

function selectCountry(idx, countryObj) {
  const btn = form.value.buttons[idx]
  if (btn) {
    btn.country = `${countryObj.code} ${countryObj.isd}`
  }
  activeCountryDropdownIdx.value = null
}

async function fetchCountryCodes() {
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_country_dialing_codes',
      method: 'POST',
    })
    countryDialingCodes.value = res || []
  } catch (e) {
    console.error('Failed to fetch country dialing codes', e)
  }
}


const currentTime = computed(() => {
  const now = new Date()
  return now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
})

// Variables preview replacements — works for {{1}} and {{first_name}}
const previewBody = computed(() => {
  let body = form.value.body || 'Message body will appear here...'
  return body.replace(/\{\{(\w+)\}\}/g, (match, g1) => {
    const sample = variableSamples.value[g1]
    if (sample && String(sample).trim()) return String(sample).trim()

    const ordinal = extractedVariables.value.indexOf(g1)
    if (form.value.type_of_variable === 'Number') {
      return (12345 + (ordinal + 1) * 1111).toString()
    }
    return previewLabelFor(g1)
  })
})

const previewHeader = computed(() => {
  let hdr = form.value.header || ''
  return hdr.replace(/\{\{(\d+)\}\}/g, (match, g1) => {
    if (form.value.type_of_variable === 'Number') {
      return '99999'
    }
    return previewLabelFor(g1)
  })
})

const hasCopyCodeButton = computed(() => {
  return form.value.buttons.some(b => b.type === 'COPY_CODE')
})

const getCopyCodeVal = computed(() => {
  const btn = form.value.buttons.find(b => b.type === 'COPY_CODE')
  return btn ? btn.coupon_code || 'CODE123' : 'CODE123'
})

// ---- Limited-time offer -------------------------------------------------
// Raw `button_configuration` as loaded; the save merges into it so keys the
// editor does not own (e.g. `limited_time_offer` written by sync) survive.
const loadedButtonConfiguration = ref('')
const ltoNotice = ref('')
// Character limit comes from the backend; null until known (server validates then).
const ltoTextMax = ref(null)
const isLtoEligible = computed(() => isLimitedTimeOfferEligible(form.value.category, form.value.header_type))
const ltoRemaining = computed(() => ltoTextMax.value - charLength(form.value.lto_text))
const ltoTextError = computed(() =>
  form.value.limited_time_offer_enabled && form.value.lto_text
    ? validateLimitedTimeOfferText(form.value.lto_text, ltoTextMax.value)
    : '')

/** Clears the notice and, when turned on, the footer (Meta disallows both together). */
function onLtoToggle() {
  ltoNotice.value = ''
  if (form.value.limited_time_offer_enabled) form.value.footer = ''
}

/**
 * Fetch the offer-text character limit from the backend so it is not repeated
 * here. Side effect: sets ltoTextMax. On failure the limit stays null and the
 * server validates on save.
 */
async function fetchLtoTextLimit() {
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_whatsapp_template_limits',
      method: 'POST',
    })
    ltoTextMax.value = Number(res?.lto_text_max) || null
  } catch (e) {
    console.error('Failed to load template limits', e)
  }
}

// Leaving Marketing / image-video turns the offer off and tells the user why.
watch(isLtoEligible, (eligible) => {
  if (!eligible && form.value.limited_time_offer_enabled) {
    form.value.limited_time_offer_enabled = false
    ltoNotice.value = 'Limited-time offer was turned off: it needs the Marketing category and an image or video header.'
  }
})

/**
 * Offer payload for mergeButtonConfiguration: object when on, null when off
 * (removes the stored key).
 * @returns {{text: string, hasExpiration: boolean}|null}
 */
function currentLimitedTimeOffer() {
  return form.value.limited_time_offer_enabled
    ? { text: form.value.lto_text, hasExpiration: form.value.lto_has_expiration }
    : null
}

// Watch header type to clear media sample when type changes
watch(() => form.value.header_type, (newType) => {
  if (!['IMAGE', 'VIDEO', 'DOCUMENT'].includes(newType)) {
    form.value.media_sample = ''
  }
})

async function fetchWabaAccounts() {
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_waba_accounts',
      method: 'POST',
    })
    wabaAccounts.value = res || []
  } catch (e) {
    console.error('Failed to fetch WABA accounts', e)
  }
}

async function fetchLanguages() {
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_languages_list',
      method: 'POST',
    })
    languagesList.value = res || []
  } catch (e) {
    console.error('Failed to fetch languages list', e)
  }
}

async function onWabaChange() {
  form.value.phone_number = ''
  phoneNumbers.value = []
  if (!form.value.waba) return

  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_waba_phone_numbers',
      method: 'POST',
      params: { waba_name: form.value.waba }
    })
    phoneNumbers.value = res || []
  } catch (e) {
    console.error('Failed to fetch WABA phone numbers', e)
  }

  if (form.value.template_type === 'CATALOGUE' || form.value.template_type === 'MPM' || form.value.header_type === 'PRODUCT' || form.value.catalog_id) {
    await fetchAvailableCatalogs()
  }
}

function onTemplateNameInput(e) {
  const input = e.target
  const originalSelectionStart = input.selectionStart
  const originalLength = input.value.length

  let val = input.value
  val = val.toLowerCase()
  val = val.replace(/[\s-]/g, '_')
  val = val.replace(/[^a-z0-9_]/g, '')
  val = val.replace(/_+/g, '_')

  form.value.template_name = val

  nextTick(() => {
    const newLength = val.length
    const diff = newLength - originalLength
    let newSelectionStart = originalSelectionStart + diff
    if (newSelectionStart < 0) newSelectionStart = 0
    input.setSelectionRange(newSelectionStart, newSelectionStart)
  })
}

function onTemplateNameBlur() {
  let val = form.value.template_name || ''
  if (val) {
    val = val.replace(/^_+|_+$/g, '')
    form.value.template_name = val
  }
  validateTemplateName()
}

function validateTemplateName() {
  let val = form.value.template_name || ''
  val = val.toLowerCase()
  val = val.replace(/[\s-]/g, '_')
  val = val.replace(/[^a-z0-9_]/g, '')
  val = val.replace(/_+/g, '_')
  val = val.replace(/^_+|_+$/g, '')

  if (!val) {
    validationError.value = 'Template Name is required and must contain only lowercase letters, numbers, and underscores.'
    return false
  } else {
    if (validationError.value.includes('Template Name')) {
      validationError.value = ''
    }
    return true
  }
}

// Media Sample Upload Helpers
const mediaPickerCardIdx = ref(null)

function setCarouselType(type) {
  form.value.carousel_type = type
  // Reset to two fresh cards of the chosen kind.
  form.value.carousel_cards = [newCarouselCard(type), newCarouselCard(type)]
}

function addCarouselCard() {
  if (form.value.carousel_cards.length >= 10) return
  // New card mirrors the first card's button combo (Meta needs identical components).
  const first = form.value.carousel_cards[0] || {}
  const card = newCarouselCard(form.value.carousel_type)
  card.button_type = first.button_type || card.button_type
  card.button2_type = first.button2_type || ''
  form.value.carousel_cards.push(card)
}

function removeCarouselCard(idx) {
  if (form.value.carousel_cards.length <= 2) return
  form.value.carousel_cards.splice(idx, 1)
}

function openMediaLibrary() {
  mediaPickerCardIdx.value = null
  showMediaPicker.value = true
}

function openCardMedia(idx) {
  mediaPickerCardIdx.value = idx
  showMediaPicker.value = true
}

function onMediaPicked(asset) {
  const fileUrl = asset.file_url
  const ext = fileUrl.split('.').pop().toLowerCase()

  // Media Carousel card target
  if (mediaPickerCardIdx.value !== null) {
    const card = form.value.carousel_cards[mediaPickerCardIdx.value]
    const isVideo = ['mp4', 'mov'].includes(ext)
    const isImage = ['jpg', 'jpeg', 'png', 'webp'].includes(ext)
    if (!isVideo && !isImage) {
      validationError.value = 'Card media must be an image (jpg, png, webp) or video (mp4, mov).'
      showMediaPicker.value = false
      mediaPickerCardIdx.value = null
      return
    }
    card.media_sample = fileUrl
    card.header_format = isVideo ? 'VIDEO' : 'IMAGE'
    validationError.value = ''
    showMediaPicker.value = false
    mediaPickerCardIdx.value = null
    return
  }

  if (form.value.header_type === 'IMAGE' && !['jpg', 'jpeg', 'png', 'webp'].includes(ext)) {
    validationError.value = 'Invalid image format. Allowed: jpg, png, jpeg, webp'
    showMediaPicker.value = false
    return
  }
  if (form.value.header_type === 'VIDEO' && !['mp4', 'mov', '3gp', '3gpp'].includes(ext)) {
    validationError.value = 'Invalid video format. Allowed: mp4, 3gp, mov'
    showMediaPicker.value = false
    return
  }
  if (form.value.header_type === 'DOCUMENT' && ext !== 'pdf') {
    validationError.value = 'Invalid document format. Allowed: pdf (Meta only accepts PDF template samples)'
    showMediaPicker.value = false
    return
  }

  form.value.media_sample = fileUrl
  validationError.value = ''
  showMediaPicker.value = false
}

function onFlowChange(btn) {
  if (btn.flow_name === '__NEW_FLOW__') {
    btn.flow_name = ''
    btn.flow_id = ''
    // In the CRM tab there is no /msuite app: the Desk form keeps this editor open.
    window.open('/app/whatsapp-flow/new', '_blank')
    return
  }
  const selected = whatsappStore.flows.find(f => f.name === btn.flow_name || f.flow_name === btn.flow_name || f.flow_id === btn.flow_name)
  if (selected) {
    btn.flow_name = selected.name || selected.flow_name
    btn.flow_id = selected.flow_id || ''
  } else {
    btn.flow_id = ''
  }
}

function removeMediaSample() {
  form.value.media_sample = ''
}

function getFileName(url) {
  if (!url) return 'Document.pdf'
  const cleanUrl = String(url).split('?')[0].split('#')[0]
  const filename = cleanUrl.split('/').pop()
  return filename ? decodeURIComponent(filename) : 'Document.pdf'
}

// Button Builder Methods
function toggleButtonCollapse(idx) {
  if (collapsedButtons.value.includes(idx)) {
    collapsedButtons.value = collapsedButtons.value.filter(i => i !== idx)
  } else {
    collapsedButtons.value.push(idx)
  }
}

function getButtonIconName(type) {
  if (type === 'QUICK_REPLY') return 'corner-up-right'
  if (type === 'URL') return 'external-link'
  if (type === 'PHONE_NUMBER') return 'phone'
  if (type === 'FLOW') return 'shuffle'
  if (type === 'COPY_CODE') return 'copy'
  return 'plus'
}

function getButtonTypeName(type) {
  if (type === 'QUICK_REPLY') return 'Quick Reply'
  if (type === 'URL') return 'Visit Website'
  if (type === 'PHONE_NUMBER') return 'Call Phone'
  if (type === 'FLOW') return 'Flow'
  if (type === 'COPY_CODE') return 'Copy Offer Code'
  return type
}

function addNewButton(type) {
  const buttons = form.value.buttons
  if (buttons.length >= 10) {
    validationError.value = 'Maximum of 10 buttons total is allowed.'
    return
  }

  const numUrl = buttons.filter(b => b.type === 'URL').length
  const numPhone = buttons.filter(b => b.type === 'PHONE_NUMBER').length
  const numVoice = buttons.filter(b => b.type === 'VOICE_CALL').length
  const numFlow = buttons.filter(b => b.type === 'FLOW').length
  const numCopy = buttons.filter(b => b.type === 'COPY_CODE').length

  if (type === 'URL' && numUrl >= 2) {
    validationError.value = 'Maximum of 2 Visit website buttons is allowed.'
    return
  }
  if (type === 'PHONE_NUMBER' && numPhone >= 1) {
    validationError.value = 'Maximum of 1 Call Phone Number button is allowed.'
    return
  }
  if (type === 'VOICE_CALL' && numVoice >= 1) {
    validationError.value = 'Maximum of 1 Call on WhatsApp button is allowed.'
    return
  }
  if (type === 'FLOW' && numFlow >= 1) {
    validationError.value = 'Maximum of 1 Complete flow button is allowed.'
    return
  }
  if (type === 'COPY_CODE' && numCopy >= 1) {
    validationError.value = 'Maximum of 1 Copy offer code button is allowed.'
    return
  }

  validationError.value = ''
  
  const newBtn = {
    type,
    text: type === 'COPY_CODE' ? 'Copy offer code' : 
          type === 'VOICE_CALL' ? 'Call on WhatsApp' : 
          type === 'URL' ? 'Visit website' : 
          type === 'PHONE_NUMBER' ? 'Call phone number' : 
          type === 'FLOW' ? 'View flow' : 'Custom',
    url: '',
    url_type: 'Static',
    example_url: '',
    phone: '',
    country: 'US +1',
    voice_call_phone: '',
    active_for: '7 days',
    flow_name: '',
    flow_id: '',
    coupon_code: '',
    track_conversions: true,
    local_id: Math.random().toString(36).slice(2, 11)
  }

  form.value.buttons.push(newBtn)
}

function moveButtonUp(idx) {
  if (idx === 0) return
  const temp = form.value.buttons[idx]
  form.value.buttons[idx] = form.value.buttons[idx - 1]
  form.value.buttons[idx - 1] = temp
  collapsedButtons.value = []
}

function moveButtonDown(idx) {
  if (idx === form.value.buttons.length - 1) return
  const temp = form.value.buttons[idx]
  form.value.buttons[idx] = form.value.buttons[idx + 1]
  form.value.buttons[idx + 1] = temp
  collapsedButtons.value = []
}

function duplicateButton(idx) {
  if (form.value.buttons.length >= 10) {
    validationError.value = 'Maximum of 10 buttons total is allowed.'
    return
  }
  const source = form.value.buttons[idx]
  addNewButton(source.type)
  const lastIndex = form.value.buttons.length - 1
  if (lastIndex >= 0 && form.value.buttons[lastIndex].type === source.type) {
    form.value.buttons[lastIndex] = {
      ...JSON.parse(JSON.stringify(source)),
      text: source.text ? `${source.text} (Copy)` : '',
      local_id: Math.random().toString(36).slice(2, 11)
    }
  }
}

function removeButton(idx) {
  form.value.buttons.splice(idx, 1)
  collapsedButtons.value = []
}

function validateForm() {
  validationError.value = ''
  if (!form.value.waba) {
    validationError.value = 'WhatsApp Business Account (WABA) is required.'
    return false
  }
  
  let name = form.value.template_name || ''
  name = name.toLowerCase()
  name = name.replace(/[\s-]/g, '_')
  name = name.replace(/[^a-z0-9_]/g, '')
  name = name.replace(/_+/g, '_')
  name = name.replace(/^_+|_+$/g, '')
  form.value.template_name = name

  if (!name) {
    validationError.value = 'Template Name is required and must contain only lowercase letters, numbers, and underscores.'
    return false
  }
  if (!form.value.category) {
    validationError.value = 'Category is required.'
    return false
  }
  if (!form.value.language) {
    validationError.value = 'Language is required.'
    return false
  }
  if (!form.value.body || !form.value.body.trim()) {
    validationError.value = 'Message Body is required.'
    return false
  }

  if (form.value.template_type === 'CATALOGUE' && form.value.category !== 'MARKETING') {
    // Catalog = MARKETING only (Meta rule). Catalogue/thumbnail are NOT
    // needed at create time — the CATALOG button is fixed and the header
    // thumbnail is an optional send-time param.
    validationError.value = 'Catalog templates must use the Marketing category.'
    return false
  }

  // SPM (PRODUCT header) and MPM templates are MARKETING-only per Meta.
  if ((form.value.header_type === 'PRODUCT' || form.value.template_type === 'MPM') && form.value.category !== 'MARKETING') {
    validationError.value = 'Single-Product and Multi-Product templates must use the Marketing category.'
    return false
  }
  if (form.value.limited_time_offer_enabled) {
    if (!isLtoEligible.value) {
      validationError.value = 'Limited-time offer needs the Marketing category and an image or video header.'
      return false
    }
    const offerError = validateLimitedTimeOfferText(form.value.lto_text, ltoTextMax.value)
    if (offerError) {
      validationError.value = offerError
      return false
    }
  }
  // Meta caps a Single-Product Message template's body at 160 characters.
  if (form.value.header_type === 'PRODUCT' && form.value.body.trim().length > 160) {
    validationError.value = 'Single-Product Message body cannot exceed 160 characters.'
    return false
  }

  if (form.value.is_carousel && form.value.carousel_type === 'Media') {
    const cards = form.value.carousel_cards
    if (cards.length < 2 || cards.length > 10) {
      validationError.value = 'A Media Card Carousel must define 2 to 10 cards.'
      return false
    }
    const combos = new Set(cards.map((c) => `${c.button_type || ''}|${c.button2_type || ''}`))
    if (combos.size > 1) {
      validationError.value = 'All media cards must use the same button combination.'
      return false
    }
    const bodyFlags = new Set(cards.map((c) => !!(c.card_body && c.card_body.trim())))
    if (bodyFlags.size > 1) {
      validationError.value = 'If any media card has body text, all cards must have body text.'
      return false
    }
    for (const card of cards) {
      if (!card.media_sample) {
        validationError.value = 'Every media card needs a header image or video.'
        return false
      }
      if (card.button_type === 'URL' && !card.website_url) {
        validationError.value = 'Website URL is required for a card with a Visit website button.'
        return false
      }
      if (card.button_type === 'Call Phone' && !card.phone_number) {
        validationError.value = 'Phone number is required for a card with a Call phone button.'
        return false
      }
    }
  } else if (form.value.is_carousel) {
    if (form.value.carousel_cards.length !== 2) {
      validationError.value = 'A Product Carousel template must define exactly 2 cards.'
      return false
    }
    const buttonTypes = new Set(form.value.carousel_cards.map((c) => c.button_type))
    if (buttonTypes.size > 1) {
      validationError.value = 'Both carousel cards must use the same button type — Meta doesn\'t support mixing SPM and URL buttons.'
      return false
    }
    for (const card of form.value.carousel_cards) {
      if (card.button_type === 'URL' && !card.website_url) {
        validationError.value = 'Website URL is required for a carousel card with a Visit Website button.'
        return false
      }
    }
  }

  // Enforce button counts and text limits
  if (form.value.buttons.length > 10) {
    validationError.value = 'Maximum of 10 buttons total is allowed.'
    return false
  }

  const numUrl = form.value.buttons.filter(b => b.type === 'URL').length
  const numPhone = form.value.buttons.filter(b => b.type === 'PHONE_NUMBER').length
  const numVoice = form.value.buttons.filter(b => b.type === 'VOICE_CALL').length
  const numFlow = form.value.buttons.filter(b => b.type === 'FLOW').length
  const numCopy = form.value.buttons.filter(b => b.type === 'COPY_CODE').length

  if (numUrl > 2) {
    validationError.value = 'Maximum of 2 Visit website buttons is allowed.'
    return false
  }
  if (numPhone > 1) {
    validationError.value = 'Maximum of 1 Call Phone Number button is allowed.'
    return false
  }
  if (numVoice > 1) {
    validationError.value = 'Maximum of 1 Call on WhatsApp button is allowed.'
    return false
  }
  if (numFlow > 1) {
    validationError.value = 'Maximum of 1 Complete flow button is allowed.'
    return false
  }
  if (numCopy > 1) {
    validationError.value = 'Maximum of 1 Copy offer code button is allowed.'
    return false
  }

  const seenLabels = new Set()
  for (const btn of form.value.buttons) {
    const text = (btn.text || '').trim()
    if (!text) {
      validationError.value = 'Button Text is required for all buttons.'
      return false
    }
    if (seenLabels.has(text.toLowerCase())) {
      validationError.value = `You cannot enter the same text for multiple buttons: "${text}".`
      return false
    }
    seenLabels.add(text.toLowerCase())

    if (btn.type === 'QUICK_REPLY' && text.length > 25) {
      validationError.value = 'Quick Reply text cannot exceed 25 characters.'
      return false
    }
    if (btn.type !== 'QUICK_REPLY' && text.length > 40) {
      validationError.value = 'Button text cannot exceed 40 characters.'
      return false
    }
    if (btn.type === 'COPY_CODE' && !btn.coupon_code) {
      validationError.value = 'Offer/Coupon Code is required for Copy offer code buttons.'
      return false
    }
    if (btn.type === 'COPY_CODE' && btn.coupon_code && btn.coupon_code.length > 15) {
      validationError.value = 'Coupon Code cannot exceed 15 characters.'
      return false
    }
    if (btn.type === 'PHONE_NUMBER' && !btn.phone) {
      validationError.value = 'Phone Number is required for all Call Phone Number buttons.'
      return false
    }
    if (btn.type === 'URL' && !btn.url) {
      validationError.value = 'Website URL is required for all Visit website buttons.'
      return false
    }
  }

  const bodyText = (form.value.body || '').trim()
  const vars = bodyText.match(/\{\{([^}]+)\}\}/g) || []
  if (vars.length > 1) {
    const staticText = bodyText.replace(/\{\{([^}]+)\}\}/g, ' ')
    const staticWords = (staticText.match(/\b\w+\b/g) || []).filter(Boolean)
    if (staticWords.length < vars.length * 2.5) {
      validationError.value = `This template has too many variables for its message length (${vars.length} variables for ${staticWords.length} words). Meta requires adding more text to the message body or reducing variables.`
      return false
    }
  }

  return true
}

async function checkDuplicateName() {
  if (editName.value) return false

  const langCode = form.value.language.replace('-', '_')
  const targetName = `${form.value.template_name}-${langCode}`

  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.check_template_duplicate',
      method: 'POST',
      params: {
        template_name: form.value.template_name,
        language: form.value.language
      }
    })
    if (res && res.length > 0) {
      validationError.value = `A template named "${form.value.template_name}" with language "${form.value.language}" already exists. Please choose a different template name.`
      return true
    }
  } catch (e) {
    console.error('Failed to check duplicate name', e)
    toast.error(prettifyFrappeError(e) || 'Failed to check duplicate name')
  }
  return false
}

// Purpose: turn the editor form into the WhatsApp Templates doc payload for save/submit,
// enforcing that carousel is mutually exclusive with MPM/SPM/Catalog.
// WhatsApp-only: yes — serializes a WhatsApp template.
function serializeTemplateDoc(statusValue) {
  const buttons = form.value.buttons.map((b, idx) => {
    let voicePhone = b.voice_call_phone
    if (b.type === 'VOICE_CALL' && !voicePhone) {
      if (phoneNumbers.value && phoneNumbers.value.length > 0) {
        voicePhone = phoneNumbers.value[0].number || phoneNumbers.value[0].id
      }
    }
    return {
      doctype: 'WhatsApp Button',
      button_type: b.type === 'QUICK_REPLY' ? 'Quick Reply' : 
                   b.type === 'URL' ? 'Visit Website' : 
                   b.type === 'PHONE_NUMBER' ? 'Call Phone' : 
                   b.type === 'FLOW' ? 'Flow' : 
                   b.type === 'VOICE_CALL' ? 'Voice Call' : 
                   b.type === 'COPY_CODE' ? 'Copy Offer Code' : 'OTP',
      otp_type: b.type === 'COPY_CODE' ? 'COPY_CODE' : '',
      button_label: b.text,
      website_url: b.type === 'URL' ? b.url : '',
      url_type: b.type === 'URL' ? b.url_type : '',
      example_url: b.type === 'URL' ? b.example_url : (b.type === 'COPY_CODE' ? b.coupon_code : ''),
      phone_number: b.type === 'PHONE_NUMBER' ? b.phone : '',
      voice_call_phone: voicePhone || '',
      sequence: idx + 1,
      flow: b.type === 'FLOW' ? (() => {
        const flowItem = whatsappStore.flows.find(f => f.name === b.flow_name || f.flow_name === b.flow_name || f.flow_id === b.flow_id || f.flow_id === b.flow_name)
        return flowItem ? (flowItem.name || flowItem.flow_name) : (b.flow_name || '')
      })() : '',
      flow_action: 'navigate',
      navigate_screen: b.type === 'FLOW' ? 'SCREEN_ID' : ''
    }
  })

  let mainButtonType = ''
  let mainUrlType = ''
  let mainFlowId = ''
  let mainOfferCode = ''
  let mainPhoneNumber = ''
  let mainCountry = ''
  let quickRepliesList = []
  
  form.value.buttons.forEach((b) => {
    if (b.type === 'QUICK_REPLY') {
      mainButtonType = 'Quick Reply'
      quickRepliesList.push(b.text)
    } else if (b.type === 'URL') {
      mainButtonType = 'Visit Website'
      mainUrlType = b.url_type
    } else if (b.type === 'PHONE_NUMBER') {
      mainButtonType = 'Call Phone'
      mainPhoneNumber = b.phone
      mainCountry = b.country
    } else if (b.type === 'FLOW') {
      mainButtonType = 'Flow'
      mainFlowId = b.flow_id
    } else if (b.type === 'COPY_CODE') {
      mainButtonType = 'Copy Offer Code'
      mainOfferCode = b.coupon_code
    } else if (b.type === 'VOICE_CALL') {
      mainButtonType = 'Voice Call'
    }
  })

  let finalHeaderType = form.value.header_type || ''
  let finalHeader = ''
  if (!['IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION', 'PRODUCT'].includes(finalHeaderType) && form.value.header?.trim()) {
    finalHeaderType = 'TEXT'
    finalHeader = form.value.header.trim()
  } else if (['IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION', 'PRODUCT'].includes(finalHeaderType)) {
    finalHeader = ''
  }

  // Carousel is mutually exclusive with MPM/SPM(PRODUCT header)/Catalog.
  const isCarousel = !!form.value.is_carousel
    && form.value.template_type !== 'MPM'
    && form.value.template_type !== 'CATALOGUE'
    && finalHeaderType !== 'PRODUCT'

  const doc = {
    doctype: 'WhatsApp Templates',
    template_name: form.value.template_name,
    whatsapp_account: form.value.waba,
    category: form.value.category,
    dlt_template_id: form.value.dlt_template_id || '',
    template_type: form.value.template_type || 'DEFAULT',
    is_call_permission: form.value.template_type === 'CALL_PERMISSION_REQUEST' || form.value.is_call_permission ? 1 : 0,
    language: form.value.language,
    header_type: finalHeaderType,
    header: finalHeader,
    template: form.value.body || '',
    footer: form.value.limited_time_offer_enabled ? '' : (form.value.footer || ''),
    status: statusValue,
    buttons: buttons,
    
    // Save new database columns
    type_of_variable: form.value.type_of_variable || 'Name',
    media_sample: form.value.media_sample || '',
    button_type: mainButtonType,
    button_configuration: mergeButtonConfiguration(loadedButtonConfiguration.value, {
      buttons: form.value.buttons,
      useLinkTracking: form.value.use_link_tracking,
      limitedTimeOffer: currentLimitedTimeOffer(),
    }),
    url_type: mainUrlType,
    flow_id: mainFlowId,
    offer_code: mainOfferCode,
    phone_number: mainPhoneNumber,
    country: mainCountry,
    quick_replies: JSON.stringify(quickRepliesList),
    button_order: JSON.stringify(form.value.buttons.map(b => b.type)),
    sample_values: form.value.sample_values || '',
    parameter_format: form.value.parameter_format || 'POSITIONAL',
    add_security_recommendation: form.value.add_security_recommendation ? 1 : 0,
    code_expiration_minutes: form.value.code_expiration_minutes || 0,
    catalog_id: form.value.catalog_id || '',
    thumbnail_product_retailer_id: form.value.thumbnail_product_retailer_id || '',
    is_carousel: isCarousel ? 1 : 0,
    carousel_cards: !isCarousel
      ? []
      : form.value.carousel_type === 'Media'
        ? form.value.carousel_cards.map((c) => ({
            header_format: c.header_format || 'IMAGE',
            media_sample: c.media_sample || '',
            card_body: c.card_body || '',
            button_type: c.button_type,
            button_label: c.button_label || '',
            website_url: c.button_type === 'URL' ? c.website_url : '',
            example_url: c.button_type === 'URL' ? (c.example_url || '') : '',
            phone_number: c.button_type === 'Call Phone' ? c.phone_number : '',
            button2_type: c.button2_type || '',
            button2_label: c.button2_type ? (c.button2_label || '') : '',
            button2_website_url: c.button2_type === 'URL' ? c.button2_website_url : '',
            button2_example_url: c.button2_type === 'URL' ? (c.button2_example_url || '') : '',
            button2_phone_number: c.button2_type === 'Call Phone' ? c.button2_phone_number : ''
          }))
        : form.value.carousel_cards.map((c) => ({
            header_format: 'PRODUCT',
            // Meta requires SPM button text to be exactly "View" — only URL
            // buttons get a customizable label.
            button_type: c.button_type,
            button_label: c.button_type === 'URL' ? (c.button_label || 'View') : 'View',
            website_url: c.button_type === 'URL' ? c.website_url : ''
          }))
  }

  return doc
}

async function saveDraft() {
  if (!validateForm()) return

  const isDuplicate = await checkDuplicateName()
  if (isDuplicate) return

  const doc = serializeTemplateDoc('Draft')

  isSaving.value = true
  try {
    if (editName.value) {
      doc.name = editName.value
    }
    await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.save_whatsapp_template',
      method: 'POST',
      params: { doc: JSON.stringify(doc) }
    })
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Template saved successfully.', indicator: 'green' })
    }
    router.push({ name: 'WhatsAppTemplates' })
  } catch (e) {
    console.error('Failed to save template', e)
    validationError.value = e?.messages?.[0] || e?.message || 'Failed to save template.'
    toast.error(prettifyFrappeError(e) || 'Failed to save template')
  } finally {
    isSaving.value = false
  }
}

async function submitForApproval() {
  if (!validateForm()) return
  
  const isDuplicate = await checkDuplicateName()
  if (isDuplicate) return

  const doc = serializeTemplateDoc('PENDING')

  const isEdit = !!editName.value
  let savedName = editName.value
  isSubmitting.value = true
  try {
    if (isEdit) {
      doc.name = editName.value
    }
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.save_whatsapp_template',
      method: 'POST',
      params: { doc: JSON.stringify(doc) }
    })
    if (res && res.name) {
      savedName = res.name
    }

    // New templates are pushed to Meta by after_insert (status PENDING).
    // Calling push_to_meta again here used to fire a second, *update*
    // call that Meta rejects for templates still in review.
    if (isEdit && savedName) {
      await frappeRequest({
        url: '/api/method/run_doc_method',
        method: 'POST',
        params: {
          dt: 'WhatsApp Templates',
          dn: savedName,
          method: 'push_to_meta'
        }
      })
    }

    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Template submitted for approval.', indicator: 'green' })
    }
    router.push({ name: 'WhatsAppTemplates' })
  } catch (e) {
    console.error('Failed to submit template', e)
    validationError.value = e?.messages?.[0] || e?.message || 'Failed to submit template.'
    toast.error(prettifyFrappeError(e) || 'Failed to submit template')
  } finally {
    isSubmitting.value = false
  }
}

function onCancel() {
  router.push({ name: 'WhatsAppTemplates' })
}

// Load existing template if editing
onMounted(async () => {
  await Promise.all([fetchWabaAccounts(), fetchLanguages(), fetchCountryCodes(), whatsappStore.fetchFlows(), fetchLtoTextLimit()])
  
  if (editName.value) {
    try {
      const res = await frappeRequest({
        url: '/api/method/msuite_whatsapp.api.v1.app.crud.get_whatsapp_template',
        method: 'POST',
        params: { name: editName.value }
      })
      if (res) {
        form.value.waba = res.whatsapp_account || ''
        await onWabaChange()
        form.value.template_name = res.template_name || ''
        form.value.category = res.category || ''
        form.value.dlt_template_id = res.dlt_template_id || ''
        form.value.template_type = res.template_type || (res.is_call_permission ? 'CALL_PERMISSION_REQUEST' : 'DEFAULT')
        form.value.is_call_permission = !!res.is_call_permission
        form.value.language = res.language || ''
        let initialHeaderType = res.header_type || ''
        if (initialHeaderType === 'TEXT') {
          initialHeaderType = ''
        }
        form.value.header_type = initialHeaderType
        form.value.header = res.header || ''
        form.value.body = res.template || ''
        form.value.footer = res.footer || ''
        form.value.sample_values = res.sample_values || ''
        
        // Load custom fields
        form.value.type_of_variable = res.type_of_variable || 'Name'
        form.value.media_sample = res.media_sample || res.sample || ''
        form.value.parameter_format = res.parameter_format || 'POSITIONAL'
        form.value.add_security_recommendation = !!res.add_security_recommendation
        form.value.catalog_id = res.catalog_id || ''
        form.value.thumbnail_product_retailer_id = res.thumbnail_product_retailer_id || ''
        if (form.value.template_type === 'CATALOGUE' || form.value.template_type === 'MPM' || form.value.header_type === 'PRODUCT' || form.value.catalog_id) {
          await fetchAvailableCatalogs()
          if (form.value.catalog_id) {
            await fetchCatalogProducts()
          }
        }
        form.value.is_carousel = !!res.is_carousel
        if (res.carousel_cards && res.carousel_cards.length) {
          const isMedia = res.carousel_cards.some((c) => ['IMAGE', 'VIDEO'].includes(c.header_format))
          form.value.carousel_type = isMedia ? 'Media' : 'Product'
          form.value.carousel_cards = res.carousel_cards.map((c) => (isMedia ? {
            header_format: c.header_format || 'IMAGE',
            media_sample: c.media_sample || '',
            card_body: c.card_body || '',
            button_type: c.button_type || 'Quick Reply',
            button_label: c.button_label || '',
            website_url: c.website_url || '',
            example_url: c.example_url || '',
            phone_number: c.phone_number || '',
            button2_type: c.button2_type || '',
            button2_label: c.button2_label || '',
            button2_website_url: c.button2_website_url || '',
            button2_example_url: c.button2_example_url || '',
            button2_phone_number: c.button2_phone_number || ''
          } : {
            header_format: 'PRODUCT',
            button_type: c.button_type || 'SPM',
            button_label: c.button_label || 'View',
            website_url: c.website_url || ''
          }))
        }

        loadedButtonConfiguration.value = res.button_configuration || ''
        const storedOffer = parseLimitedTimeOffer(res.button_configuration)
        form.value.limited_time_offer_enabled = storedOffer.enabled
        form.value.lto_text = storedOffer.text
        form.value.lto_has_expiration = storedOffer.hasExpiration

        // Parse UI-only extras stored in the button_configuration blob
        // (track_conversions, active_for, link tracking, …).
        let blobButtons = null
        let blobLinkTracking = true
        if (res.button_configuration) {
          try {
            const parsed = JSON.parse(res.button_configuration)
            if (Array.isArray(parsed)) {
              blobButtons = parsed
            } else if (parsed && parsed.buttons) {
              blobButtons = parsed.buttons
              blobLinkTracking = parsed.use_link_tracking !== undefined ? parsed.use_link_tracking : true
            }
          } catch (e) {
            console.error('Failed to parse button_configuration', e)
            toast.error(prettifyFrappeError(e) || 'Failed to parse button_configuration')
          }
        }
        form.value.use_link_tracking = blobLinkTracking

        // The child table is the source of truth (it's what the backend
        // pushes to Meta, and what Desk edits / Meta sync write). The JSON
        // blob used to win outright, so Desk-side button edits were
        // silently ignored here — now it only contributes UI extras.
        if (res.buttons && res.buttons.length) {
          form.value.buttons = res.buttons.map((b, i) => {
            let type = 'QUICK_REPLY'
            if (b.button_type === 'Visit Website') type = 'URL'
            else if (b.button_type === 'Call Phone') type = 'PHONE_NUMBER'
            else if (b.button_type === 'Flow') type = 'FLOW'
            else if (b.button_type === 'OTP' || b.button_type === 'Copy Offer Code') type = 'COPY_CODE'
            else if (b.button_type === 'Voice Call') type = 'VOICE_CALL'
            const extra = (blobButtons && blobButtons[i] && blobButtons[i].type === type) ? blobButtons[i] : {}
            return {
              type,
              text: b.button_label || '',
              url: b.website_url || '',
              url_type: b.url_type || extra.url_type || 'Static',
              example_url: b.example_url || extra.example_url || '',
              phone: b.phone_number || '',
              voice_call_phone: b.voice_call_phone || '',
              active_for: extra.active_for || '7 days',
              country: extra.country || res.country || '',
              local_id: Math.random().toString(36).slice(2, 11),
              flow_name: extra.flow_name || b.flow || '',
              flow_id: b.flow_id || b.flow || extra.flow_id || '',
              coupon_code: res.offer_code || extra.coupon_code || '',
              track_conversions: extra.track_conversions !== undefined ? extra.track_conversions : true
            }
          })
        } else if (blobButtons) {
          // No child rows (e.g. a very old draft) — fall back to the blob
          form.value.buttons = blobButtons.map(b => ({
            ...b,
            local_id: b.local_id || Math.random().toString(36).slice(2, 11)
          }))
        }
      }
    } catch (e) {
      console.error('Failed to load template', e)
    }
  }
})
</script>

<style scoped>
.editor-page {
  color: var(--ink-900, var(--ink-900));
}

/* ── Header ────────────────────────────────────────── */
.editor-page {
  padding: 0 0 var(--page-gutter);
}
.editor-header {
  margin-bottom: 24px;
}
.back-link {
  display: inline-block;
  margin-bottom: 8px;
  padding: 4px 10px;
  margin-left: -10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-500);
  text-decoration: none;
  border-radius: 6px;
  transition: background 0.12s, color 0.12s;
}
.back-link:hover {
  background: var(--ink-50);
  color: var(--brand-600);
}
.editor-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

/* ── Layout ────────────────────────────────────────── */
.editor-layout {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(320px, 3fr);
  gap: 32px;
  align-items: start;
}
@media (max-width: 1024px) {
  .editor-layout {
    grid-template-columns: 1fr;
    gap: 24px;
  }
  .preview-panel {
    position: static;
  }
}

/* ── Form Panel ────────────────────────────────────── */
.form-panel {
  background: var(--bg-surface);
  border: 1px solid var(--ink-100);
  border-radius: 14px;
  padding: 32px 28px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02), 0 4px 16px rgba(0,0,0,0.04);
}
.form-heading { font-size: 20px; font-weight: 700; margin: 0 0 28px; letter-spacing: -0.01em; }
.form-section { margin-top: 28px; padding-top: 20px; border-top: 1px solid var(--ink-50); }
.form-section-title { font-size: 15px; font-weight: 600; margin: 0 0 14px; color: var(--ink-900); }
.form-group { margin-bottom: 18px; }
.form-label { display: block; font-size: 12px; font-weight: 600; color: var(--ink-600); text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 6px; }
.form-control { width: 100%; height: 40px; padding: 0 14px; border: 1.5px solid var(--ink-100); border-radius: 10px; font-size: 14px; color: var(--ink-900); background: var(--bg-surface); outline: none; transition: border-color 0.15s; box-sizing: border-box; }
.form-control:focus { border-color: var(--brand); }
.form-control:disabled { background: var(--ink-25); color: var(--ink-300); cursor: not-allowed; }
.form-textarea { height: auto; padding: 12px 14px; resize: vertical; line-height: 1.5; font-family: monospace; font-size: 13px; }
.form-hint { font-size: 11px; color: var(--ink-300); margin: 4px 0 0; }

/* Upload placeholder */
.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px;
  border: 2px dashed var(--ink-100);
  border-radius: 12px;
  background: var(--ink-25);
  cursor: pointer;
  transition: border-color 0.15s;
}
.upload-placeholder:hover { border-color: var(--ink-200); }
.upload-text { font-size: 13px; color: var(--ink-300); margin: 0; }

/* Buttons editor */
.button-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.btn-type-select { max-width: 160px; }
.remove-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--status-red-bg);
  border-radius: 8px;
  background: var(--bg-surface);
  color: var(--status-red-fg);
  cursor: pointer;
  flex-shrink: 0;
}
.remove-btn:hover { background: var(--status-red-bg); }
.add-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1.5px dashed var(--ink-100);
  border-radius: 8px;
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-500);
  cursor: pointer;
}
.add-btn:hover { border-color: var(--brand); color: var(--brand); }

/* ── Preview Panel ─────────────────────────────────── */
.preview-panel {
  background: var(--bg-surface);
  border: 1px solid var(--ink-100);
  border-radius: 14px;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02), 0 4px 16px rgba(0,0,0,0.04);
  position: sticky;
  top: 24px;
  align-self: start;
}
.preview-heading { font-size: 15px; font-weight: 600; margin: 0 0 20px; color: var(--ink-900); align-self: flex-start; }
.phone-frame {
  width: 100%;
  max-width: 400px;
  border-radius: 24px;
  border: 2px solid var(--ink-100);
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
}
/* WhatsApp-style preview header */
.wa-preview-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #075e54;
}
.wa-preview-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.wa-preview-header-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.wa-preview-sender {
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wa-preview-status {
  color: rgba(255, 255, 255, 0.7);
  font-size: var(--fs-2xs);
}

.wa-chat-bg {
  background: #efeae2;
  min-height: 260px;
  max-height: 580px;
  overflow-y: auto;
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 6px;
}
.wa-message-card {
  position: relative;
  background: var(--bg-surface);
  border-radius: 0 8px 8px 8px;
  box-shadow: 0 1px 1.5px rgba(11, 20, 26, 0.15);
  max-width: 90%;
  margin-left: 8px;
  display: flex;
  flex-direction: column;
}
.wa-message-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: -8px;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 0 8px 10px 0;
  border-color: transparent #ffffff transparent transparent;
}
.wa-message-content {
  padding: 10px 12px 6px 12px;
}
.wa-msg-header { font-weight: 700; font-size: 14.5px; color: #111b21; margin-bottom: 4px; }
.wa-msg-media {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  border-radius: 6px;
  padding: 24px;
  margin-bottom: 6px;
}
.wa-msg-doc { background: #e9edef; flex-direction: row; gap: 8px; padding: 12px; }
.media-placeholder-text { font-size: 11px; color: #667781; }
.wa-msg-body { font-size: 14.2px; color: #111b21; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
.wa-msg-offer { margin-bottom: 6px; }
.wa-msg-offer-text { font-size: 14px; font-weight: 600; color: #111b21; word-break: break-word; }
.wa-msg-offer-ends { font-size: 12px; color: #667781; }
.wa-msg-footer { font-size: 12px; color: #667781; margin-top: 4px; }
.wa-msg-catalog-title { font-weight: 700; font-size: 14.5px; color: #111b21; line-height: 1.35; }
.wa-msg-catalog-sub { font-size: 13px; color: #667781; margin-bottom: 6px; line-height: 1.35; }
.wa-msg-time { font-size: var(--fs-2xs); color: #667781; text-align: right; margin-top: 4px; }
.wa-card-buttons {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--ink-50);
}
.wa-card-button-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 12px;
  font-size: 14px;
  font-weight: 500;
  color: #008069;
  border-bottom: 1px solid var(--ink-50);
  cursor: pointer;
  transition: background 0.12s;
}
.wa-card-button-row:last-child {
  border-bottom: none;
}
.wa-card-button-row:hover {
  background: var(--ink-25);
}
.wa-btn-icon {
  color: #008069 !important;
  flex-shrink: 0;
}
.wa-btn-text {
  color: #008069;
}

/* ── Product Carousel preview ─────────────────────── */
.wa-carousel-row {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  margin-top: 6px;
  padding-bottom: 2px;
}
.wa-carousel-card {
  flex: 0 0 130px;
  background: var(--bg-surface);
  border: 1px solid var(--ink-100);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.wa-carousel-img {
  height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ink-50);
}
.wa-carousel-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
}
.wa-carousel-title {
  font-size: 12px;
  font-weight: 500;
  color: #111b21;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wa-carousel-price {
  font-size: 11px;
  color: #667781;
}
.wa-carousel-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 8px 6px;
  font-size: 12px;
  font-weight: 500;
  color: #008069;
  border-top: 1px solid var(--ink-50);
}

/* ── Footer Actions ────────────────────────────────── */
.editor-footer {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--ink-50);
  display: flex;
  align-items: center;
  gap: 12px;
}
.grow { flex: 1; }
.btn {
  height: 42px; padding: 0 18px;
  border-radius: 10px;
  font-weight: 500; font-size: 14px;
  cursor: pointer; border: 1.5px solid transparent;
  transition: background .12s, border-color .12s;
  font-family: inherit;
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-default {
  background: var(--surface-surface);
  border-color: var(--ink-100);
  color: var(--ink-900, var(--ink-900));
}
.btn-default:hover:not(:disabled) { border-color: var(--brand-500); }
.btn-primary {
  background: var(--brand);
  color: white;
  border-color: var(--brand-500);
}
.btn-primary:hover:not(:disabled) {
  background: var(--brand);
  border-color: var(--brand-600);
}

/* Validation */
.validation-err {
  margin: 16px 0 0;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.08);
  color: var(--red-700);
  font-size: 13px;
  line-height: 1.5;
}

.editor-fields-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  column-gap: 24px;
}
@media (max-width: 768px) {
  .editor-fields-grid {
    grid-template-columns: 1fr;
  }
}

/* ── Button Card & Builder ─────────────────────────── */
.button-card {
  background: var(--bg-surface);
  border: 1px solid var(--ink-100);
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  transition: all 0.2s ease;
}

.button-card:hover {
  border-color: var(--ink-200);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
}

/* Variable Samples Section */
.variable-samples-section {
  background: var(--ink-25);
  border: 1px solid var(--ink-100);
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
}

/* Button Card styling */
.button-row-card {
  background: var(--bg-surface);
  border: 1.5px solid var(--ink-100);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 18px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.button-row-card:hover {
  border-color: var(--ink-200);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}

.cursor-grab {
  cursor: grab;
}
.cursor-grab:active {
  cursor: grabbing;
}

.button-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--ink-25);
  border-bottom: 1px solid var(--ink-50);
  cursor: pointer;
  user-select: none;
}

.button-card-title-group {
  display: flex;
  align-items: center;
}

.button-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700);
}

.button-card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  color: var(--ink-500);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.icon-action-btn:hover:not(:disabled) {
  background: var(--ink-50);
  color: var(--ink-900);
}

.icon-action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.button-card-body {
  padding: 14px;
  background: var(--bg-surface);
}

.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.col-span-2 {
  grid-column: span 2 / span 2;
}

.add-button-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding: 12px 14px;
  background: var(--ink-25);
  border: 1px dashed var(--ink-100);
  border-radius: 8px;
}

.btn-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.btn-xs {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  border-radius: 6px;
}

/* ── Media Sample ──────────────────────────────────── */
.media-preview-container {
  margin-top: 8px;
}

.media-preview-box {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ink-25);
  border: 1px solid var(--ink-100);
  border-radius: 8px;
  overflow: hidden;
  max-width: 100%;
  padding: 8px;
  margin-bottom: 10px;
}

.preview-media {
  max-width: 100%;
  max-height: 180px;
  border-radius: 6px;
  object-fit: contain;
}

.doc-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--ink-50);
  border-radius: 6px;
}

.doc-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-600);
  text-align: center;
  word-break: break-all;
  max-width: 220px;
}

.media-preview-actions {
  display: flex;
  align-items: center;
}

/* ── Live Preview Styles ───────────────────────────── */
.img-preview {
  max-width: 100%;
  max-height: 140px;
  border-radius: 4px;
  object-fit: cover;
}

.offer-code-badge {
  display: block;
  text-align: center;
  border: 1.5px dashed var(--emerald-500);
  background: var(--status-green-bg);
  color: var(--green-700);
  font-weight: 700;
  font-size: 13px;
  font-family: monospace;
  letter-spacing: 0.05em;
  padding: 6px 12px;
  border-radius: 6px;
  margin-top: 10px;
  text-transform: uppercase;
}
</style>
