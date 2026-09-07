<template>
  <Teleport to="body">
    <div class="toast-viewport" aria-live="polite" aria-atomic="true">
      <TransitionGroup name="toast">
        <div v-for="toast in store.toasts" :key="toast.id" class="toast-item" :class="`is-${toast.tone}`">
          <component :is="iconFor(toast.tone)" :size="20" weight="fill" aria-hidden="true" />
          <div class="toast-copy">
            <strong>{{ toast.title }}</strong>
            <span v-if="toast.message">{{ toast.message }}</span>
          </div>
          <button class="icon-button quiet" type="button" aria-label="关闭通知" @click="store.dismissToast(toast.id)">
            <X :size="17" aria-hidden="true" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { PhCheckCircle as CheckCircle, PhInfo as Info, PhWarningCircle as WarningCircle, PhX as X } from '@phosphor-icons/vue'
import { useAppStore } from '../../stores/app'

const store = useAppStore()

function iconFor(tone: 'success' | 'error' | 'info') {
  if (tone === 'success') return CheckCircle
  if (tone === 'error') return WarningCircle
  return Info
}
</script>
