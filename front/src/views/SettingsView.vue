<template>
  <div class="page-scroll settings-page">
    <PageHeader title="配置中心" description="管理运行时能力。保存后新请求立即使用最新配置，无需重启服务。">
      <template #actions>
        <button class="button secondary" type="button" :disabled="loading" @click="loadAll">
          <ArrowClockwise :size="18" :class="{ spinning: loading }" /> 刷新配置
        </button>
      </template>
    </PageHeader>

    <div v-if="!store.isAdmin" class="access-denied">
      <ShieldWarning :size="34" weight="duotone" />
      <h2>需要管理员权限</h2>
      <p>当前 API Key 不能查看或修改运行时配置。</p>
      <RouterLink class="button secondary" :to="{ name: 'agents' }">返回应用</RouterLink>
    </div>

    <div v-else class="settings-workspace">
      <aside class="settings-categories" aria-label="配置分类">
        <button
          v-for="item in categories"
          :key="item.key"
          type="button"
          :class="{ active: activeCategory === item.key }"
          @click="activeCategory = item.key"
        >
          <component :is="item.icon" :size="20" />
          <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
        </button>
      </aside>

      <main class="settings-content">
        <section v-if="activeCategory === 'llm'" class="content-section settings-panel">
          <header class="settings-panel-header">
            <div>
              <h2>模型配置</h2>
              <p>Chat Agent、MainAgent 与 SubAgent 共用当前模型。</p>
            </div>
            <StatusBadge :status="llmConfig?.status || 'unconfigured'" show-dot />
          </header>

          <div v-if="llmLoading" class="settings-form-skeleton"><span v-for="index in 6" :key="index"></span></div>
          <form v-else class="settings-form" @submit.prevent="saveLlm">
            <div class="settings-form-grid">
              <div class="field-group">
                <label for="llm-provider">Provider</label>
                <select id="llm-provider" v-model="llmForm.provider" @change="applyProviderDefault">
                  <option value="deepseek">DeepSeek</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </div>
              <div class="field-group">
                <label for="llm-model">模型名称</label>
                <input id="llm-model" v-model.trim="llmForm.model_name" required placeholder="例如 deepseek-chat" />
              </div>
              <div class="field-group settings-span-2">
                <label for="llm-key">API Key</label>
                <input
                  id="llm-key"
                  v-model.trim="llmForm.api_key"
                  type="password"
                  autocomplete="new-password"
                  :placeholder="llmConfig?.api_key_hint ? `已配置 ${llmConfig.api_key_hint}，留空则不修改` : '输入模型服务 API Key'"
                />
                <small>密钥加密保存在服务端，读取接口不会返回明文。</small>
              </div>
              <div class="field-group settings-span-2">
                <label for="llm-base-url">Base URL</label>
                <input id="llm-base-url" v-model.trim="llmForm.base_url" placeholder="留空使用 Provider 默认地址" />
              </div>
              <div class="field-group">
                <label for="llm-temperature">Temperature</label>
                <input id="llm-temperature" v-model.number="llmForm.temperature" type="number" min="0" max="2" step="0.1" />
              </div>
              <div class="field-group">
                <label for="llm-max-tokens">Max Tokens</label>
                <input id="llm-max-tokens" v-model.number="llmForm.max_tokens" type="number" min="1" placeholder="使用模型默认值" />
              </div>
            </div>

            <div v-if="llmConfig?.last_error" class="inline-alert is-error">
              <WarningCircle :size="18" /><span>{{ llmConfig.last_error }}</span>
            </div>
            <div v-if="llmTestMessage" class="inline-alert" :class="llmTestOk ? 'is-success' : 'is-error'">
              <CheckCircle v-if="llmTestOk" :size="18" />
              <WarningCircle v-else :size="18" />
              <span>{{ llmTestMessage }}</span>
            </div>

            <footer class="settings-form-actions">
              <span v-if="llmConfig?.revision" class="settings-revision">配置版本 {{ llmConfig.revision }}</span>
              <button class="button secondary" type="button" :disabled="llmTesting || llmSaving" @click="testLlm">
                <Pulse :size="17" />{{ llmTesting ? '正在测试' : '测试连接' }}
              </button>
              <button class="button primary" type="submit" :disabled="llmSaving || llmTesting">
                <FloppyDisk :size="17" />{{ llmSaving ? '正在应用' : '保存并应用' }}
              </button>
            </footer>
          </form>
        </section>

        <section v-else class="content-section settings-panel mcp-panel">
          <header class="settings-panel-header">
            <div>
              <h2>MCP 服务</h2>
              <p>管理外部工具服务及其对子智能体的可见范围。</p>
            </div>
            <button class="button primary" type="button" @click="openCreateMcp"><Plus :size="17" />新增 MCP</button>
          </header>

          <div v-if="mcpLoading" class="mcp-list-skeleton"><span v-for="index in 3" :key="index"></span></div>
          <EmptyState
            v-else-if="!mcpConfigs.length"
            :icon="PlugsConnected"
            title="还没有 MCP 服务"
            description="新增一个 HTTP 或本地 stdio MCP 服务后，工具会自动发现并注入 Multi-Agent。"
          >
            <button class="button primary" type="button" @click="openCreateMcp"><Plus :size="17" />新增 MCP</button>
          </EmptyState>
          <div v-else class="mcp-config-list">
            <article v-for="config in mcpConfigs" :key="config.config_id" class="mcp-config-row">
              <div class="mcp-config-icon"><TerminalWindow v-if="config.transport === 'stdio'" :size="21" /><Globe v-else :size="21" /></div>
              <div class="mcp-config-copy">
                <div class="mcp-config-title">
                  <strong>{{ config.name }}</strong>
                  <StatusBadge :status="config.enabled ? config.status : 'disabled'" show-dot />
                </div>
                <p>{{ config.transport === 'stdio' ? formatCommand(config) : config.url }}</p>
                <div class="mcp-config-meta">
                  <span>{{ config.transport }}</span>
                  <span>{{ config.tool_count }} 个工具</span>
                  <span>{{ formatSubagents(config.subagents) }}</span>
                </div>
                <small v-if="config.last_error" class="mcp-config-error">{{ config.last_error }}</small>
              </div>
              <div class="mcp-config-actions">
                <button
                  class="config-switch"
                  type="button"
                  role="switch"
                  :aria-checked="config.enabled"
                  :aria-label="`${config.enabled ? '停用' : '启用'} ${config.name}`"
                  :disabled="mcpBusyId === config.config_id"
                  @click="toggleMcp(config)"
                ><span></span></button>
                <button class="icon-button quiet" type="button" title="测试连接" :disabled="mcpBusyId === config.config_id" @click="testMcp(config)"><Pulse :size="18" /></button>
                <button class="icon-button quiet" type="button" title="编辑配置" @click="openEditMcp(config)"><PencilSimple :size="18" /></button>
                <button class="icon-button quiet danger-icon" type="button" title="删除配置" @click="mcpToDelete = config"><Trash :size="18" /></button>
              </div>
            </article>
          </div>
        </section>
      </main>
    </div>

    <BaseModal
      :open="mcpEditorOpen"
      :title="editingMcpId ? '编辑 MCP 服务' : '新增 MCP 服务'"
      description="保存后会重新发现工具，新请求立即使用最新工具集。"
      width="720px"
      @close="closeMcpEditor"
    >
      <form id="mcp-config-form" class="stack-form" @submit.prevent="saveMcp">
        <div class="settings-form-grid">
          <div class="field-group">
            <label for="mcp-name">服务名称</label>
            <input id="mcp-name" v-model.trim="mcpDraft.name" required maxlength="100" placeholder="例如 knowledge" />
          </div>
          <div class="field-group">
            <label for="mcp-transport">Transport</label>
            <select id="mcp-transport" v-model="mcpDraft.transport">
              <option value="streamable-http">Streamable HTTP</option>
              <option value="stdio">stdio</option>
            </select>
          </div>
          <div v-if="mcpDraft.transport === 'streamable-http'" class="field-group settings-span-2">
            <label for="mcp-url">服务 URL</label>
            <input id="mcp-url" v-model.trim="mcpDraft.url" required placeholder="https://example.com/mcp" />
          </div>
          <template v-else>
            <div class="field-group settings-span-2">
              <label for="mcp-command">启动命令</label>
              <input id="mcp-command" v-model.trim="mcpDraft.command" required placeholder="python 或 npx" />
            </div>
            <div class="field-group settings-span-2">
              <label for="mcp-args">命令参数</label>
              <textarea id="mcp-args" v-model="mcpDraft.argsText" rows="3" placeholder="每行一个参数"></textarea>
            </div>
            <div class="inline-alert is-warning settings-span-2">
              <WarningCircle :size="18" /><span>stdio 会在后端主机启动本地进程，仅应配置可信命令。</span>
            </div>
          </template>
          <div class="field-group settings-span-2">
            <label for="mcp-headers">Headers</label>
            <textarea id="mcp-headers" v-model="mcpDraft.headersText" rows="3" placeholder="每行 KEY=value，留空值不会覆盖已有密钥"></textarea>
          </div>
          <div class="field-group settings-span-2">
            <label for="mcp-env">环境变量</label>
            <textarea id="mcp-env" v-model="mcpDraft.envText" rows="3" placeholder="每行 KEY=value，适用于 stdio"></textarea>
          </div>
          <div class="field-group">
            <label for="mcp-timeout">超时秒数</label>
            <input id="mcp-timeout" v-model.number="mcpDraft.timeout_seconds" type="number" min="1" max="300" />
          </div>
          <div class="field-group">
            <label for="mcp-subagents">可用子智能体</label>
            <input id="mcp-subagents" v-model.trim="mcpDraft.subagentsText" placeholder="如 workspace_file_agent 或 vision_agent" />
            <small>文件和视觉 MCP 必须明确指定对应子智能体；使用 * 不会授予会话文件权限。</small>
          </div>
          <div class="field-group settings-span-2">
            <label for="mcp-tools">允许的工具</label>
            <input id="mcp-tools" v-model.trim="mcpDraft.allowedToolsText" placeholder="* 或多个工具名，以逗号分隔" />
          </div>
        </div>
        <label class="config-checkbox"><input v-model="mcpDraft.enabled" type="checkbox" /> 保存后立即启用</label>
        <div v-if="mcpEditorError" class="inline-alert is-error"><WarningCircle :size="18" /><span>{{ mcpEditorError }}</span></div>
      </form>
      <template #footer>
        <button class="button secondary" type="button" @click="closeMcpEditor">取消</button>
        <button class="button primary" type="submit" form="mcp-config-form" :disabled="mcpSaving">
          {{ mcpSaving ? '正在应用' : '保存并应用' }}
        </button>
      </template>
    </BaseModal>

    <ConfirmDialog
      :open="Boolean(mcpToDelete)"
      title="删除这个 MCP 配置？"
      description="相关工具会从新的 Multi-Agent 请求中移除。"
      :detail="mcpToDelete?.name"
      confirm-label="确认删除"
      :busy="mcpDeleting"
      @cancel="mcpToDelete = null"
      @confirm="deleteMcp"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  PhArrowClockwise as ArrowClockwise,
  PhCheckCircle as CheckCircle,
  PhFloppyDisk as FloppyDisk,
  PhGlobe as Globe,
  PhPencilSimple as PencilSimple,
  PhPlugsConnected as PlugsConnected,
  PhPlus as Plus,
  PhPulse as Pulse,
  PhRobot as Robot,
  PhShieldWarning as ShieldWarning,
  PhTerminalWindow as TerminalWindow,
  PhTrash as Trash,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'
