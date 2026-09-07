<template>
  <article class="chat-message" :class="`is-${message.role}`">
    <div class="message-avatar" aria-hidden="true">
      <span v-if="message.role === 'assistant'" class="assistant-avatar"><Sparkle :size="17" weight="fill" /></span>
      <span v-else class="user-avatar small">{{ userInitial }}</span>
    </div>

    <div class="message-body">
      <header class="message-meta">
        <strong>{{ message.role === 'assistant' ? 'Chat Agent' : '你' }}</strong>
        <time :datetime="message.created_at">{{ formattedTime }}</time>
      </header>

      <div class="message-content-wrap">
        <div v-if="message.role === 'assistant'" class="message-markdown" :class="{ streaming: message.state === 'streaming' }" v-html="rendered"></div>
        <p v-else class="user-message-content">{{ userContent }}</p>

        <div v-if="message.state === 'sending'" class="thinking-row" aria-label="正在准备回答"><i></i><i></i><i></i></div>
        <div v-if="message.state === 'error'" class="message-error">
          <WarningCircle :size="17" weight="fill" aria-hidden="true" /> {{ message.error_message || '生成失败，请稍后重试。' }}
        </div>

        <details v-if="message.citations?.length" class="citations">
          <summary><Books :size="16" aria-hidden="true" /> {{ message.citations.length }} 个知识来源</summary>
          <ol>
            <li v-for="citation in message.citations" :key="citation.index">
              <strong>{{ citation.document_name }}</strong>
              <span>{{ citation.section || (citation.page ? `第 ${citation.page} 页` : citation.scope === 'shared' ? '共享知识' : '私有知识') }}</span>
              <p>{{ citation.text_snippet }}</p>
            </li>
          </ol>
        </details>

        <div v-if="message.role === 'assistant' && message.state !== 'sending'" class="message-actions">
          <button type="button" @click="copy"><Check v-if="copied" :size="15" /><Copy v-else :size="15" />{{ copied ? '已复制' : '复制' }}</button>
          <span v-if="message.token_usage">{{ message.token_usage.total_tokens }} tokens</span>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhBooks as Books, PhCheck as Check, PhCopy as Copy, PhSparkle as Sparkle, PhWarningCircle as WarningCircle } from '@phosphor-icons/vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useAppStore } from '../../stores/app'
import type { Message } from '../../types/api'
import { visibleUserMessageContent } from '../../utils/chatMessages'

marked.setOptions({ breaks: true, gfm: true })

const props = defineProps<{ message: Message }>()
const store = useAppStore()
const copied = ref(false)
const rendered = computed(() => DOMPurify.sanitize(marked.parse(props.message.content || '') as string))
const userContent = computed(() => visibleUserMessageContent(props.message.content))
const formattedTime = computed(() => new Date(props.message.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }))
const userInitial = computed(() => (store.userDisplayName.trim()[0] || 'U').toUpperCase())

async function copy() {
  await navigator.clipboard.writeText(props.message.content)
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1600)
}
</script>
