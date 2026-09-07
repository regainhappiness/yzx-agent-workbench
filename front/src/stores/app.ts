import { defineStore } from 'pinia'
import { api, getSavedApiBase, normalizeApiBase, STORAGE_KEYS } from '../api/client'
import type {
  DocumentListParams,
  DocumentPage,
  DocumentRecord,
  DocumentScope,
  DocumentStatusFilter,
  Identity,
  IndexTask,
  KnowledgeScope,
  ReadyHealth,
  Session,
} from '../types/api'

interface ToastItem {
  id: number
  title: string
  message?: string
  tone: 'success' | 'error' | 'info'
}

const activePolls = new Map<string, string>()
const pollFailures = new Map<string, number>()
let taskPollingLoop: Promise<void> | null = null
let documentsRequest: {
  key: string
  promise: Promise<DocumentPage>
  controller: AbortController
  timeoutId: number
} | null = null
let documentsRequestVersion = 0
const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const useAppStore = defineStore('app', {
  state: () => ({
    apiBase: getSavedApiBase(),
    apiKey: localStorage.getItem(STORAGE_KEYS.apiKey) || '',
    connected: false,
    connecting: false,
    connectionError: '',
    identity: null as Identity | null,
    health: null as ReadyHealth | null,
    healthCheckedAt: null as string | null,

    sessions: [] as Session[],
    activeSessionId: null as string | null,
    sessionsLoading: false,
    sessionsError: '',

    documents: [] as DocumentRecord[],
    documentsPage: 1,
    documentsPageSize: 20,
    documentsTotal: 0,
    documentsTotalPages: 0,
    documentsSearch: '',
    documentsScopeFilter: '' as '' | DocumentScope,
    documentsStatusFilter: '' as '' | DocumentStatusFilter,
    documentsLoading: false,
    documentsError: '',
    tasks: {} as Record<string, IndexTask>,
    uploadProgress: 0,

    knowledgeScope: (localStorage.getItem(STORAGE_KEYS.scope) || 'hybrid') as KnowledgeScope,
    streamEnabled: localStorage.getItem(STORAGE_KEYS.stream) !== 'false',
    toasts: [] as ToastItem[],
  }),

  getters: {
    isAdmin: (state) => state.identity?.role === 'admin',
    activeSession: (state) => state.sessions.find((item) => item.session_id === state.activeSessionId) || null,
    userDisplayName: (state) => state.identity?.name || '未连接',
    apiKeyMasked: (state) => state.apiKey ? `${state.apiKey.slice(0, 8)}••••${state.apiKey.slice(-4)}` : '',
  },

  actions: {
    notify(title: string, message = '', tone: ToastItem['tone'] = 'info') {
      const id = Date.now() + Math.floor(Math.random() * 1000)
      this.toasts.push({ id, title, message, tone })
      window.setTimeout(() => this.dismissToast(id), 4200)
    },

    dismissToast(id: number) {
      this.toasts = this.toasts.filter((item) => item.id !== id)
    },

    savePreferences() {
      localStorage.setItem(STORAGE_KEYS.apiBase, normalizeApiBase(this.apiBase))
      localStorage.setItem(STORAGE_KEYS.apiKey, this.apiKey.trim())
      localStorage.setItem(STORAGE_KEYS.scope, this.knowledgeScope)
      localStorage.setItem(STORAGE_KEYS.stream, String(this.streamEnabled))
    },

    async connect(base?: string, key?: string) {
      this.connecting = true
      this.connectionError = ''
      this.apiBase = normalizeApiBase(base ?? this.apiBase)
      this.apiKey = (key ?? this.apiKey).trim()
      this.savePreferences()
      try {
        this.identity = await api.me()
        this.connected = true
        const results = await Promise.allSettled([
          this.refreshHealth(),
          this.loadSessions(false),
          this.loadDocuments(false),
        ])
        const unavailable = results.filter((result) => result.status === 'rejected').length
        this.notify('连接成功', unavailable ? '部分服务暂不可用，可在系统状态中查看。' : `你好，${this.identity.name}`, 'success')
      } catch (error) {
        this.connected = false
        this.identity = null
        this.connectionError = error instanceof Error ? error.message : '连接失败'
        throw error
      } finally {
        this.connecting = false
      }
    },

    async bootstrap() {
      if (!this.apiKey) return
      await this.connect(this.apiBase, this.apiKey)
    },

    markDisconnected(message = '') {
      this.connected = false
      this.identity = null
      this.connectionError = message
      if (message) this.notify('连接已断开', message, 'error')
    },

    disconnect() {
      localStorage.removeItem(STORAGE_KEYS.apiKey)
      this.apiKey = ''
      this.identity = null
      this.connected = false
      this.sessions = []
      this.documents = []
      this.documentsPage = 1
      this.documentsTotal = 0
      this.documentsTotalPages = 0
      this.documentsSearch = ''
      this.documentsScopeFilter = ''
      this.documentsStatusFilter = ''
      this.activeSessionId = null
      activePolls.clear()
      pollFailures.clear()
      if (documentsRequest) {
        window.clearTimeout(documentsRequest.timeoutId)
        documentsRequest.controller.abort()
      }
      documentsRequest = null
      documentsRequestVersion += 1
    },

    setKnowledgeScope(scope: KnowledgeScope) {
      this.knowledgeScope = scope
      localStorage.setItem(STORAGE_KEYS.scope, scope)
    },

    setStreamEnabled(enabled: boolean) {
      this.streamEnabled = enabled
      localStorage.setItem(STORAGE_KEYS.stream, String(enabled))
    },

    async refreshHealth() {
      this.health = await api.healthReady()
      this.healthCheckedAt = new Date().toISOString()
      return this.health
    },

    async loadSessions(showError = true) {
      this.sessionsLoading = true
      this.sessionsError = ''
      try {
        this.sessions = await api.listSessions('chat')
        if (this.activeSessionId && !this.sessions.some((item) => item.session_id === this.activeSessionId)) {
          this.activeSessionId = null
        }
      } catch (error) {
        this.sessionsError = error instanceof Error ? error.message : '会话加载失败'
        if (showError) this.notify('无法加载会话', this.sessionsError, 'error')
        throw error
      } finally {
        this.sessionsLoading = false
      }
    },

    async createSession(title?: string | null) {
      const session = await api.createSession(title || null, 'chat')
      this.sessions.unshift(session)
      this.activeSessionId = session.session_id
      return session
    },

    async deleteSession(sessionId: string) {
      await api.deleteSession(sessionId)
      this.sessions = this.sessions.filter((item) => item.session_id !== sessionId)
      if (this.activeSessionId === sessionId) this.activeSessionId = null
      this.notify('会话已删除', '', 'success')
    },

    async renameSession(sessionId: string, title: string | null) {
      const updated = await api.renameSession(sessionId, title)
      const index = this.sessions.findIndex((item) => item.session_id === sessionId)
      if (index !== -1) this.sessions[index] = updated
    },

    async loadDocuments(
      showError = true,
      pagination: Pick<DocumentListParams, 'page' | 'pageSize'> = {},
    ) {
      const currentPage = Number.isFinite(this.documentsPage) ? this.documentsPage : 1
      const currentPageSize = Number.isFinite(this.documentsPageSize) ? this.documentsPageSize : 20
      const page = Math.max(1, pagination.page ?? currentPage)
      const pageSize = Math.max(1, pagination.pageSize ?? currentPageSize)
      const params: DocumentListParams = {
        page,
        pageSize,
        search: typeof this.documentsSearch === 'string' ? this.documentsSearch || undefined : undefined,
        scope: this.documentsScopeFilter || undefined,
        status: this.documentsStatusFilter || undefined,
      }
      const requestKey = JSON.stringify(params)
      let request: Promise<DocumentPage>
      let version: number
      if (documentsRequest?.key === requestKey) {
        request = documentsRequest.promise
        version = documentsRequestVersion
      } else {
        if (documentsRequest) {
          window.clearTimeout(documentsRequest.timeoutId)
          documentsRequest.controller.abort()
        }
        const controller = new AbortController()
        const timeoutId = window.setTimeout(() => controller.abort(), 15_000)
        request = api.listDocuments(params, controller.signal)
        version = ++documentsRequestVersion
        documentsRequest = { key: requestKey, promise: request, controller, timeoutId }
      }

      this.documentsLoading = true
      this.documentsError = ''
      try {
        const result = await request
        if (version !== documentsRequestVersion) return result
        this.documents = result.items
        this.documentsPage = result.page
        this.documentsPageSize = result.page_size
        this.documentsTotal = result.total
        this.documentsTotalPages = result.total_pages
        return result
      } catch (error) {
        if (version === documentsRequestVersion) {
          this.documentsError = error instanceof DOMException && error.name === 'AbortError'
            ? '文档列表请求超时，请确认后端已重启后再重试'
            : error instanceof Error ? error.message : '文档加载失败'
          if (showError) this.notify('无法加载知识库', this.documentsError, 'error')
        }
        throw error
      } finally {
        if (documentsRequest?.promise === request) {
          window.clearTimeout(documentsRequest.timeoutId)
          documentsRequest = null
        }
        if (version === documentsRequestVersion) this.documentsLoading = false
      }
    },

    async uploadDocument(file: File, scope: DocumentScope) {
      const result = await api.uploadDocument(file, scope)
      this.notify('文件已进入处理队列', result.filename, 'success')
      await this.loadDocuments(false, { page: 1 }).catch(() => undefined)
      void this.pollTask(result.task_id, result.document_id)
      return result
    },

    async uploadDocuments(files: File[], scope: DocumentScope) {
      const result = await api.uploadDocuments(files, scope)
      if (result.succeeded) {
        await this.loadDocuments(false, { page: 1 }).catch(() => undefined)
        result.results.forEach((item) => {
          if (item.success && item.document) {
            void this.pollTask(item.document.task_id, item.document.document_id)
          }
        })
      }
      const summary = `${result.succeeded} 个成功，${result.failed} 个失败`
      this.notify(result.failed ? '批量上传已完成' : '文件已进入处理队列', summary, result.failed ? 'error' : 'success')
      return result
    },

    async pollTask(taskId: string, documentId: string) {
      activePolls.set(taskId, documentId)
      if (!taskPollingLoop) {
        taskPollingLoop = this.pollPendingTasks().finally(() => {
          taskPollingLoop = null
          if (activePolls.size) void this.pollTaskLoopRestart()
        })
      }
      return taskPollingLoop
    },

    async pollTaskLoopRestart() {
      await delay(500)
      if (!activePolls.size || taskPollingLoop) return
      const [taskId, documentId] = activePolls.entries().next().value as [string, string]
      void this.pollTask(taskId, documentId)
    },

    async pollPendingTasks() {
      try {
        for (let cycle = 0; cycle < 240 && activePolls.size; cycle += 1) {
          const entries = Array.from(activePolls.entries())
          let receivedUpdate = false
          let reachedTerminalState = false

          try {
            const results = await api.getTasks(entries.map(([taskId]) => taskId))
            const byId = new Map(results.map((task) => [task.task_id, task]))
            entries.forEach(([taskId, documentId]) => {
              const task = byId.get(taskId)
              if (!task) {
                const failures = (pollFailures.get(taskId) || 0) + 1
                pollFailures.set(taskId, failures)
                if (failures >= 5) {
                  activePolls.delete(taskId)
                  pollFailures.delete(taskId)
                  this.notify('任务记录不存在', '请刷新文档列表确认处理结果', 'error')
                }
                return
              }

              receivedUpdate = true
              pollFailures.delete(taskId)
              this.tasks[documentId] = task
              if (task.status === 'done') {
                reachedTerminalState = true
                activePolls.delete(taskId)
                this.notify('索引已完成', '', 'success')
              } else if (task.status === 'failed') {
                reachedTerminalState = true
                activePolls.delete(taskId)
                this.notify('索引失败', task.error_message || '请检查服务配置', 'error')
              }
            })
          } catch (error) {
            entries.forEach(([taskId]) => {
              const failures = (pollFailures.get(taskId) || 0) + 1
              pollFailures.set(taskId, failures)
              if (failures >= 5) {
                activePolls.delete(taskId)
                pollFailures.delete(taskId)
                this.notify(
                  '任务状态暂时无法更新',
                  error instanceof Error ? error.message : '请稍后手动刷新',
                  'error',
                )
              }
            })
          }

          // 一个轮询周期最多刷新一次文档列表，批量任务不再各自重复请求。
          if (receivedUpdate && (cycle % 2 === 0 || reachedTerminalState)) {
            await this.loadDocuments(false).catch(() => undefined)
          }
          if (activePolls.size) await delay(cycle < 10 ? 1500 : 3000)
        }
      } catch (error) {
        this.notify('任务状态更新暂停', error instanceof Error ? error.message : '', 'error')
      }
    },

    async deleteDocument(documentId: string) {
      await api.deleteDocument(documentId)
      this.documents = this.documents.filter((item) => item.document_id !== documentId)
      this.documentsTotal = Math.max(0, this.documentsTotal - 1)
      this.documentsTotalPages = Math.ceil(this.documentsTotal / this.documentsPageSize)
      const page = Math.min(
        this.documentsPage,
        Math.max(1, this.documentsTotalPages),
      )
      delete this.tasks[documentId]
      await this.loadDocuments(false, { page }).catch(() => undefined)
      this.notify('文档已删除', '', 'success')
    },
  },
})