import type { LlmConfig, LlmConfigInput, LlmProvider, McpConfig, McpConfigInput, McpTransport } from '../types/api'
import PageHeader from '../components/layout/PageHeader.vue'
import BaseModal from '../components/feedback/BaseModal.vue'
import ConfirmDialog from '../components/feedback/ConfirmDialog.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

type Category = 'llm' | 'mcp'
interface McpDraft {
  name: string
  transport: McpTransport
  enabled: boolean
  command: string
  argsText: string
  envText: string
  url: string
  headersText: string
  timeout_seconds: number
  allowedToolsText: string
  subagentsText: string
}

const store = useAppStore()
const activeCategory = ref<Category>('llm')
const categories = [
  { key: 'llm' as const, label: '模型配置', description: 'Provider 与生成参数', icon: Robot },
  { key: 'mcp' as const, label: 'MCP 服务', description: '外部工具与连接', icon: PlugsConnected },
]

const providerDefaults: Record<LlmProvider, { model: string; baseUrl: string }> = {
  deepseek: { model: 'deepseek-chat', baseUrl: 'https://api.deepseek.com' },
  openai: { model: 'gpt-4o-mini', baseUrl: '' },
  anthropic: { model: 'claude-haiku-4-5-20251001', baseUrl: '' },
}

