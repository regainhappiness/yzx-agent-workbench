<template>
  <BaseModal :open="open" :title="title" :description="description" width="440px" @close="emit('cancel')">
    <div v-if="detail" class="confirm-detail">{{ detail }}</div>
    <template #footer>
      <button class="button secondary" type="button" @click="emit('cancel')">取消</button>
      <button class="button danger" type="button" :disabled="busy" @click="emit('confirm')">
        {{ busy ? '处理中' : confirmLabel }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import BaseModal from './BaseModal.vue'

withDefaults(defineProps<{
  open: boolean
  title: string
  description?: string
  detail?: string
  confirmLabel?: string
  busy?: boolean
}>(), { description: '', detail: '', confirmLabel: '确认删除', busy: false })

const emit = defineEmits<{ cancel: []; confirm: [] }>()
</script>

