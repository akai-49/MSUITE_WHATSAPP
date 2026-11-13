<!--
  Section block — header (title + hint) + body slot.
  Used to group fields inside a composer step so the marketer can
  scan the page by section instead of reading every label.

  Usage:
    <Section title="Demographics" hint="Age range + gender">
      <FormControl ... />
      <FormControl ... />
    </Section>
-->
<template>
  <section class="section">
    <header v-if="title || hint" class="section-head">
      <span class="section-title">{{ title }}</span>
      <span v-if="hint" class="section-hint">{{ hint }}</span>
    </header>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  hint:  { type: String, default: '' },
})
</script>

<style scoped>
/* Section internal rhythm — uniform across every form in the app.
   Header → first field: 16px. Section bottom margin only kicks in
   when the parent doesn't manage spacing itself (e.g. it's not using
   flex `gap`). With a flex-gap parent the margin is shadowed. */
.section { margin-bottom: 32px; }
.section:last-child { margin-bottom: 0; }

/* Direct children of a Section's body get a uniform 18px vertical
   rhythm. Catches FormControl, subfield wrappers, MediaInput, etc.
   Using `> *` so deeply-nested content stays unaffected. */
.section > :not(.section-head) {
  margin-top: 18px;
}
.section > :not(.section-head):first-of-type {
  /* The first body child sits 16px below the header — the same
     space-between as Section ↔ Section (see .ace-form gap 28px ≈
     section-head 16 + content) so the editor looks balanced top to
     bottom. */
  margin-top: 0;
}

.section-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0 0 16px;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900, var(--ink-900));
  letter-spacing: -0.005em;
}
.section-hint {
  color: var(--ink-500, var(--ink-500));
  font-size: 12px;
  font-weight: 400;
}
</style>
