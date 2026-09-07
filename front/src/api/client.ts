import type {
  ApiErrorBody,
  ApiKeyInfo,
  ChatResponse,
  CreatedApiKey,
  DocumentBatchUpload,
  DocumentListParams,
  DocumentPage,
  DocumentRecord,
  DocumentScope,
  DocumentUpload,
  Identity,
  IndexTask,
  LlmConfig,
  LlmConfigInput,
  McpConfig,
  McpConfigInput,
  MultiAgentAttachment,
  MultiAgentWorkspace,
  ConfigTestResult,
  KnowledgeScope,
  LiveHealth,
  Message,
  ReadyHealth,
  Session,
  WorkspacePermission,
  StreamEvent,
  User,
} from '../types/api'

export const STORAGE_KEYS = {
  apiBase: 'mka.apiBase',
  apiKey: 'mka.apiKey',
  stream: 'mka.stream',
  scope: 'mka.scope',
} as const

const envBase = import.meta.env.VITE_API_BASE || '/api/v1'

export function normalizeApiBase(value: string): string {
  let base = value.trim() || envBase
  base = base.replace(/\/+$/, '')
  if (!/\/api\/v\d+$/i.test(base)) base += '/api/v1'
  return base
}

export function getSavedApiBase(): string {
  return normalizeApiBase(localStorage.getItem(STORAGE_KEYS.apiBase) || envBase)
}

function getApiKey(): string {
  return localStorage.getItem(STORAGE_KEYS.apiKey) || ''
}

function rootUrl(path: string): string {
  const root = getSavedApiBase().replace(/\/api\/v\d+$/i, '')
  return `${root}${path}`
}

export class ApiError extends Error {
  status: number
  code: string
  requestId?: string
  details?: Record<string, unknown>

  constructor(message: string, status = 0, code = 'REQUEST_FAILED', body?: ApiErrorBody) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = body?.error?.request_id
    this.details = body?.error?.details
  }
}

function validationMessage(detail: ApiErrorBody['detail']): string | null {
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  return detail.map((item) => item.msg).filter(Boolean).join('；') || null
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | undefined
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    body = undefined
  }
  const message = body?.error?.message
    || validationMessage(body?.detail)
    || `${response.status} ${response.statusText}`
  return new ApiError(message, response.status, body?.error?.code, body)
}