const loading = computed(() => llmLoading.value || mcpLoading.value)
const llmLoading = ref(false)
const llmSaving = ref(false)
const llmTesting = ref(false)
const llmTestMessage = ref('')
const llmTestOk = ref(false)
const llmConfig = ref<LlmConfig | null>(null)
const llmForm = reactive<LlmConfigInput>({
  provider: 'deepseek', model_name: 'deepseek-chat', api_key: '',
  base_url: 'https://api.deepseek.com', temperature: 0.3, max_tokens: null,
})

const mcpLoading = ref(false)
const mcpConfigs = ref<McpConfig[]>([])
const mcpBusyId = ref('')
const mcpEditorOpen = ref(false)
const editingMcpId = ref('')
const mcpSaving = ref(false)
const mcpEditorError = ref('')
const mcpToDelete = ref<McpConfig | null>(null)
const mcpDeleting = ref(false)
const mcpDraft = reactive<McpDraft>(emptyMcpDraft())

onMounted(() => { if (store.isAdmin) void loadAll() })

async function loadAll() {
  await Promise.all([loadLlm(), loadMcp()])
}

async function loadLlm() {
  llmLoading.value = true
  try {
    const config = await api.getLlmConfig()
    llmConfig.value = config
    Object.assign(llmForm, {
      provider: config.provider as LlmProvider,
      model_name: config.model_name,
      api_key: '',
      base_url: config.base_url || '',
      temperature: config.temperature,
      max_tokens: config.max_tokens,
    })
  } catch (error) {
    store.notify('模型配置加载失败', error instanceof Error ? error.message : '', 'error')
  } finally { llmLoading.value = false }
}

