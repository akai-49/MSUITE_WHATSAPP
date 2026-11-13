<!--
  MediaLibraryPickerModal — reusable dialog to select assets from the centralized Media Library or upload a new one.
-->
<template>
  <Teleport to="body">
    <div class="overlay" @click.self="$emit('close')" @keydown.esc="$emit('close')">
      <div class="modal" role="dialog" aria-modal="true">
        <header class="head">
          <div>
            <h3>Select Media Asset</h3>
            <p class="head-sub">Choose a previously uploaded file or add a new one.</p>
          </div>
          <button class="close" @click="$emit('close')" aria-label="Close">
            <Icon name="x" size="18" />
          </button>
        </header>

        <!-- Tabs -->
        <div class="tabs">
          <button
            class="tab"
            :class="{ 'is-active': activeTab === 'existing' }"
            @click="activeTab = 'existing'"
          >
            <Icon name="folder-open" size="14" class="mr-1-5" />
            Choose Existing
          </button>
          <button
            class="tab"
            :class="{ 'is-active': activeTab === 'upload' }"
            @click="activeTab = 'upload'"
          >
            <Icon name="plus" size="14" class="mr-1-5" />
            Upload New
          </button>
        </div>

        <div class="body">
          <!-- Option 1: Choose Existing -->
          <div v-if="activeTab === 'existing'" class="existing-tab-content">
            <div class="search-bar">
              <Icon name="search" size="14" class="search-ic text-[var(--text-tertiary)]" />
              <input
                v-model="searchTerm"
                type="text"
                class="search-input"
                placeholder="Search by file name..."
                @input="onSearchInput"
              />
            </div>

            <Shimmer v-if="loading && items.length === 0" variant="cards" :count="8" />

            <div v-else-if="items.length === 0" class="empty-state">
              <Icon name="folder" size="28" class="text-[var(--text-tertiary)] mb-2" />
              <p>No media files found in library.</p>
            </div>

            <div v-else class="assets-scroll-grid">
              <div
                v-for="asset in items"
                :key="asset.name"
                class="picker-card"
                :class="{ 'is-selected': selectedAsset?.name === asset.name }"
                @click="selectedAsset = asset"
              >
                <div class="card-preview">
                  <img v-if="asset.media_type === 'Image'" :src="asset.file_url" class="img-preview" alt="Preview" />
                  <div v-else class="placeholder-preview">
                    <Icon :name="getFileIcon(asset)" size="28" class="text-[var(--text-tertiary)]" />
                    <span class="ext-badge">{{ getExtension(asset.file_name) }}</span>
                  </div>
                </div>
                <div class="card-meta">
                  <p class="asset-name" :title="asset.file_name">{{ asset.file_name }}</p>
                  <span class="asset-size">{{ formatBytes(asset.file_size) }}</span>
                </div>
              </div>
            </div>

            <div v-if="hasMore" class="load-more-row">
              <button class="btn btn-default btn-xs" :disabled="loading" @click="loadMore">
                Load More
              </button>
            </div>
          </div>

          <!-- Option 2: Upload New -->
          <div v-else class="upload-tab-content">
            <div
              class="dropzone-area"
              :class="{ 'is-dragover': isDragOver }"
              @dragover.prevent="isDragOver = true"
              @dragleave.prevent="isDragOver = false"
              @drop.prevent="onFileDrop"
              @click="triggerFileSelect"
            >
              <Icon name="plus" size="36" class="text-[var(--text-tertiary)] mb-3" />
              <h4>Drag & drop file here or click to select</h4>
              <p class="text-xs text-[var(--text-secondary)] mt-1">Images, videos, documents, or audio files.</p>
              <input ref="fileInput" type="file" class="hidden" :accept="fileInputAccept" @change="onFileSelected" />
            </div>

            <!-- Upload state feedback -->
            <div v-if="uploadState.status" class="upload-status-pane mt-4">
              <div class="status-meta">
                <span class="status-filename">{{ uploadState.name }}</span>
                <span class="status-label" :class="uploadState.status">{{ uploadState.status }}</span>
              </div>
              <div class="progress-bar-container">
                <div class="progress-bar-fill" :style="{ width: uploadState.progress + '%' }" :class="uploadState.status"></div>
              </div>
              <p v-if="uploadState.error" class="status-error-text">{{ uploadState.error }}</p>
              <p v-if="uploadState.isDuplicate" class="text-xs text-[var(--status-green-fg)] font-medium mt-1">
                <Icon name="check" :size="14" class="ei" /> Exact duplicate found in library. Reused asset url.
              </p>
            </div>
          </div>
        </div>

        <footer class="foot">
          <button class="btn btn-default" @click="$emit('close')">Cancel</button>
          <button
            class="btn btn-primary ml-2"
            :disabled="activeTab === 'existing' ? !selectedAsset : (uploadState.status !== 'completed')"
            @click="confirmSelection"
          >
            Select Asset
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import Icon from '@/shared/icons/Icon.vue'
import * as api from '@/services/mediaLibraryApi'
import { getMediaLibrary, createMedia, uploadKBFile } from '@/services/aiCallingApi'

