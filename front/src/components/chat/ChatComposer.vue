<template>
  <div class="composer-wrap">
    <div class="composer" :class="{ focused }">
      <textarea
        ref="textarea"
        v-model="text"
        rows="1"
        maxlength="4000"
        :disabled="disabled"
        placeholder="询问文档内容，或开始一个新话题"
        aria-label="消息内容"
        @focus="focused = true"
        @blur="focused = false"
        @input="resize"
        @keydown="onKeydown"
      ></textarea>
      <div class="composer-tools">
        <div class="composer-options">
          <label class="compact-select">
            <Database :size="16" aria-hidden="true" />
            <select :value="scope" aria-label="知识范围" @change="emit('update:scope', ($event.target as HTMLSelectElement).value as KnowledgeScope)">
              <option value="hybrid">全部知识</option>
              <option value="private">仅私有</option>
              <option value="shared">仅共享</option>
            </select>
          </label>
          <label class="stream-toggle" title="开启后逐步显示回答">
            <input :checked="streamEnabled" type="checkbox" @change="emit('update:streamEnabled', ($event.target as HTMLInputElement).checked)" />
            <span aria-hidden="true"></span> 流式回答
          </label>
        </div>
        <div class="composer-submit">
          <span v-if="text.length > 3600" class="char-count">{{ text.length }}/4000</span>
          <button v-if="sending" class="send-button stop" type="button" aria-label="停止生成" @click="emit('stop')"><Stop :size="18" weight="fill" /></button>
          <button v-else class="send-button" type="button" aria-label="发送消息" :disabled="disabled || !text.trim()" @click="send"><ArrowUp :size="19" weight="bold" /></button>
        </div>
      </div>
    </div>
    <p>Enter 发送，Shift + Enter 换行。回答可能存在误差，请核对重要信息。</p>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { PhArrowUp as ArrowUp, PhDatabase as Database, PhStop as Stop } from '@phosphor-icons/vue'
import type { KnowledgeScope } from '../../types/api'

defineProps<{
  disabled: boolean
  sending: boolean
  streamEnabled: boolean
  scope: KnowledgeScope
}>()

const emit = defineEmits<{
  send: [text: string]
  stop: []
  'update:streamEnabled': [value: boolean]
  'update:scope': [value: KnowledgeScope]
}>()

const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const focused = ref(false)

function resize() {
  if (!textarea.value) return
  textarea.value.style.height = 'auto'
  textarea.value.style.height = `${Math.min(textarea.value.scrollHeight, 180)}px`
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    send()
  }
}

function send() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value)
  text.value = ''
  void nextTick(resize)
}
</script>