function applyProviderDefault() {
  const defaults = providerDefaults[llmForm.provider]
  llmForm.model_name = defaults.model
  llmForm.base_url = defaults.baseUrl
}

function llmPayload(): LlmConfigInput {
  return {
    provider: llmForm.provider,
    model_name: llmForm.model_name.trim(),
    api_key: llmForm.api_key?.trim() || null,
    base_url: llmForm.base_url?.trim() || null,
    temperature: Number(llmForm.temperature),
    max_tokens: llmForm.max_tokens ? Number(llmForm.max_tokens) : null,
  }
}

async function testLlm() {
  llmTesting.value = true
  llmTestMessage.value = ''
  try {
    const result = await api.testLlmConfig(llmPayload())
    llmTestOk.value = result.success
    llmTestMessage.value = result.success ? '模型连接正常' : result.message
  } catch (error) {
    llmTestOk.value = false
    llmTestMessage.value = error instanceof Error ? error.message : '模型连接失败'
  } finally { llmTesting.value = false }
}

async function saveLlm() {
  llmSaving.value = true
  llmTestMessage.value = ''
  try {
    llmConfig.value = await api.saveLlmConfig(llmPayload())
    llmForm.api_key = ''
    store.notify('模型配置已应用', `${llmConfig.value.provider} / ${llmConfig.value.model_name}`, 'success')
  } catch (error) {
    store.notify('模型配置保存失败', error instanceof Error ? error.message : '', 'error')
  } finally { llmSaving.value = false }
}

async function loadMcp() {
  mcpLoading.value = true
  try { mcpConfigs.value = await api.listMcpConfigs() }
  catch (error) { store.notify('MCP 配置加载失败', error instanceof Error ? error.message : '', 'error') }
  finally { mcpLoading.value = false }
}

function emptyMcpDraft(): McpDraft {
  return {
    name: '', transport: 'streamable-http', enabled: true, command: '',
    argsText: '', envText: '', url: '', headersText: '', timeout_seconds: 30,
    allowedToolsText: '*', subagentsText: '*',
  }
}

function openCreateMcp() {
  editingMcpId.value = ''
  Object.assign(mcpDraft, emptyMcpDraft())
  mcpEditorError.value = ''
  mcpEditorOpen.value = true
}