const props = defineProps({
  accept: { type: String, default: 'any' }, // 'image' | 'video' | 'any'
  sourceModule: { type: String, default: 'MediaLibrary' }
})

const emit = defineEmits(['close', 'pick'])

const activeTab = ref('existing')
const searchTerm = ref('')
const items = ref([])
const loading = ref(false)
const hasMore = ref(false)
const start = ref(0)
const limit = 24
const selectedAsset = ref(null)

// Upload state
const fileInput = ref(null)
const isDragOver = ref(false)
const uploadState = ref({ name: '', progress: 0, status: '', error: '', fileUrl: '', isDuplicate: false })

// Map accept types
// "image/*,video/*" (MediaUrlField's default, a carousel card) means either
// kind — it used to fall through to "all", listing PDFs in an image slot.
const isVisual = computed(() => ['visual', 'image/*,video/*', 'video/*,image/*'].includes(props.accept))

const mappedMediaType = computed(() => {
  if (props.accept === 'image' || props.accept === 'image/*') return 'images'
  if (props.accept === 'video' || props.accept === 'video/*') return 'videos'
  if (isVisual.value) return 'visual'
  if (props.accept === 'document' || props.accept === 'documents' || props.accept === 'pdf') return 'documents'
  return 'all'
})

const fileInputAccept = computed(() => {
  if (props.accept === 'image' || props.accept === 'image/*') return 'image/*'
  if (props.accept === 'video' || props.accept === 'video/*') return 'video/*'
  if (isVisual.value) return 'image/*,video/*'
  if (props.accept === 'pdf') return '.pdf'
  if (props.accept === 'document' || props.accept === 'documents') return '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt'
  return undefined
})

// Load existing files
async function fetchAssets(reset = false) {
  if (reset) {
    start.value = 0
    items.value = []
  }
  loading.value = true
  try {
    if (props.accept === 'pdf') {
      const res = await getMediaLibrary()
      const rawList = res?.message || res || []
      const mapped = rawList.map(item => ({
        name: item.name,
        file_name: item.source_filename || item.file?.split('/').pop() || '',
        file_url: item.file,
        title: item.title,
        description: item.description || '',
        media_type: 'Document'
      }))
      let filtered = mapped
      if (searchTerm.value && searchTerm.value.trim()) {
        const q = searchTerm.value.toLowerCase()
        filtered = filtered.filter(item =>
          (item.title || '').toLowerCase().includes(q) ||
          (item.file_name || '').toLowerCase().includes(q)
        )
      }
      items.value = filtered
      hasMore.value = false
      return
    }

    const res = await api.listMedia({
      media_type: mappedMediaType.value,
      search: searchTerm.value,
      limit: limit,
      start: start.value
    })
    if (res && Array.isArray(res)) {
      if (reset) items.value = res
      else items.value = [...items.value, ...res]
      hasMore.value = res.length === limit
    } else {
      hasMore.value = false
    }
  } catch (e) {
    console.error('Failed to load picker assets', e)
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  start.value += limit
  await fetchAssets(false)
}

let searchTimer = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    fetchAssets(true)
  }, 220)
}

function triggerFileSelect() {
  fileInput.value?.click()
}

async function onFileSelected(ev) {
  const file = ev.target.files?.[0]
  if (file) await handleFileUpload(file)
}

async function onFileDrop(ev) {
  isDragOver.value = false
  const file = ev.dataTransfer?.files?.[0]
  if (file) await handleFileUpload(file)
}

