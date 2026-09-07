<template>
  <aside class="session-panel" :class="{ open }">
    <div class="session-panel-head">
      <div><strong>对话记录</strong><span>{{ filteredSessions.length }} 个会话</span></div>
      <button class="icon-button" type="button" aria-label="关闭会话列表" @click="emit('close')"><X :size="19" /></button>
    </div>
    <button class="button secondary new-session-button" type="button" @click="emit('new')">
      <Plus :size="18" weight="bold" aria-hidden="true" /> 新对话
    </button>
    <label class="search-field">
      <MagnifyingGlass :size="17" aria-hidden="true" />
      <input v-model="search" type="search" placeholder="搜索会话" aria-label="搜索会话" />
    </label>

    <div class="session-list">
      <div v-if="loading" class="session-skeleton" aria-label="正在加载会话">
        <span v-for="index in 5" :key="index"></span>
      </div>
      <EmptyState v-else-if="!filteredSessions.length" :icon="Chats" title="还没有对话" description="发出第一条消息后，会话会出现在这里。" compact />
      <div
        v-for="session in filteredSessions"
        v-else
        :key="session.session_id"
        class="session-item"
        :class="{ active: session.session_id === activeId, editing: editingId === session.session_id }"
      >
        <!-- 编辑模式 -->
        <template v-if="editingId === session.session_id">
          <div class="session-main editing-row">
            <input
              v-model="editTitle"
              class="session-edit-input"
              maxlength="200"
              @keydown.enter="saveRename(session.session_id)"
              @keydown.escape="cancelEdit"
              @blur="cancelEdit"
            />
          </div>
          <button class="session-delete" type="button" aria-label="取消重命名" @click.stop="cancelEdit">
            <X :size="16" aria-hidden="true" />
          </button>
        </template>

        <!-- 普通模式 -->
        <template v-else>
          <button class="session-main" type="button" @click="emit('select', session.session_id)">
            <strong
              class="session-title"
              title="点击编辑标题"
              @click.stop="startEdit(session)"
            >{{ session.title || '未命名会话' }}</strong>
            <small>{{ session.message_count }} 条消息 · {{ formatRelative(session.updated_at) }}</small>
          </button>
          <button class="session-delete" type="button" :aria-label="`删除会话 ${session.title || ''}`" @click.stop="emit('delete', session)">
            <Trash :size="16" aria-hidden="true" />
          </button>
        </template>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { PhChats as Chats, PhMagnifyingGlass as MagnifyingGlass, PhPlus as Plus, PhTrash as Trash, PhX as X } from '@phosphor-icons/vue'
import EmptyState from '../ui/EmptyState.vue'
import { useAppStore } from '../../stores/app'
import type { Session } from '../../types/api'

const props = defineProps<{
  sessions: Session[]
  activeId: string | null
  loading: boolean
  open: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  delete: [session: Session]
  new: []
  close: []
}>()

const store = useAppStore()
const search = ref('')
const editingId = ref<string | null>(null)
const editTitle = ref('')
const isSaving = ref(false)

const filteredSessions = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return props.sessions
  return props.sessions.filter((item) => (item.title || '未命名会话').toLowerCase().includes(keyword))
})

function formatRelative(value: string) {
  const date = new Date(value)
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

async function startEdit(session: Session) {
  editingId.value = session.session_id
  editTitle.value = session.title || ''
  await nextTick()
  const input = document.querySelector<HTMLInputElement>('.session-edit-input')
  input?.focus()
  input?.select()
}

async function saveRename(sessionId: string) {
  const title = editTitle.value.trim() || null
  if (isSaving.value) return
  isSaving.value = true
  try {
    await store.renameSession(sessionId, title)
  } catch (error) {
    store.notify('重命名失败', error instanceof Error ? error.message : '', 'error')
  } finally {
    editingId.value = null
    editTitle.value = ''
    isSaving.value = false
  }
}

function cancelEdit() {
  if (isSaving.value) return
  editingId.value = null
  editTitle.value = ''
}
</script>