function openEditMcp(config: McpConfig) {
  editingMcpId.value = config.config_id
  Object.assign(mcpDraft, {
    name: config.name,
    transport: config.transport,
    enabled: config.enabled,
    command: config.command || '',
    argsText: config.args.join('\n'),
    envText: pairsToText(config.env),
    url: config.url || '',
    headersText: pairsToText(config.headers),
    timeout_seconds: config.timeout_seconds,
    allowedToolsText: config.allowed_tools.join(', '),
    subagentsText: config.subagents.join(', '),
  })
  mcpEditorError.value = ''
  mcpEditorOpen.value = true
}

function closeMcpEditor() {
  if (mcpSaving.value) return
  mcpEditorOpen.value = false
  editingMcpId.value = ''
}

function parsePairs(value: string): Record<string, string> {
  const result: Record<string, string> = {}
  value.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) return
    const separator = trimmed.indexOf('=')
    if (separator <= 0) throw new Error(`格式错误: ${trimmed}`)
    result[trimmed.slice(0, separator).trim()] = trimmed.slice(separator + 1).trim()
  })
  return result
}

function pairsToText(value: Record<string, string>): string {
  return Object.entries(value).map(([key, item]) => `${key}=${item}`).join('\n')
}

function parseList(value: string): string[] {
  const items = value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)
  return items.length ? items : ['*']
}

function mcpPayload(): McpConfigInput {
  return {
    name: mcpDraft.name.trim(),
    transport: mcpDraft.transport,
    enabled: mcpDraft.enabled,
    command: mcpDraft.transport === 'stdio' ? mcpDraft.command.trim() : null,
    args: mcpDraft.transport === 'stdio' ? mcpDraft.argsText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) : [],
    env: parsePairs(mcpDraft.envText),
    url: mcpDraft.transport === 'streamable-http' ? mcpDraft.url.trim() : null,
    headers: parsePairs(mcpDraft.headersText),
    timeout_seconds: Number(mcpDraft.timeout_seconds),
    allowed_tools: parseList(mcpDraft.allowedToolsText),
    subagents: parseList(mcpDraft.subagentsText),
  }
}

async function saveMcp() {
  mcpSaving.value = true
  mcpEditorError.value = ''
  try {
    const payload = mcpPayload()
    if (editingMcpId.value) await api.updateMcpConfig(editingMcpId.value, payload)
    else await api.createMcpConfig(payload)
    mcpEditorOpen.value = false
    store.notify('MCP 配置已应用', payload.name, 'success')
    await loadMcp()
  } catch (error) {
    mcpEditorError.value = error instanceof Error ? error.message : 'MCP 配置保存失败'
  } finally { mcpSaving.value = false }
}

async function toggleMcp(config: McpConfig) {
  mcpBusyId.value = config.config_id
  try {
    const updated = await api.setMcpEnabled(config.config_id, !config.enabled)
    const index = mcpConfigs.value.findIndex((item) => item.config_id === config.config_id)
    if (index !== -1) mcpConfigs.value[index] = updated
    store.notify(updated.enabled ? 'MCP 已启用' : 'MCP 已停用', updated.name, 'success')
  } catch (error) { store.notify('MCP 状态更新失败', error instanceof Error ? error.message : '', 'error') }
  finally { mcpBusyId.value = '' }
}

async function testMcp(config: McpConfig) {
  mcpBusyId.value = config.config_id
  try {
    const result = await api.testMcpConfig(config.config_id)
    store.notify('MCP 连接正常', result.message, 'success')
    await loadMcp()
  } catch (error) { store.notify('MCP 连接失败', error instanceof Error ? error.message : '', 'error') }
  finally { mcpBusyId.value = '' }
}

async function deleteMcp() {
  if (!mcpToDelete.value) return
  mcpDeleting.value = true
  try {
    await api.deleteMcpConfig(mcpToDelete.value.config_id)
    const name = mcpToDelete.value.name
    mcpToDelete.value = null
    await loadMcp()
    store.notify('MCP 配置已删除', name, 'success')
  } catch (error) { store.notify('MCP 删除失败', error instanceof Error ? error.message : '', 'error') }
  finally { mcpDeleting.value = false }
}

function formatCommand(config: McpConfig): string {
  return [config.command, ...config.args].filter(Boolean).join(' ')
}

function formatSubagents(subagents: string[]): string {
  return subagents.includes('*') ? '全部子智能体' : `${subagents.length} 个子智能体`
}
</script>
