<template>
  <div class="chat-workspace">
    <button class="session-overlay" :class="{ visible: sessionsOpen }" type="button" aria-label="关闭会话列表" @click="sessionsOpen = false"></button>
    <SessionPanel
      :sessions="store.sessions"
      :active-id="store.activeSessionId"
      :loading="store.sessionsLoading"
      :open="sessionsOpen"
      @select="selectSession"
      @delete="requestDelete"
      @new="newConversation"
      @close="sessionsOpen = false"
    />

    <section class="chat-main">
      <header class="chat-header">
        <div class="chat-title-group">
          <button class="icon-button session-toggle" type="button" aria-label="打开会话列表" @click="sessionsOpen = true"><SidebarSimple :size="20" /></button>
          <div class="agent-mini-icon"><ChatCircleDots :size="21" weight="duotone" /></div>
          <div><strong>{{ store.activeSession?.title || '新对话' }}</strong><span>Chat Agent · {{ scopeLabel }}</span></div>
        </div>
        <div class="chat-header-actions">
          <StatusBadge status="connected" label="Agent 在线" show-dot />
          <button class="button secondary compact" type="button" @click="newConversation"><Plus :size="17" weight="bold" /> 新对话</button>
        </div>
      </header>

      <div ref="messageList" class="message-list">
        <div v-if="loadingMessages" class="message-loading" aria-label="正在加载消息">
          <div v-for="index in 3" :key="index" class="message-loading-row"><span></span><i></i><i></i></div>
        </div>
        <div v-else-if="!messages.length" class="chat-empty">
          <div class="chat-empty-mark"><Sparkle :size="27" weight="fill" aria-hidden="true" /></div>
          <h1>今天想了解什么？</h1>
          <p>我会根据所选知识范围检索资料，也可以完成普通对话。</p>
          <div class="prompt-suggestions">
            <button v-for="suggestion in suggestions" :key="suggestion" type="button" @click="sendMessage(suggestion)">
              {{ suggestion }} <ArrowUpRight :size="16" aria-hidden="true" />
            </button>
          </div>
        </div>
        <div v-else class="messages-column">
          <ChatMessage v-for="(message, index) in messages" :key="`${message.created_at}-${index}`" :message="message" />
        </div>
      </div>

      <ChatComposer
        :disabled="loadingMessages"
        :sending="sending"
        :stream-enabled="store.streamEnabled"
        :scope="store.knowledgeScope"
        @send="sendMessage"
        @stop="stopGeneration"
        @update:stream-enabled="store.setStreamEnabled"
        @update:scope="store.setKnowledgeScope"
      />
    </section>

    <ConfirmDialog
      :open="Boolean(sessionToDelete)"
      title="删除这段对话？"
      description="会话记录将从列表中移除，此操作无法撤销。"
      :detail="sessionToDelete?.title || '未命名会话'"
      :busy="deleting"
      @cancel="sessionToDelete = null"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowUpRight as ArrowUpRight, PhChatCircleDots as ChatCircleDots, PhPlus as Plus, PhSidebarSimple as SidebarSimple, PhSparkle as Sparkle } from '@phosphor-icons/vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'
import type { Message, Session } from '../types/api'
import { normalizeVisibleMessage } from '../utils/chatMessages'
import ChatComposer from '../components/chat/ChatComposer.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import SessionPanel from '../components/chat/SessionPanel.vue'
import ConfirmDialog from '../components/feedback/ConfirmDialog.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

const props = defineProps<{ sessionId?: string }>()
const store = useAppStore()
const router = useRouter()
const messages = ref<Message[]>([])
const loadingMessages = ref(false)
const sending = ref(false)
const sessionsOpen = ref(false)
const messageList = ref<HTMLElement | null>(null)
const sessionToDelete = ref<Session | null>(null)
const deleting = ref(false)
let streamController: AbortController | null = null
let loadSequence = 0
let scrollFrame: number | null = null

const suggestions = [
  '概括知识库中的核心主题',
  '列出最近文档里的关键结论',
  '帮我从已有资料中查找答案',
]
const scopeLabel = computed(() => ({ hybrid: '全部知识', private: '仅私有', shared: '仅共享' })[store.knowledgeScope])

onMounted(async () => {
  if (!store.sessions.length) await store.loadSessions(false).catch(() => undefined)
  await syncFromRoute(props.sessionId)
})

