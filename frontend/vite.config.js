import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import frappeui from 'frappe-ui/vite'

// Builds the WhatsApp panel that msuite_whatsapp mounts inside Frappe CRM's Lead and Deal
// WhatsApp tab. The output is served from /assets/msuite_whatsapp/crm_tab/, and
// `msuite_whatsapp/crm_tab/renderer.py` reads the manifest to add the entry to the /crm page.
export default defineConfig({
  // frappe-ui's plugin is used for its Lucide icons only: this bundle has no page of its own
  // (no boot data, no index.html) and is not served by the Vite dev proxy.
  plugins: [frappeui({ lucideIcons: true, frappeProxy: false, jinjaBootData: false, buildConfig: false }), vue()],
  base: '/assets/msuite_whatsapp/crm_tab/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../msuite_whatsapp/public/crm_tab'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'src/crm/main.js'),
    },
  },
})
