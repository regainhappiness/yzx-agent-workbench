<template>
  <span class="status-badge" :class="toneClass">
    <span v-if="showDot" class="status-dot" aria-hidden="true"></span>
    {{ label || statusLabel }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  status: string
  label?: string
  showDot?: boolean
}>(), { label: '', showDot: false })

const labels: Record<string, string> = {
  ok: '正常',
  connected: '已连接',
  disabled: '已停用',
  applying: '应用中',
  indexed: '可检索',
  done: '已完成',
  queued: '排队中',
  uploaded: '已上传',
  parsing: '解析中',
  chunking: '分块中',
  embedding: '向量化',
  cleanup_pending: '失败待清理',
  failed: '失败',
  error: '异常',
  unconfigured: '未配置',
  unknown: '未知',
  active: '有效',
  revoked: '已撤销',
  private: '私有',
  shared: '共享',
}

const statusLabel = computed(() => labels[props.status] || props.status)
const toneClass = computed(() => {
  if (['ok', 'connected', 'indexed', 'done', 'active'].includes(props.status)) return 'is-good'
  if (['queued', 'uploaded', 'parsing', 'chunking', 'embedding', 'applying'].includes(props.status)) return 'is-progress'
  if (['failed', 'cleanup_pending', 'error', 'revoked'].includes(props.status)) return 'is-bad'
  if (props.status === 'shared') return 'is-accent'
  return 'is-neutral'
})
</script>