async function fetchWithErrors(url: string, init: RequestInit = {}): Promise<Response> {
  try {
    const response = await fetch(url, init)
    if (!response.ok) {
      if (response.status === 401) window.dispatchEvent(new Event('mka:unauthorized'))
      throw await parseError(response)
    }
    return response
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) {
      throw error
    }
    throw new ApiError(error instanceof Error ? error.message : '无法连接到服务', 0, 'NETWORK_ERROR')
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const key = getApiKey()
  if (key) headers.set('Authorization', `Bearer ${key}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const method = (init.method || 'GET').toUpperCase()
  const attempts = method === 'GET' ? 3 : 1
  let lastError: unknown

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetchWithErrors(`${getSavedApiBase()}${path}`, { ...init, headers })
      if (response.status === 204) return undefined as T
      return response.json() as Promise<T>
    } catch (error) {
      lastError = error
      const retryable = error instanceof ApiError
        && (error.status === 0 || [500, 502, 503, 504].includes(error.status))
      if (!retryable || attempt === attempts - 1) throw error
      await new Promise((resolve) => window.setTimeout(resolve, 300 * (2 ** attempt)))
    }
  }

  throw lastError
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value)
}

function parseSseFrame(frame: string): StreamEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(':')) continue
    const separator = rawLine.indexOf(':')
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator)
    let value = separator === -1 ? '' : rawLine.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    if (field === 'data') data.push(value)
  }
  if (!data.length) return null
  const rawData = data.join('\n')
  try {
    return { event, data: JSON.parse(rawData) as Record<string, unknown> }
  } catch {
    return { event, data: { text: rawData } }
  }
}

async function chatStream(
  query: string,
  sessionId: string | null,
  scope: KnowledgeScope,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers = new Headers({
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  })
  const key = getApiKey()
  if (key) headers.set('Authorization', `Bearer ${key}`)
  const response = await fetchWithErrors(`${getSavedApiBase()}/chat/stream`, {
    method: 'POST',
    headers,
    body: jsonBody({ query, session_id: sessionId, knowledge_scope: scope }),
    signal,
  })
  if (!response.body) throw new ApiError('浏览器未提供流式响应内容', 0, 'STREAM_UNAVAILABLE')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processFrame = (frame: string) => {
    const parsed = parseSseFrame(frame)
    if (!parsed) return
    onEvent(parsed)
    if (parsed.event === 'error') {
      throw new ApiError(String(parsed.data.message || 'Agent 生成失败'), 500, String(parsed.data.code || 'AGENT_ERROR'))
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let match = buffer.match(/\r?\n\r?\n/)
    while (match?.index !== undefined) {
      processFrame(buffer.slice(0, match.index))
      buffer = buffer.slice(match.index + match[0].length)
      match = buffer.match(/\r?\n\r?\n/)
    }
    if (done) break
  }
  if (buffer.trim()) processFrame(buffer)
}

export const api = {
  me: () => request<Identity>('/me'),
  healthLive: async () => (await fetchWithErrors(rootUrl('/health/live'))).json() as Promise<LiveHealth>,
  healthReady: async () => (await fetchWithErrors(rootUrl('/health/ready'))).json() as Promise<ReadyHealth>,
  docsUrl: () => rootUrl('/docs'),

  listUsers: () => request<User[]>('/users'),
  getUser: (id: string) => request<User>(`/users/${encodeURIComponent(id)}`),
  createUser: (name: string, role: 'user' | 'admin') => request<User>('/users', {
    method: 'POST', body: jsonBody({ name, role }),
  }),
  deleteUser: (id: string) => request<void>(`/users/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  listUserKeys: (id: string) => request<ApiKeyInfo[]>(`/users/${encodeURIComponent(id)}/api-keys`),
  createApiKey: (userId: string) => request<CreatedApiKey>('/api-keys', {
    method: 'POST', body: jsonBody({ user_id: userId }),
  }),
  revokeApiKey: (prefix: string) => request<void>(`/api-keys/${encodeURIComponent(prefix)}`, { method: 'DELETE' }),

  getLlmConfig: () => request<LlmConfig>('/admin/config/llm'),
  saveLlmConfig: (config: LlmConfigInput) => request<LlmConfig>('/admin/config/llm', {
    method: 'PUT', body: jsonBody(config),
  }),
  testLlmConfig: (config: LlmConfigInput) => request<ConfigTestResult>('/admin/config/llm/test', {
    method: 'POST', body: jsonBody(config),
  }),
  listMcpConfigs: () => request<McpConfig[]>('/admin/config/mcp'),
  createMcpConfig: (config: McpConfigInput) => request<McpConfig>('/admin/config/mcp', {
    method: 'POST', body: jsonBody(config),
  }),
  updateMcpConfig: (id: string, config: McpConfigInput) => request<McpConfig>(
    `/admin/config/mcp/${encodeURIComponent(id)}`,
    { method: 'PUT', body: jsonBody(config) },
  ),
  setMcpEnabled: (id: string, enabled: boolean) => request<McpConfig>(
    `/admin/config/mcp/${encodeURIComponent(id)}/enabled`,
    { method: 'PATCH', body: jsonBody({ enabled }) },
  ),
  testMcpConfig: (id: string) => request<ConfigTestResult>(
    `/admin/config/mcp/${encodeURIComponent(id)}/test`,
    { method: 'POST' },
  ),
  deleteMcpConfig: (id: string) => request<void>(
    `/admin/config/mcp/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  ),

  listSessions: (sessionType: Session['session_type']) => request<Session[]>(
    `/sessions?session_type=${encodeURIComponent(sessionType)}`,
  ),
  createSession: (title: string | null, sessionType: Session['session_type']) => request<Session>('/sessions', {
    method: 'POST', body: jsonBody({ title: title || null, session_type: sessionType }),
  }),
  getMessages: (sessionId: string) => request<Message[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`),
  renameSession: (sessionId: string, title: string | null) => request<Session>(
    `/sessions/${encodeURIComponent(sessionId)}`,
    { method: 'PATCH', body: jsonBody({ title: title || null }) },
  ),
  deleteSession: (sessionId: string) => request<void>(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  listMultiAgentWorkspaceRoots: () => request<{ roots: string[] }>('/multi-agent/workspace-roots'),
  getMultiAgentWorkspace: (sessionId: string) => request<MultiAgentWorkspace | null>(
    `/multi-agent/sessions/${encodeURIComponent(sessionId)}/workspace`,
  ),
  configureMultiAgentWorkspace: (
    sessionId: string,
    rootPath: string,
    permission: WorkspacePermission,
  ) => request<MultiAgentWorkspace>(
    `/multi-agent/sessions/${encodeURIComponent(sessionId)}/workspace`,
    { method: 'PUT', body: jsonBody({ root_path: rootPath, permission }) },
  ),
  listMultiAgentAttachments: (sessionId: string) => request<MultiAgentAttachment[]>(
    `/multi-agent/sessions/${encodeURIComponent(sessionId)}/attachments`,
  ),
  uploadMultiAgentAttachment: (
    sessionId: string,
    file: File,
    source: 'file_picker' | 'clipboard' = 'file_picker',
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('source', source)
    return request<MultiAgentAttachment>(
      `/multi-agent/sessions/${encodeURIComponent(sessionId)}/attachments`,
      { method: 'POST', body: form },
    )
  },
  deleteMultiAgentAttachment: (sessionId: string, attachmentId: string) => request<void>(
    `/multi-agent/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}`,
    { method: 'DELETE' },
  ),

  chat: (query: string, sessionId: string | null, scope: KnowledgeScope, signal?: AbortSignal) => request<ChatResponse>('/chat', {
    method: 'POST', body: jsonBody({ query, session_id: sessionId, knowledge_scope: scope }), signal,
  }),
  chatStream,

  listDocuments: async (params: DocumentListParams = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams()
    query.set('page', String(params.page ?? 1))
    query.set('page_size', String(params.pageSize ?? 20))
    if (params.search?.trim()) query.set('search', params.search.trim())
    if (params.scope) query.set('scope', params.scope)
    if (params.status) query.set('status', params.status)
    const payload = await request<DocumentPage | DocumentRecord[]>(
      `/documents?${query.toString()}`,
      { signal },
    )

    // 兼容后端滚动升级期间的旧数组响应，避免页面被 undefined 数据击穿。
    if (Array.isArray(payload)) {
      const search = params.search?.trim().toLocaleLowerCase() || ''
      const processing = new Set(['uploaded', 'queued', 'parsing', 'chunking', 'embedding'])
      const failed = new Set(['failed', 'cleanup_pending'])
      const filtered = payload.filter((document) => {
        if (search && !document.filename.toLocaleLowerCase().includes(search)) return false
        if (params.scope && document.scope !== params.scope) return false
        if (params.status === 'indexed' && document.status !== 'indexed') return false
        if (params.status === 'processing' && !processing.has(document.status)) return false
        if (params.status === 'failed' && !failed.has(document.status)) return false
        return true
      })
      const page = Math.max(1, params.page ?? 1)
      const pageSize = Math.max(1, params.pageSize ?? 20)
      const offset = (page - 1) * pageSize
      return {
        items: filtered.slice(offset, offset + pageSize),
        total: filtered.length,
        page,
        page_size: pageSize,
        total_pages: Math.ceil(filtered.length / pageSize),
      }
    }

    if (!payload || !Array.isArray(payload.items)) {
      throw new ApiError('文档列表响应格式异常，请重启后端服务', 502, 'INVALID_DOCUMENT_PAGE')
    }
    return payload
  },
  getDocument: (id: string) => request<DocumentRecord>(`/documents/${encodeURIComponent(id)}`),
  uploadDocument: (file: File, scope: DocumentScope) => {
    const form = new FormData()
    form.append('file', file)
    form.append('scope', scope)
    return request<DocumentUpload>('/documents', { method: 'POST', body: form })
  },
  uploadDocuments: (files: File[], scope: DocumentScope) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('scope', scope)
    return request<DocumentBatchUpload>('/documents/batch', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getTask: (id: string) => request<IndexTask>(`/tasks/${encodeURIComponent(id)}`),
  getTasks: (ids: string[]) => {
    const query = new URLSearchParams()
    ids.forEach((id) => query.append('task_ids', id))
    return request<IndexTask[]>(`/tasks?${query.toString()}`)
  },
  downloadDocument: async (id: string, filename: string) => {
    const headers = new Headers()
    const key = getApiKey()
    if (key) headers.set('Authorization', `Bearer ${key}`)
    const response = await fetchWithErrors(`${getSavedApiBase()}/documents/${encodeURIComponent(id)}/download`, { headers })
    const blobUrl = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(blobUrl)
  },
}
