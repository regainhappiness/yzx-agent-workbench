export type Role = 'user' | 'admin'
export type KnowledgeScope = 'private' | 'shared' | 'hybrid'
export type DocumentScope = 'private' | 'shared'
export type SessionType = 'chat' | 'multi_agent'
export type WorkspacePermission = 'read_only' | 'read_write'

export interface Identity {
  user_id: string
  name: string
  role: Role
  api_key_prefix: string
}

export interface User {
  user_id: string
  name: string
  role: Role
  created_at: string
}

export interface ApiKeyInfo {
  prefix: string
  user_id: string
  created_at: string
  revoked_at: string | null
}

export interface CreatedApiKey {
  key: string
  prefix: string
  created_at: string
}

export interface Session {
  session_id: string
  session_type: SessionType
  title: string | null
  message_count: number
  created_at: string
  updated_at: string
}

export interface Citation {
  index: number
  document_name: string
  scope: DocumentScope
  page: number | null
  section: string | null
  text_snippet: string
}

export interface TokenUsage {
  input_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface Message {
  message_id?: string | null
  turn_id?: string | null
  role: 'user' | 'assistant'
  content: string
  created_at: string
  status?: 'pending' | 'complete' | 'failed' | 'cancelled' | string
  metadata?: Record<string, unknown>
  citations?: Citation[]
  token_usage?: TokenUsage | null
  state?: 'sending' | 'streaming' | 'complete' | 'error'
  error_message?: string
}

export interface ChatResponse {
  answer: string
  session_id: string
  citations: Citation[]
  token_usage: TokenUsage | null
}

export interface DocumentRecord {
  document_id: string
  filename: string
  mime_type: string
  file_size: number
  scope: DocumentScope
  status: 'uploaded' | 'queued' | 'parsing' | 'chunking' | 'embedding' | 'indexed' | 'failed' | string
  chunk_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export type DocumentStatusFilter = 'indexed' | 'processing' | 'failed'

export interface DocumentListParams {
  page?: number
  pageSize?: number
  search?: string
  scope?: DocumentScope
  status?: DocumentStatusFilter
}

export interface DocumentPage {
  items: DocumentRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface DocumentUpload {
  document_id: string
  filename: string
  mime_type: string
  file_size: number
  scope: DocumentScope
  status: string
  task_id: string
  created_at: string
}

export interface DocumentBatchUploadItem {
  filename: string
  success: boolean
  document: DocumentUpload | null
  error_code: string | null
  error_message: string | null
}

export interface DocumentBatchUpload {
  total: number
  succeeded: number
  failed: number
  results: DocumentBatchUploadItem[]
}

export interface IndexTask {
  task_id: string
  document_id: string
  status: 'queued' | 'parsing' | 'chunking' | 'done' | 'failed' | string
  progress: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ReadyHealth {
  status: string
  checks: Record<'chat_agent' | 'multi_agent' | 'embedding' | 'milvus' | 'retrieval', string>
}

export interface LiveHealth {
  status: string
}

export interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
    request_id?: string
    details?: Record<string, unknown>
  }
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>
}

export interface StreamEvent {
  event: 'start' | 'token' | 'done' | 'error' | string
  data: Record<string, unknown>
}

export interface MultiAgentWorkspace {
  session_id: string
  root_path: string
  permission: WorkspacePermission
  created_at: string
  updated_at: string
}

export type MultiAgentAttachmentKind = 'text' | 'image' | 'pdf_office_unparsed' | 'binary'

export interface MultiAgentAttachment {
  attachment_id: string
  session_id: string
  turn_id: string | null
  filename: string
  mime_type: string
  file_size: number
  source: 'file_picker' | 'clipboard'
  kind: MultiAgentAttachmentKind
  created_at: string
}

export type LlmProvider = 'openai' | 'deepseek' | 'anthropic'

export interface LlmConfigInput {
  provider: LlmProvider
  model_name: string
  api_key?: string | null
  base_url?: string | null
  temperature: number
  max_tokens?: number | null
}

export interface LlmConfig extends Omit<LlmConfigInput, 'api_key'> {
  configured: boolean
  api_key_configured: boolean
  api_key_hint: string | null
  source: string
  revision: number
  status: string
  last_error: string | null
}

export interface ConfigTestResult {
  success: boolean
  message: string
  tool_count?: number | null
}

export type McpTransport = 'stdio' | 'streamable-http'

export interface McpConfigInput {
  name: string
  transport: McpTransport
  enabled: boolean
  command?: string | null
  args: string[]
  env: Record<string, string>
  url?: string | null
  headers: Record<string, string>
  timeout_seconds: number
  allowed_tools: string[]
  subagents: string[]
}

export interface McpConfig extends McpConfigInput {
  config_id: string
  revision: number
  status: string
  last_error: string | null
  tool_count: number
  created_at: string
  updated_at: string
}
