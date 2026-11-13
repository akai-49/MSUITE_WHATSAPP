<!-- src/shared/ui/PageHeader.vue
     Standard page header component rendering exactly one <h1> per view.
     Includes subtitle, optional back link, meta slot (for badges/chips),
     and right-aligned actions with mobile wrapping (<=640px).
     Does NOT modify document.title (routing/composables handle browser tab titles). -->
<template>
  <header class="page-header">
    <div class="page-header-main">
      <!-- Optional Back Navigation -->
      <RouterLink
        v-if="backTo"
        :to="backTo"
        class="page-header-back"
      >
        <Icon name="arrow-left" :size="16" class="back-icon" />
        <span>{{ backLabel || 'Back' }}</span>
      </RouterLink>

      <div class="page-header-title-row">
        <h1 class="page-title">{{ title }}</h1>
        <div v-if="$slots.meta" class="page-header-meta">
          <slot name="meta" />
        </div>
      </div>

      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>

    <!-- Actions right-aligned on desktop, wraps below on mobile -->
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
/**
 * PageHeader
 *
 * @component PageHeader
 * @description Single source of truth for routed view titles adhering to the MSuite design standard.
 *
 * Props:
 * @prop {string} title - Required page heading text, rendered once in <h1> (22px/700).
 * @prop {string} [subtitle=''] - Optional descriptive subtitle rendered in 13px --text-secondary.
 * @prop {string|object} [backTo=null] - Optional route location (path or route object) for back link.
 * @prop {string} [backLabel='Back'] - Optional accessible label for the back link.
 *
 * Slots:
 * @slot actions - Interactive action buttons/controls, right-aligned on desktop.
 * @slot meta - Status chips, badges, or counters aligned beside the title.
 *
 * Side effects: None. Does NOT mutate document.title.
 */
import { RouterLink } from 'vue-router'
import Icon from '@/shared/icons/Icon.vue'

defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  backTo: {
    type: [String, Object],
    default: null,
  },
  backLabel: {
    type: String,
    default: 'Back',
  },
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
  width: 100%;
  box-sizing: border-box;
}

.page-header-main {
  flex: 1;
  min-width: 0;
}

.page-header-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs, 12px);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  margin-bottom: 8px;
  transition: color var(--motion-micro, 150ms ease-out);
}
.page-header-back:hover {
  color: var(--brand);
}

.back-icon {
  flex-shrink: 0;
}

.page-header-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  /* Frappe CRM's page headings: text-lg, semibold. */
  font-size: 18px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.015em;
  word-break: break-word;
}

.page-header-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.page-subtitle {
  font-size: var(--fs-sm, 13px);
  line-height: 1.45;
  color: var(--text-secondary);
  margin: 4px 0 0;
  max-width: 720px;
}

.page-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* Mobile wrapping: <= 640px actions drop below */
@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
    margin-bottom: 20px;
  }

  .page-header-actions {
    justify-content: flex-start;
    width: 100%;
  }
}
</style>