// Upload and deduplication engine
async function handleFileUpload(file) {
  uploadState.value = { name: file.name, progress: 0, status: 'uploading', error: '', fileUrl: '', isDuplicate: false }
  
  try {
    if (props.accept === 'pdf') {
      const uploaded = await uploadKBFile(file)
      const fileUrl = uploaded?.message?.file_url
      if (!fileUrl) throw new Error('Upload did not return a file URL')
      
      const createdRes = await createMedia({
        title: file.name.replace(/\.pdf$/i, ''),
        description: '',
        fileUrl
      })
      const created = createdRes?.message || createdRes
      
      uploadState.value.progress = 100
      uploadState.value.status = 'completed'
      uploadState.value.fileUrl = fileUrl
      selectedAsset.value = {
        name: created.name,
        file_name: file.name,
        file_url: fileUrl,
        title: file.name.replace(/\.pdf$/i, ''),
        description: '',
        media_type: 'Document'
      }
      return
    }

    // 1. Check duplicate
    const duplicate = await api.checkExistingAsset(file.name, file.size)
    if (duplicate) {
      uploadState.value.progress = 100
      uploadState.value.status = 'completed'
      uploadState.value.fileUrl = duplicate.file_url
      uploadState.value.isDuplicate = true
      selectedAsset.value = duplicate
      return
    }

    // 2. Perform direct upload
    const formData = new FormData()
    formData.append('file', file)
    formData.append('source_module', props.sourceModule)
    
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/method/msuite_core.api.v1.app.media_library.upload_media')
    xhr.setRequestHeader('X-Frappe-CSRF-Token', window.csrf_token || 'token')
    xhr.withCredentials = true
    
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100)
        uploadState.value.progress = pct
      }
    }
    
    const uploadPromise = new Promise((resolve, reject) => {
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText))
        } else {
          reject(new Error(`Upload failed: status ${xhr.status}`))
        }
      }
      xhr.onerror = () => reject(new Error('Network error.'))
    })
    
    xhr.send(formData)
    const res = await uploadPromise
    const uploadedAsset = res?.message || res
    
    uploadState.value.progress = 100
    uploadState.value.status = 'completed'
    uploadState.value.fileUrl = uploadedAsset.file_url
    selectedAsset.value = uploadedAsset
  } catch (e) {
    uploadState.value.status = 'failed'
    uploadState.value.error = e.message || 'Upload failed.'
  }
}

// Confirm selections
function confirmSelection() {
  if (selectedAsset.value) {
    emit('pick', selectedAsset.value)
  }
}

// Helpers
function getExtension(filename) {
  if (!filename) return ''
  return filename.split('.').pop().toUpperCase()
}

function getFileIcon(asset) {
  const type = asset.media_type
  if (type === 'Video') return 'video'
  if (type === 'Audio') return 'music'
  if (type === 'Document') return 'file-text'
  return 'file'
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

watch(activeTab, (tab) => {
  if (tab === 'existing') {
    fetchAssets(true)
  }
})

onMounted(() => {
  fetchAssets(true)
})
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  z-index: 1200;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.modal {
  width: 100%;
  max-width: 640px;
  max-height: calc(100vh - 48px);
  background: var(--bg-surface);
  border-radius: 14px;
  box-shadow: 0 30px 60px rgba(0, 0, 0, 0.22);
  display: flex; flex-direction: column;
  overflow: hidden;
  animation: pop-in 0.18s cubic-bezier(0.22, 0.61, 0.36, 1);
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0)   scale(1); }
}

.head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px;
  padding: 20px 24px 14px;
  border-bottom: 1px solid var(--ink-100, var(--ink-100));
}
.head h3 {
  margin: 0;
  font-size: 16px; font-weight: 700;
  color: var(--ink-900, var(--ink-900));
}
.head-sub {
  margin: 4px 0 0;
  font-size: 12.5px; color: var(--ink-500, var(--ink-500));
}
.close {
  background: transparent; border: none;
  color: var(--ink-500, var(--ink-500)); cursor: pointer;
}

.tabs {
  display: flex; gap: 4px;
  padding: 8px 24px 0;
  border-bottom: 1px solid var(--ink-100, var(--ink-100));
}
.tab {
  display: inline-flex; align-items: center;
  padding: 10px 14px; margin-bottom: -1px;
  background: transparent; border: none; cursor: pointer;
  color: var(--ink-500, var(--ink-500));
  font-size: 13px; font-weight: 500;
  border-bottom: 2px solid transparent;
  transition: all 0.12s;
}
.tab:hover { color: var(--ink-900, var(--ink-900)); }
.tab.is-active {
  color: var(--brand-600);
  border-bottom-color: var(--brand-500);
  font-weight: 600;
}

.body {
  flex: 1;
  min-width: 0; overflow-y: auto;
  padding: 20px;
}

