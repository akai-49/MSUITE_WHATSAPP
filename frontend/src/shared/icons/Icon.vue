<!-- src/components/Icon.vue
     Usage: <Icon name="rocket" /> or <Icon name="rocket" size="18" /> -->
<template>
  <component
    v-if="isCustomBrand"
    :is="lucideIcon"
  />
  <component
    v-else
    :is="lucideIcon"
    :size="size"
    :stroke-width="strokeWidth"
    class="lucide-icon"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import * as icons from 'lucide-vue-next'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  strokeWidth: { type: Number, default: 2 },
})

const isCustomBrand = computed(() => {
  const customBrands = ['brand', 'tiktok', 'brand-meta', 'meta', 'brand-whatsapp', 'whatsapp', 'google', 'threads', 'microsoft']
  return customBrands.includes(props.name.toLowerCase())
})

const lucideIcon = computed(() => {
  const lowerName = props.name.toLowerCase()

  // Lemnia drew its brand mark here. In Frappe CRM a neutral AI icon stands in for it.
  if (lowerName === 'brand') {
    return icons.Sparkles
  }

  // ── Custom SVG paths for brand icons in unified Lucide stroke style ──
  if (lowerName === 'tiktok') {
    return {
      render() {
        return h('svg', {
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': props.strokeWidth,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          style: { width: props.size + 'px', height: props.size + 'px' },
          class: 'lucide-icon'
        }, [
          h('path', { d: 'M9 12a4 4 0 1 0 4 4V4a5 5 0 0 0 5 5' })
        ])
      }
    }
  }

  // Threads "@" loop and Microsoft four-pane window, drawn in the same stroke style as the other brand icons.
  const strokeSvg = (...paths) => ({
    render() {
      return h('svg', {
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': props.strokeWidth,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        style: { width: props.size + 'px', height: props.size + 'px' },
        class: 'lucide-icon'
      }, paths.map((d) => h('path', { d })))
    }
  })
  if (lowerName === 'threads') {
    return strokeSvg('M17.5 8.5C16.6 6.4 14.6 5 12 5c-3.3 0-5.5 2.5-5.5 7s2.2 7 5.5 7c3 0 4.7-1.5 4.7-3.5 0-2-1.8-3-4.2-3-1.7 0-2.8.8-2.8 2s1 2 2.3 2c2.2 0 3.5-1.8 3.5-5')
  }
  if (lowerName === 'microsoft') {
    return strokeSvg('M3 3h8v8H3z', 'M13 3h8v8h-8z', 'M3 13h8v8H3z', 'M13 13h8v8h-8z')
  }

  if (lowerName === 'brand-meta' || lowerName === 'meta') {
    return {
      render() {
        return h('svg', {
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': props.strokeWidth,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          style: { width: props.size + 'px', height: props.size + 'px' },
          class: 'lucide-icon'
        }, [
          h('path', { d: 'M2 12a5 5 0 0 1 9.5-3l1 2A5 5 0 0 1 22 12a5 5 0 0 1-9.5 3l-1-2A5 5 0 0 1 2 12z' })
        ])
      }
    }
  }

  if (lowerName === 'brand-whatsapp' || lowerName === 'whatsapp') {
    return {
      render() {
        return h('svg', {
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': props.strokeWidth,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          style: { width: props.size + 'px', height: props.size + 'px' },
          class: 'lucide-icon'
        }, [
          h('path', { d: 'M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z' }),
          h('path', { d: 'M17 14c-.3-.1-1.7-.8-2-1-.3-.1-.5-.1-.7.2l-.8 1c-.2.2-.4.3-.7.1a10 10 0 0 1-4-4c-.2-.3-.1-.5.1-.7l1-.8c.3-.2.3-.4.2-.7-.1-.3-.8-2-1-2.2-.2-.3-.5-.3-.7-.2-.2 0-.4.1-.6.3a4 4 0 0 0-1.2 2.5c0 1.2.6 2.5 1.5 3.5a13 13 0 0 0 7 5c.6.2 1.2.3 1.8.1A3 3 0 0 0 18 16c0-.6-.2-.8-.4-.9z' })
        ])
      }
    }
  }

  if (lowerName === 'google') {
    return {
      render() {
        return h('svg', {
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': props.strokeWidth,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          style: { width: props.size + 'px', height: props.size + 'px' },
          class: 'lucide-icon'
        }, [
          h('path', { d: 'M12 2a10 10 0 1 0 10 10V11H12' })
        ])
      }
    }
  }

  // ── Map string names to PascalCase Lucide icon components ──
  const map = {
    // Lemnia (Tabler) names used by the AI Calling pages that lucide spells differently.
    'adjustments': 'SlidersHorizontal',
    'checks': 'CheckCheck',
    'dots-vertical': 'EllipsisVertical',
    'microphone': 'Mic',
    'robot': 'Bot',
    'stop': 'CircleStop',
    'thumb-up': 'ThumbsUp',
    'users-group': 'Users',
    'world': 'Globe',
    'layout-grid': 'LayoutGrid',
    'inbox': 'Inbox',
    'checklist': 'CheckSquare',
    'rocket': 'Rocket',
    'calendar': 'Calendar',
    'ad-2': 'Megaphone',
    'mail': 'Mail',
    'phone-call': 'PhoneCall',
    'building-store': 'Store',
    'gauge': 'Gauge',
    'target-arrow': 'Target',
    'search': 'Search',
    'chart-dots': 'Activity',
    'plus': 'Plus',
    'calendar-plus': 'CalendarPlus',
    'bell': 'Bell',
    'wallet': 'Wallet',
    'users': 'Users',
    'message-2': 'MessageSquare',
    'arrow-up-right': 'ArrowUpRight',
    'arrow-down-right': 'ArrowDownRight',
    'clock': 'Clock',
    'photo': 'Image',
    'template': 'FileText',
    'send': 'Send',
    'chart-bar': 'BarChart3',
    'settings': 'Settings',
    'palette': 'Palette',
    'message-chatbot': 'Bot',
    'alert-triangle': 'AlertTriangle',
    'info-circle': 'Info',
    'lock': 'Lock',
    'layout-dashboard': 'LayoutDashboard',
    'stack-2': 'Layers',
    'forms': 'FileSpreadsheet',
    'list-details': 'ListTodo',
    'currency-rupee': 'IndianRupee',
    'git-branch': 'GitBranch',
    'brand-instagram': 'Instagram',
    'brand-messenger': 'MessageSquare',
    'chevron-down': 'ChevronDown',
    'dots': 'MoreHorizontal',
    'link': 'Link',
    'trash-2': 'Trash2',
    'folder': 'Folder',
    'check': 'Check',
    'x': 'X',
    'globe': 'Globe',
    'eye': 'Eye',
    'phone': 'Phone',
    'facebook': 'Facebook',
    'instagram': 'Instagram',
    'linkedin': 'Linkedin',
    'youtube': 'Youtube',
    'brand-youtube': 'Youtube',
    'twitter': 'Twitter',
  }

  const pascalName = map[lowerName] || props.name
    .split('-')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')

  return icons[pascalName] || icons.HelpCircle
})
</script>

<style scoped>
.lucide-icon {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
}
</style>
