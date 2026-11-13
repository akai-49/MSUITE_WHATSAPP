<!-- src/shared/ui/WizardShell.vue
     Unified broadcast and multi-step wizard shell.
     Standardizes layout (centered 880px), stepper integration, card container,
     single PageHeader h1, and consistent footer actions. -->
<template>
  <div class="wizard-shell" :style="{ maxWidth }">
    <!-- Header: PageHeader by default with single h1, subtitle, back link, and action slot -->
    <slot name="header">
      <PageHeader
        :title="title"
        :subtitle="subtitle"
        :back-to="backTo"
        :back-label="backLabel"
      >
        <template v-if="$slots['header-actions']" #actions>
          <slot name="header-actions" />
        </template>
        <template v-if="$slots['header-meta']" #meta>
          <slot name="header-meta" />
        </template>
      </PageHeader>
    </slot>

    <!-- Stepper Navigation -->
    <slot name="stepper">
      <Stepper
        v-if="steps && steps.length > 0"
        :steps="steps"
        :current="currentStep"
        :completed="completedSteps"
        @select="onStepSelect"
      />
    </slot>

    <!-- Main Content Card -->
    <main class="l-card wizard-card">
      <slot />

      <!-- Footer Actions -->
      <footer
        v-if="$slots.footer || $slots['footer-left'] || $slots['footer-right']"
        class="wizard-footer"
      >
        <slot name="footer">
          <div class="wizard-footer-left">
            <slot name="footer-left" />
          </div>
          <div class="wizard-footer-right">
            <slot name="footer-right" />
          </div>
        </slot>
      </footer>
    </main>
  </div>
</template>

<script setup>
/**
 * WizardShell
 *
 * Props:
 * @prop {string} title - Required page heading for PageHeader.
 * @prop {string} [subtitle=''] - Optional descriptive subtitle.
 * @prop {string|object} [backTo=null] - Destination for the back link.
 * @prop {string} [backLabel='Back'] - Accessible label for the back link.
 * @prop {string[]} [steps=[]] - Array of step names for Stepper.
 * @prop {number} [currentStep=0] - Active step index.
 * @prop {boolean[]} [completedSteps=[]] - Array of completed flags per step.
 * @prop {string} [maxWidth='880px'] - Maximum width of the centered wizard container.
 *
 * Emits:
 * @emit step-select - Fired with the selected step index when stepper pill is clicked.
 * @emit update:currentStep - v-model support for currentStep.
 */
import PageHeader from './PageHeader.vue'
import Stepper from './Stepper.vue'

const props = defineProps({
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
  steps: {
    type: Array,
    default: () => [],
  },
  currentStep: {
    type: Number,
    default: 0,
  },
  completedSteps: {
    type: Array,
    default: () => [],
  },
  maxWidth: {
    type: String,
    default: '880px',
  },
})

const emit = defineEmits(['step-select', 'select', 'update:currentStep'])

function onStepSelect(index) {
  emit('step-select', index)
  emit('select', index)
  emit('update:currentStep', index)
}
</script>

<style scoped>
.wizard-shell {
  width: 100%;
  margin-inline: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 48px;
}

.wizard-card {
  padding: 24px;
  min-height: 420px;
  display: flex;
  flex-direction: column;
}

.wizard-footer {
  margin-top: auto;
  padding-top: 24px;
  border-top: 1px solid var(--border-subtle, var(--border-soft));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.wizard-footer-left,
.wizard-footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .wizard-card {
    padding: 16px;
  }

  .wizard-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .wizard-footer-left,
  .wizard-footer-right {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