.search-bar {
  position: relative;
  margin-bottom: 16px;
}
.search-ic {
  position: absolute; left: 12px; top: 50%;
  transform: translateY(-50%);
}
.search-input {
  width: 100%; height: 36px;
  padding: 0 12px 0 34px;
  border: 1.5px solid var(--ink-100, var(--ink-100));
  border-radius: 8px;
  font-size: 13px; outline: none;
  transition: border-color .12s;
}
.search-input:focus { border-color: var(--brand-500); }

.loading-state, .empty-state {
  text-align: center;
  padding: 48px 16px;
  color: var(--ink-500, var(--ink-500));
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.assets-scroll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  max-height: 280px;
  overflow-y: auto;
  padding: 2px;
}

.picker-card {
  background: var(--bg-surface);
  border: 1.5px solid var(--ink-100, var(--ink-100));
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: all 0.12s;
}
.picker-card:hover {
  border-color: var(--brand-500);
  transform: translateY(-1px);
}
.picker-card.is-selected {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(52, 65, 156, 0.15);
}

.card-preview {
  aspect-ratio: 4 / 3;
  background: var(--ink-25, #f8fafc);
  border-bottom: 1.5px solid var(--ink-100, #e2e8f0);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.img-preview {
  width: 100%; height: 100%; object-fit: cover;
}
.placeholder-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.ext-badge {
  font-size: var(--fs-2xs);
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--ink-100, var(--ink-100));
  color: var(--ink-600, var(--ink-600));
  text-transform: uppercase;
}

.card-meta {
  padding: 8px;
}
.asset-name {
  margin: 0; font-size: 11.5px; font-weight: 600;
  color: var(--ink-900, var(--ink-900));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.asset-size {
  font-size: var(--fs-2xs); color: var(--ink-400, var(--ink-400));
}

.load-more-row {
  display: flex; justify-content: center; margin-top: 14px;
}
.btn-xs { padding: 4px 10px; font-size: 11px; }

/* Upload tab */
.dropzone-area {
  border: 2.5px dashed var(--ink-200, var(--ink-200));
  border-radius: 12px;
  background: var(--ink-25, var(--ink-25));
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
}
.dropzone-area:hover, .dropzone-area.is-dragover {
  border-color: var(--brand-500);
  background: rgba(52, 65, 156, 0.03);
}
.dropzone-area h4 {
  font-size: 14px; font-weight: 600; color: var(--ink-800, var(--ink-800)); margin: 0;
}
.dropzone-area p { margin: 0; }

.upload-status-pane {
  background: var(--ink-25, var(--ink-25));
  border: 1px solid var(--ink-100, var(--ink-100));
  border-radius: 8px;
  padding: 12px 14px;
}
.status-meta {
  display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;
}
.status-filename {
  font-weight: 500; color: var(--ink-900, var(--ink-900));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px;
}
.status-label { font-weight: 700; text-transform: capitalize; }
.status-label.uploading { color: var(--brand-500); }
.status-label.completed { color: var(--green-500); }
.status-label.failed { color: var(--status-red-dot); }

.progress-bar-container {
  height: 6px; background: var(--ink-100, var(--ink-100)); border-radius: 3px; overflow: hidden;
}
.progress-bar-fill {
  height: 100%; transition: width 0.15s ease;
}
.progress-bar-fill.uploading { background: var(--brand-500); }
.progress-bar-fill.completed { background: var(--green-500); }
.progress-bar-fill.failed { background: var(--status-red-dot); }

.status-error-text { font-size: 11px; color: var(--status-red-dot); margin-top: 4px; margin-bottom: 0; }

.foot {
  padding: 16px 24px;
  border-top: 1px solid var(--ink-100, var(--ink-100));
  background: var(--ink-25, var(--ink-25));
  display: flex; justify-content: flex-end;
}

.btn {
  display: inline-flex; align-items: center;
  padding: 8px 16px; border-radius: 8px;
  font-size: 13px; font-weight: 500;
  cursor: pointer; border: 1.5px solid transparent;
  font-family: inherit;
}
.btn-primary { background: var(--brand-500); color: white; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary:not(:disabled):hover { background: var(--brand-600); }

.btn-default {
  background: var(--bg-surface); border-color: var(--ink-100, var(--ink-100)); color: var(--ink-700, var(--ink-700));
}
.btn-default:hover { border-color: var(--brand-500); color: var(--brand-600); }

.ml-2 { margin-left: 8px; }
.mr-1-5 { margin-right: 6px; }
.mt-1 { margin-top: 4px; }
.mt-4 { margin-top: 16px; }
.mb-2 { margin-bottom: 8px; }
.mb-3 { margin-bottom: 12px; }
.hidden { display: none; }
.animate-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