watch(() => props.sessionId, (sessionId) => { void syncFromRoute(sessionId) })
onBeforeUnmount(() => {
  streamController?.abort()
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
})

async function syncFromRoute(sessionId?: string) {
  if (!sessionId) {
    store.activeSessionId = null
    messages.value = []
    return
  }
  if (store.activeSessionId === sessionId) return
  store.activeSessionId = sessionId
  await loadMessages(sessionId)
}

async function loadMessages(sessionId: string) {
  const sequence = ++loadSequence
  loadingMessages.value = true
  try {
    const result = await api.getMessages(sessionId)
    if (sequence !== loadSequence) return
    messages.value = result.map((item) => ({
      ...normalizeVisibleMessage(item),
      state: 'complete',
    }))
    await scrollBottom(false)
  } catch (error) {
    store.notify('无法加载消息', error instanceof Error ? error.message : '', 'error')
  } finally {
    if (sequence === loadSequence) loadingMessages.value = false
  }
}

async function selectSession(sessionId: string) {
  sessionsOpen.value = false
  await router.push({ name: 'chat', params: { sessionId } })
}

async function newConversation() {
  stopGeneration()
  sessionsOpen.value = false
  store.activeSessionId = null
  messages.value = []
  await router.push({ name: 'chat' })
}

function requestDelete(session: Session) {
  sessionToDelete.value = session
}

async function confirmDelete() {
  if (!sessionToDelete.value) return
  deleting.value = true
  const id = sessionToDelete.value.session_id
  try {
    await store.deleteSession(id)
    sessionToDelete.value = null
    if (props.sessionId === id) await newConversation()
  } catch (error) {
    store.notify('删除失败', error instanceof Error ? error.message : '', 'error')
  } finally {
    deleting.value = false
  }
}

async function sendMessage(query: string) {
  if (sending.value) return
  sending.value = true

  try {
    if (!store.activeSessionId) {
      const title = query.length > 30 ? `${query.slice(0, 30)}…` : query
      const session = await store.createSession(title)
      await router.replace({ name: 'chat', params: { sessionId: session.session_id } })
    }
    const sessionId = store.activeSessionId
    if (!sessionId) throw new Error('无法创建会话')

    const now = new Date().toISOString()
    messages.value.push({ role: 'user', content: query, created_at: now, state: 'complete' })
    messages.value.push({ role: 'assistant', content: '', created_at: new Date().toISOString(), state: 'sending' })
    const assistant = messages.value[messages.value.length - 1]!
    await scrollBottom(true)
    streamController = new AbortController()

    if (store.streamEnabled) {
      await api.chatStream(query, sessionId, store.knowledgeScope, (event) => {
        if (event.event === 'token' && typeof event.data.text === 'string') {
          assistant.state = 'streaming'
          assistant.content += event.data.text
          scheduleScrollBottom()
        }
        if (event.event === 'done') assistant.state = 'complete'
      }, streamController.signal)
      if (!assistant.content.trim()) throw new Error('Agent 未返回有效内容')
      assistant.state = 'complete'
    } else {
      const response = await api.chat(query, sessionId, store.knowledgeScope, streamController.signal)
      assistant.content = response.answer
      assistant.citations = response.citations
      assistant.token_usage = response.token_usage
      assistant.state = 'complete'
    }
    await store.loadSessions(false).catch(() => undefined)
  } catch (error) {
    const assistant = messages.value[messages.value.length - 1]
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (assistant?.role === 'assistant') {
        assistant.state = 'complete'
        if (!assistant.content) assistant.content = '已停止生成。'
      }
    } else {
      if (assistant?.role === 'assistant') {
        assistant.state = 'error'
        assistant.error_message = error instanceof Error ? error.message : '生成失败'
      }
      store.notify('消息发送失败', error instanceof Error ? error.message : '', 'error')
    }
  } finally {
    sending.value = false
    streamController = null
    await scrollBottom(true)
  }
}

function stopGeneration() {
  streamController?.abort()
}

async function scrollBottom(smooth: boolean) {
  await nextTick()
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function scheduleScrollBottom() {
  if (scrollFrame !== null) return
  scrollFrame = window.requestAnimationFrame(async () => {
    scrollFrame = null
    await scrollBottom(false)
  })
}
</script>
