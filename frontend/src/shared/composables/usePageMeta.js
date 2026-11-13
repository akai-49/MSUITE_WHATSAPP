import { reactive, unref, isRef, watch } from 'vue'

const state = reactive({
  title: '',
  badge: null,
  breadcrumb: null,
  searchPlaceholder: 'Search campaigns, contacts, templates…',
  searchQuery: '',
})

let activeTitleWatcher = null

export function usePageMeta(meta) {
  if (meta) {
    if (meta.title !== undefined) {
      if (activeTitleWatcher) {
        activeTitleWatcher()
        activeTitleWatcher = null
      }
      if (isRef(meta.title)) {
        state.title = unref(meta.title) || ''
        activeTitleWatcher = watch(meta.title, (newVal) => {
          state.title = unref(newVal) || ''
        })
      } else {
        state.title = unref(meta.title) || ''
      }
    }
    if (meta.badge !== undefined)             state.badge = unref(meta.badge)
    if (meta.breadcrumb !== undefined)        state.breadcrumb = unref(meta.breadcrumb)
    if (meta.searchPlaceholder !== undefined) state.searchPlaceholder = unref(meta.searchPlaceholder)
    if (meta.searchQuery !== undefined)       state.searchQuery = unref(meta.searchQuery)
  }
  return state
}
