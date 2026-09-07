<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-layer" @mousedown.self="emit('close')">
        <section
          ref="panel"
          class="modal-panel"
          :style="{ maxWidth: width }"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="description ? descriptionId : undefined"
          tabindex="-1"
          @keydown="onKeydown"
        >
          <header class="modal-header">
            <div>
              <h2 :id="titleId">{{ title }}</h2>
              <p v-if="description" :id="descriptionId">{{ description }}</p>
            </div>
            <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
              <X :size="19" aria-hidden="true" />
            </button>
          </header>
          <div class="modal-body"><slot /></div>
          <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { PhX as X } from '@phosphor-icons/vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  description?: string
  width?: string
}>(), { description: '', width: '520px' })

const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
const titleId = `modal-title-${Math.random().toString(36).slice(2)}`
const descriptionId = `${titleId}-description`
let previousFocus: HTMLElement | null = null

watch(() => props.open, async (open) => {
  if (open) {
    previousFocus = document.activeElement as HTMLElement | null
    document.body.classList.add('modal-open')
    await nextTick()
    const first = panel.value?.querySelector<HTMLElement>('input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])')
    ;(first || panel.value)?.focus()
  } else {
    document.body.classList.remove('modal-open')
    previousFocus?.focus()
  }
})

onBeforeUnmount(() => {
  if (props.open) document.body.classList.remove('modal-open')
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = Array.from(panel.value.querySelectorAll<HTMLElement>('input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])'))
    .filter((element) => !element.hasAttribute('disabled'))
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>
