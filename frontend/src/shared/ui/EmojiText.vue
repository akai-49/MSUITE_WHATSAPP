<!-- EmojiText — renders a string, swapping any decorative emoji for the brand line icon.
     Use where data (labels, chips, notifications) carries an emoji that is only ever
     DISPLAYED: the underlying string — and anything sent or compared with it — is unchanged,
     so behaviour doesn't change; only the glyph does. See shared/icons/emojiIcons.js. -->
<template>
  <span class="emoji-text"><template v-for="(p, i) in parts" :key="i"><Icon v-if="p.icon" :name="p.icon" :size="size" class="ei" /><template v-else>{{ p.text }}</template></template></span>
</template>

<script setup>
import { computed } from 'vue'
import Icon from '@/shared/icons/Icon.vue'
import { EMOJI_ICONS, EMOJI_RE } from '@/shared/icons/emojiIcons'

const props = defineProps({
  text: { type: [String, Number], default: '' },
  size: { type: [Number, String], default: 14 },
})

const parts = computed(() => {
  const s = String(props.text ?? '')
  const out = []
  let last = 0
  for (const m of s.matchAll(EMOJI_RE)) {
    if (m.index > last) out.push({ text: s.slice(last, m.index) })
    out.push({ icon: EMOJI_ICONS[m[0]] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ text: s.slice(last) })
  return out
})
</script>
