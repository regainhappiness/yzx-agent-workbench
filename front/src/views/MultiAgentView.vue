<template>
  <div class="ma-workspace">
    <aside class="ma-rail" aria-label="多智能体编排概览">
      <RouterLink class="ma-back-link" :to="{ name: 'agents' }">
        <ArrowLeft :size="16" aria-hidden="true" />
        Agent 应用
      </RouterLink>

      <div class="ma-agent-intro">
        <span class="ma-agent-mark"><GraphIcon :size="26" weight="duotone" aria-hidden="true" /></span>
        <div>
          <span class="ma-product-name">Multi-Agent</span>
          <h1>Plan-and-Solve</h1>
        </div>
      </div>
      <p class="ma-agent-description">主智能体负责理解与调度，子智能体按计划执行，最后统一综合结果。</p>

      <section class="ma-history" aria-labelledby="ma-history-title">
        <header>
          <h2 id="ma-history-title">历史会话</h2>
          <button type="button" aria-label="刷新历史任务" title="刷新" @click="loadMultiAgentSessions()">
            <ClockCounterClockwise :size="15" aria-hidden="true" />
          </button>
        </header>
        <p v-if="sessionsLoading" class="ma-history-state">正在加载…</p>
        <p v-else-if="sessionsError" class="ma-history-state is-error">{{ sessionsError }}</p>
        <p v-else-if="!multiAgentSessions.length" class="ma-history-state">暂无历史任务</p>
        <div v-else class="ma-history-list">
          <div
            v-for="session in multiAgentSessions"
            :key="session.session_id"
            class="ma-history-item"
            :class="{ 'is-active': activeSessionId === session.session_id }"
          >
            <button
              class="ma-history-main"
              type="button"
              :disabled="running || Boolean(loadingSessionId) || deleting"
              @click="loadHistoricalSession(session)"
            >
              <span>
                <strong>{{ session.title || '未命名任务' }}</strong>
                <small>{{ formatSessionTime(session.updated_at) }}</small>
              </span>
            </button>
            <button
              class="ma-history-delete"
              type="button"
              :disabled="running || Boolean(loadingSessionId) || deleting"
              :aria-label="`删除历史会话 ${session.title || '未命名会话'}`"
              title="删除历史会话"
              @click="sessionToDelete = session"
            >
              <CircleNotch
                v-if="deleting && sessionToDelete?.session_id === session.session_id"
                class="ma-spinning"
                :size="14"
                aria-hidden="true"
              />
              <Trash v-else :size="14" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <ol class="ma-pipeline" aria-label="执行阶段">
        <li
          v-for="(stage, index) in stageDefinitions"
          :key="stage.key"
          :class="`is-${stageState(index)}`"
          :aria-current="stageState(index) === 'active' ? 'step' : undefined"
        >
          <span class="ma-stage-icon">
            <Check v-if="stageState(index) === 'complete'" :size="16" weight="bold" aria-hidden="true" />
            <WarningCircle v-else-if="stageState(index) === 'error'" :size="17" weight="fill" aria-hidden="true" />
            <Stop v-else-if="stageState(index) === 'stopped'" :size="16" weight="fill" aria-hidden="true" />
            <component v-else :is="stage.icon" :size="17" aria-hidden="true" />
          </span>
          <span class="ma-stage-copy">
            <strong>{{ stage.label }}</strong>
            <small>{{ stage.note }}</small>
          </span>
        </li>
      </ol>

      <div class="ma-architecture">
        <div>
          <span><Brain :size="17" aria-hidden="true" />主智能体</span>
          <small>分析、规划、调度、综合</small>
        </div>
        <div>
          <span><Robot :size="17" aria-hidden="true" />子智能体</span>
          <small>分解、执行、评估、汇报</small>
        </div>
      </div>
    </aside>

    <main class="ma-main">
      <header class="ma-header">
        <div>
          <h2>多轮协作</h2>
          <p>在同一会话中追问、修改任务，或继续中止的执行</p>
        </div>
        <div class="ma-header-actions">
          <button
            v-if="hasRun && !running"
            class="ma-icon-button"
            type="button"
            aria-label="新建任务"
            title="新建任务"
            @click="resetRun"
          >
            <Plus :size="18" aria-hidden="true" />
          </button>
          <span class="ma-runtime-status" :class="`is-${runState}`" role="status" aria-live="polite">
            <CircleNotch v-if="running" class="ma-spinning" :size="15" aria-hidden="true" />
            <WarningCircle v-else-if="runState === 'error'" :size="15" weight="fill" aria-hidden="true" />
            <Stop v-else-if="runState === 'stopped'" :size="14" weight="fill" aria-hidden="true" />
            <CheckCircle v-else :size="15" weight="fill" aria-hidden="true" />
            {{ statusLabel }}
          </span>
        </div>
      </header>

      <section class="ma-resource-bar" aria-label="会话工作区与附件">
        <div class="ma-workspace-picker">
          <FolderOpen :size="18" aria-hidden="true" />
          <label for="ma-workspace-path">工作区</label>
          <input
            id="ma-workspace-path"
            v-model.trim="workspacePath"
            list="ma-workspace-roots"
            type="text"
            :disabled="running || workspaceLocked"
            placeholder="输入后端可访问的文件夹路径"
          />
          <datalist id="ma-workspace-roots">
            <option v-for="root in workspaceRoots" :key="root" :value="root" />
          </datalist>
          <select
            v-model="workspacePermission"
            :disabled="running || workspaceLocked"
            aria-label="工作区权限"
          >
            <option value="read_only">只读</option>
            <option value="read_write">可读写</option>
          </select>
        </div>
        <div class="ma-resource-actions">
          <span v-if="workspaceError" class="ma-resource-error">{{ workspaceError }}</span>
          <span v-else-if="workspaceLocked" class="ma-resource-note">
            当前会话已锁定此工作区 · {{ sessionAttachments.length }} 个文件
          </span>
          <span v-else class="ma-resource-note">附件始终只读，PDF/Office 暂不解析</span>
          <button
            class="ma-attach-button"
            type="button"
            :disabled="running || attachmentUploading || !workspacePath.trim()"
            @click="openAttachmentPicker"
          >
            <CircleNotch v-if="attachmentUploading" class="ma-spinning" :size="15" aria-hidden="true" />
            <Paperclip v-else :size="16" aria-hidden="true" />
            添加文件
          </button>
          <input ref="attachmentInput" class="sr-only" type="file" multiple @change="onFilesSelected" />
        </div>
        <div v-if="pendingAttachmentViews.length" class="ma-attachment-list" aria-label="本轮附件">
          <span v-for="item in pendingAttachmentViews" :key="item.id" class="ma-attachment-chip">
            <ImageIcon v-if="item.kind === 'image'" :size="15" aria-hidden="true" />
            <FileIcon v-else :size="15" aria-hidden="true" />
            <span>
              <strong>{{ item.filename }}</strong>
              <small>{{ attachmentKindLabel(item.kind) }} · {{ formatFileSize(item.fileSize) }}</small>
            </span>
            <button type="button" :disabled="running" aria-label="移除附件" @click="removePendingAttachment(item.id)">
              <X :size="13" aria-hidden="true" />
            </button>
          </span>
        </div>
      </section>

      <div ref="outputPanel" class="ma-output" @scroll="handleOutputScroll">
        <section v-if="!hasRun" class="ma-empty">
          <div class="ma-empty-copy">
            <span class="ma-empty-mark"><Strategy :size="34" weight="duotone" aria-hidden="true" /></span>
            <h2>把复杂问题交给一支智能体队伍</h2>
            <p>描述目标和期望结果，编排器会判断协作范围、生成计划并汇总每个执行结果。</p>
          </div>

          <div class="ma-prompt-starters" aria-label="任务示例">
            <button
              v-for="prompt in promptStarters"
              :key="prompt.label"
              type="button"
              @click="choosePrompt(prompt.value)"
            >
              <span>
                <strong>{{ prompt.label }}</strong>
                <small>{{ prompt.description }}</small>
              </span>
              <CaretRight :size="17" aria-hidden="true" />
            </button>
          </div>
        </section>

        <template v-else>
          <section v-if="historicalMessages.length" class="ma-conversation" aria-label="会话记录">
            <article
              v-for="message in historicalMessages"
              :key="message.message_id || `${message.turn_id}-${message.created_at}-${message.role}`"
              class="ma-conversation-message"
              :class="`is-${message.role}`"
            >
              <span class="ma-conversation-role">{{ message.role === 'user' ? '你' : 'Multi-Agent' }}</span>
              <p v-if="message.role === 'user'">{{ message.content }}</p>
              <div v-else class="message-markdown" v-html="renderConversationMessage(message.content)"></div>
              <div v-if="messageAttachments(message).length" class="ma-message-attachments">
                <span v-for="attachment in messageAttachments(message)" :key="attachment.attachment_id">
                  <Paperclip :size="12" aria-hidden="true" />{{ attachment.filename }}
                </span>
              </div>
              <small v-if="message.status === 'cancelled'">该轮已中止</small>
              <small v-else-if="message.status === 'failed'">该轮执行失败</small>
            </article>
          </section>

          <template v-if="currentTask || events.length">
          <article class="ma-user-brief">
            <span class="ma-brief-icon"><Stack :size="19" aria-hidden="true" /></span>
            <div>
              <span>任务输入</span>
              <p>{{ currentTask }}</p>
            </div>
          </article>

          <div class="ma-results-grid">
            <section class="ma-trace-panel" aria-labelledby="ma-trace-title">
              <header class="ma-panel-header">
                <div>
                  <ListChecks :size="19" aria-hidden="true" />
                  <h3 id="ma-trace-title">执行追踪</h3>
                </div>
                <span>{{ traceEvents.length }} 条更新</span>
              </header>

              <div v-if="!traceEvents.length && running" class="ma-trace-skeleton" aria-label="正在建立执行计划">
                <span></span><span></span><span></span>
              </div>

              <div v-else ref="traceTimeline" class="ma-timeline" @scroll="handleTraceScroll">
                <article
                  v-for="event in traceEvents"
                  :key="event.id"
                  class="ma-trace-event"
                  :class="eventTone(event)"
                >
                  <span class="ma-trace-icon">
                    <component :is="eventIcon(event)" :size="17" aria-hidden="true" />
                  </span>
                  <div class="ma-trace-copy">
                    <header>
                      <strong>{{ eventTitle(event) }}</strong>
                      <time>{{ elapsedLabel(event) }}</time>
                    </header>
                    <p v-if="eventDetail(event)">{{ eventDetail(event) }}</p>

                    <ol v-if="planSteps(event).length" class="ma-plan-list">
                      <li v-for="step in planSteps(event)" :key="step.stepId">
                        <span>{{ step.stepId }}</span>
                        <div>
                          <strong>{{ step.description }}</strong>
                          <small v-if="step.subagentType">{{ formatAgent(step.subagentType) }}</small>
                        </div>
                      </li>
                    </ol>

                    <span v-if="complexityLabel(event)" class="ma-complexity">
                      {{ complexityLabel(event) }}
                    </span>
                  </div>
                </article>
              </div>
            </section>

            <section class="ma-answer-panel" aria-labelledby="ma-answer-title">
              <header class="ma-panel-header">
                <div>
                  <Sparkle :size="19" weight="fill" aria-hidden="true" />
                  <h3 id="ma-answer-title">最终交付</h3>
                </div>
                <button
                  v-if="answerText"
                  class="ma-copy-button"
                  type="button"
                  :aria-label="copied ? '已复制结果' : '复制结果'"
                  @click="copyAnswer"
                >
                  <Check v-if="copied" :size="15" weight="bold" aria-hidden="true" />
                  <Copy v-else :size="15" aria-hidden="true" />
                  {{ copied ? '已复制' : '复制' }}
                </button>
              </header>

              <div v-if="errorMessage" class="ma-answer-state is-error" role="alert">
                <WarningCircle :size="27" weight="duotone" aria-hidden="true" />
                <strong>任务执行未完成</strong>
                <p>{{ errorMessage }}</p>
              </div>

              <div v-else-if="cancelledMessage" class="ma-answer-state is-stopped" role="status">
                <Stop :size="25" weight="duotone" aria-hidden="true" />
                <strong>任务已停止</strong>
                <p>{{ cancelledMessage }}</p>
              </div>

              <div v-else-if="answerText" ref="answerContent" class="message-markdown ma-answer-content" v-html="renderedAnswer"></div>

              <div v-else-if="running" class="ma-answer-skeleton" aria-label="正在等待综合结果">
                <div><span></span><span></span></div>
                <i></i><i></i><i></i><i></i>
              </div>

              <div v-else class="ma-answer-state">
                <Sparkle :size="27" aria-hidden="true" />
                <strong>暂无可展示结果</strong>
                <p>可以调整任务描述后重新运行。</p>
              </div>

              <footer v-if="isComplete && answerText" class="ma-answer-footer">
                <CheckCircle :size="16" weight="fill" aria-hidden="true" />
                本次协作任务已完成
              </footer>
            </section>
          </div>
          </template>
        </template>
      </div>

      <footer class="ma-composer-wrap">
        <form class="ma-composer" :class="{ 'is-focused': composerFocused }" @submit.prevent="submitTask">
          <label class="sr-only" for="multi-agent-task">描述需要多智能体协作的任务</label>
          <textarea
            id="multi-agent-task"
            ref="composerInput"
            v-model="taskInput"
            maxlength="4000"
            rows="2"
            :placeholder="activeSessionId ? '继续追问、修改任务，或输入“继续”恢复执行' : '描述任务目标、可用信息和期望结果'"
            :disabled="running"
            @focus="composerFocused = true"
            @blur="composerFocused = false"
            @keydown="handleComposerKeydown"
            @paste="handleComposerPaste"
          ></textarea>
          <div class="ma-composer-tools">
            <span class="ma-composer-hint">Enter 运行，Shift+Enter 换行</span>
            <span class="ma-character-count">{{ taskInput.length }} / 4000</span>
            <button v-if="running" class="ma-stop-button" type="button" @click="stopRun">
              <Stop :size="16" weight="fill" aria-hidden="true" />
              停止
            </button>
            <button v-else class="ma-submit-button" type="submit" :disabled="!taskInput.trim() || !workspacePath.trim() || attachmentUploading">
              <PaperPlaneTilt :size="17" weight="bold" aria-hidden="true" />
              发送
            </button>
          </div>
        </form>
      </footer>
    </main>

    <ConfirmDialog
      :open="Boolean(sessionToDelete)"
      title="删除这项历史会话？"
      description="所有对话消息、任务轮次和执行状态都将被删除，此操作无法撤销。"
      :detail="sessionToDelete?.title || '未命名任务'"
      :busy="deleting"
      @cancel="sessionToDelete = null"
      @confirm="confirmDeleteSession"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import {
  PhArrowLeft as ArrowLeft,
  PhBrain as Brain,
  PhCaretRight as CaretRight,
  PhCheck as Check,
  PhCheckCircle as CheckCircle,
  PhCircleNotch as CircleNotch,
  PhClockCounterClockwise as ClockCounterClockwise,
  PhCopy as Copy,
  PhFile as FileIcon,
  PhFolderOpen as FolderOpen,
  PhGitBranch as GitBranch,
  PhGraph as GraphIcon,
  PhImage as ImageIcon,
  PhListChecks as ListChecks,
  PhPaperclip as Paperclip,
  PhPaperPlaneTilt as PaperPlaneTilt,
  PhPlus as Plus,
  PhRobot as Robot,
  PhSparkle as Sparkle,
  PhStack as Stack,
  PhStop as Stop,
  PhStrategy as Strategy,
  PhTrash as Trash,
  PhWarningCircle as WarningCircle,
  PhWrench as Wrench,
  PhX as X,
} from '@phosphor-icons/vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { api, getSavedApiBase, STORAGE_KEYS } from '../api/client'
import type {
  Message,
  MultiAgentAttachment,
  MultiAgentAttachmentKind,
  MultiAgentWorkspace,
  Session,
  WorkspacePermission,
} from '../types/api'
import ConfirmDialog from '../components/feedback/ConfirmDialog.vue'

marked.setOptions({ breaks: true, gfm: true })

interface RunEvent {
  id: number
  type: string
  data: Record<string, unknown>
  receivedAt: number
}

interface PlanStepView {
  stepId: string
  description: string
  subagentType: string
}

interface StagedAttachment {
  id: string
  file: File
  source: 'file_picker' | 'clipboard'
}

interface AttachmentView {
  id: string
  filename: string
  fileSize: number
  kind: MultiAgentAttachmentKind
}

type StageState = 'idle' | 'active' | 'complete' | 'error' | 'stopped'

const stageDefinitions: Array<{ key: string; label: string; note: string; icon: Component }> = [
  { key: 'analyze', label: '理解任务', note: '识别范围与复杂度', icon: Brain },
  { key: 'plan', label: '制定计划', note: '拆分步骤与依赖', icon: ListChecks },
  { key: 'execute', label: '协作执行', note: '调度子智能体', icon: GitBranch },
  { key: 'synthesize', label: '综合结果', note: '汇总并形成交付', icon: Sparkle },
]

const promptStarters = [
  {
    label: '梳理方案与风险',
    description: '拆解目标、约束和潜在风险，输出可执行方案',
    value: '请梳理这个任务的目标、关键约束和潜在风险，分工验证后给出一份可执行方案。',
  },
  {
    label: '比较多种选择',
    description: '从多个维度并行分析，汇总差异和建议',
    value: '请对我提供的几种选择做多维度比较，分别分析优缺点、风险和适用条件，最后给出建议。',
  },
  {
    label: '分析问题根因',
    description: '分工核查假设，形成有依据的结论',
    value: '请分析这个问题的可能根因，安排不同子任务核查关键假设，并汇总为结论和后续行动。',
  },
]

const taskInput = ref('')
const currentTask = ref('')
const running = ref(false)
const events = ref<RunEvent[]>([])
const outputPanel = ref<HTMLElement | null>(null)
const traceTimeline = ref<HTMLElement | null>(null)
const answerContent = ref<HTMLElement | null>(null)
const composerInput = ref<HTMLTextAreaElement | null>(null)
const composerFocused = ref(false)
const copied = ref(false)
const runStartedAt = ref(0)
const shouldAutoScroll = ref(true)
const traceShouldAutoScroll = ref(true)
const activeController = ref<AbortController | null>(null)
const activeSessionId = ref('')
const activeTurnId = ref('')
const conversationMessages = ref<Message[]>([])
const multiAgentSessions = ref<Session[]>([])
const sessionsLoading = ref(false)
const sessionsError = ref('')
const loadingSessionId = ref('')
const sessionToDelete = ref<Session | null>(null)
const deleting = ref(false)
const workspaceRoots = ref<string[]>([])
const workspacePath = ref('')
const workspacePermission = ref<WorkspacePermission>('read_only')
const workspaceRecord = ref<MultiAgentWorkspace | null>(null)
const workspaceError = ref('')
const attachmentInput = ref<HTMLInputElement | null>(null)
const stagedAttachments = ref<StagedAttachment[]>([])
const pendingAttachments = ref<MultiAgentAttachment[]>([])
const sessionAttachments = ref<MultiAgentAttachment[]>([])
const attachmentUploading = ref(false)
let eventSequence = 0
let copyTimer: number | undefined

const hasRun = computed(() => conversationMessages.value.length > 0 || Boolean(currentTask.value) || events.value.length > 0)
const workspaceLocked = computed(() => Boolean(activeSessionId.value && workspaceRecord.value))
const pendingAttachmentViews = computed<AttachmentView[]>(() => [
  ...stagedAttachments.value.map((item) => ({
    id: item.id,
    filename: item.file.name,
    fileSize: item.file.size,
    kind: inferAttachmentKind(item.file.name, item.file.type),
  })),
  ...pendingAttachments.value.map((item) => ({
    id: item.attachment_id,
    filename: item.filename,
    fileSize: item.file_size,
    kind: item.kind,
  })),
])
const historicalMessages = computed(() => (
  activeTurnId.value
    ? conversationMessages.value.filter((message) => message.turn_id !== activeTurnId.value)
    : conversationMessages.value
))
const errorEvent = computed(() => [...events.value].reverse().find((event) => event.type === 'error'))
const errorMessage = computed(() => dataString(errorEvent.value, 'message') || '')
const cancelledEvent = computed(() => [...events.value].reverse().find((event) => event.type === 'cancelled'))
const cancelledMessage = computed(() => dataString(cancelledEvent.value, 'message') || '')
const isComplete = computed(() => events.value.some((event) => event.type === 'done') && !running.value)
const runState = computed(() => {
  if (running.value) return 'running'
  if (errorMessage.value) return 'error'
  if (cancelledMessage.value) return 'stopped'
  if (isComplete.value) return 'complete'
  return 'ready'
})
const statusLabel = computed(() => ({
  running: '执行中',
  error: '需要处理',
  stopped: '已停止',
  complete: '已完成',
  ready: '就绪',
})[runState.value])

const traceEvents = computed(() => events.value.filter(
  (event) => !['start', 'turn_started', 'token', 'done'].includes(event.type),
))

const answerText = computed(() => {
  const synthesis = [...events.value].reverse().find((event) => event.type === 'synthesis_done')
  const synthesizedAnswer = dataString(synthesis, 'answer')
  if (synthesizedAnswer) return synthesizedAnswer

  let markerIndex = -1
  for (let index = events.value.length - 1; index >= 0; index -= 1) {
    const event = events.value[index]
    if (!event) continue
    const node = dataString(event, 'node')
    if (event.type === 'synthesizing' || (event.type === 'status' && ['synthesize', 'respond'].includes(node))) {
      markerIndex = index
      break
    }
  }

  const startIndex = markerIndex > 0 && events.value[markerIndex - 1]?.type === 'token'
    ? markerIndex - 1
    : Math.max(0, markerIndex + 1)
  const tokenEvents = events.value.slice(startIndex).filter((event) => (
    event.type === 'token' && (!dataString(event, 'agent') || dataString(event, 'agent') === 'main')
  ))
  return tokenEvents.map((event) => dataString(event, 'text')).join('')
})

const renderedAnswer = computed(() => DOMPurify.sanitize(marked.parse(answerText.value) as string))

watch(answerText, () => {
  if (!running.value) return
  nextTick(() => {
    const element = answerContent.value
    if (element) element.scrollTop = element.scrollHeight
  })
})

const activeStageIndex = computed(() => {
  if (!hasRun.value) return -1
  let current = 0
  for (const event of events.value) {
    const node = dataString(event, 'node')
    if (event.type === 'done') current = stageDefinitions.length
    else if (event.type === 'synthesizing' || event.type === 'synthesis_done' || ['synthesize', 'respond'].includes(node)) current = 3
    else if (['dispatching', 'subagent_start', 'subagent_plan', 'subagent_step', 'subagent_progress', 'subagent_done', 'tool_call', 'tool_result'].includes(event.type) || node === 'execute') current = 2
    else if (event.type === 'plan_created' || ['plan', 'replan'].includes(node)) current = 1
    else if (event.type === 'analyzing' || event.type === 'analysis_done' || node === 'analyze') current = 0
  }
  return current
})

function stageState(index: number): StageState {
  if (!hasRun.value) return 'idle'
  if (index < activeStageIndex.value || activeStageIndex.value >= stageDefinitions.length) return 'complete'
  if (index === activeStageIndex.value && errorMessage.value) return 'error'
  if (index === activeStageIndex.value && cancelledMessage.value) return 'stopped'
  if (index === activeStageIndex.value) return 'active'
  return 'idle'
}

function dataString(event: RunEvent | undefined, key: string): string {
  const value = event?.data[key]
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function dataNumber(event: RunEvent, key: string): number | null {
  const value = event.data[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function eventTitle(event: RunEvent): string {
  const titles: Record<string, string> = {
    status: dataString(event, 'node') === 'replan' ? '调整执行计划' : '主智能体更新',
    analyzing: '分析任务',
    analysis_done: '任务分析完成',
    plan_created: '执行计划已生成',
    dispatching: '调度子智能体',
    subagent_start: `${formatAgent(dataString(event, 'subagent_type'))} 开始执行`,
    subagent_plan: `${formatAgent(dataString(event, 'subagent_type'))} 制定子计划`,
    subagent_step: `${formatAgent(dataString(event, 'subagent_type'))} 更新步骤`,
    subagent_progress: `${formatAgent(dataString(event, 'subagent_type'))} 更新进度`,
    subagent_done: `${formatAgent(dataString(event, 'subagent_type'))} ${event.data.success === false ? '执行失败' : '执行完成'}`,
    synthesizing: '综合执行结果',
    synthesis_done: '最终结果已生成',
    tool_call: `调用工具 ${dataString(event, 'tool_name')}`,
    tool_result: `工具 ${dataString(event, 'tool_name')} 返回结果`,
    error: '执行发生错误',
    cancelled: '任务已停止',
  }
  return titles[event.type] || '执行状态更新'
}

function eventDetail(event: RunEvent): string {
  if (event.type === 'analysis_done') {
    return dataString(event, 'task_summary') || '已完成任务范围与协作需求分析。'
  }
  if (event.type === 'plan_created') {
    const count = planSteps(event).length
    return count ? `已生成 ${count} 个可执行步骤。` : '执行计划已准备。'
  }
  if (event.type === 'dispatching') {
    const agent = formatAgent(dataString(event, 'subagent_type'))
    const step = dataString(event, 'step_id')
    return step ? `${agent} 正在处理计划步骤 ${step}。` : `${agent} 正在接收任务。`
  }
  if (event.type === 'subagent_done') return dataString(event, 'result_summary')
  if (event.type === 'subagent_step') {
    return dataString(event, 'description') || `当前状态：${dataString(event, 'status') || '执行中'}`
  }
  if (event.type === 'subagent_progress') {
    const progress = dataNumber(event, 'progress')
    return progress === null ? '子智能体正在执行。' : `当前进度 ${Math.round(progress)}%。`
  }
  if (event.type === 'tool_call') return '子智能体正在使用可用工具处理当前步骤。'
  if (event.type === 'tool_result') return dataString(event, 'result_summary') || '工具调用已完成。'
  if (event.type === 'synthesis_done') return '所有可用结果已完成汇总。'
  if (event.type === 'cancelled') return dataString(event, 'message')
  return dataString(event, 'message') || dataString(event, 'reason')
}

function eventIcon(event: RunEvent): Component {
  const icons: Record<string, Component> = {
    analyzing: Brain,
    analysis_done: CheckCircle,
    plan_created: ListChecks,
    dispatching: GitBranch,
    subagent_start: Robot,
    subagent_plan: ListChecks,
    subagent_step: Robot,
    subagent_progress: CircleNotch,
    subagent_done: event.data.success === false ? WarningCircle : CheckCircle,
    synthesizing: Sparkle,
    synthesis_done: CheckCircle,
    tool_call: Wrench,
    tool_result: Wrench,
    error: WarningCircle,
    cancelled: Stop,
  }
  return icons[event.type] || (dataString(event, 'node') === 'replan' ? GitBranch : CircleNotch)
}

function eventTone(event: RunEvent): string {
  if (event.type === 'error' || event.type === 'cancelled' || event.data.success === false) return 'is-error'
  if (['analysis_done', 'subagent_done', 'synthesis_done'].includes(event.type)) return 'is-success'
  if (['plan_created', 'dispatching', 'subagent_start', 'subagent_plan', 'synthesizing'].includes(event.type)) return 'is-accent'
  return ''
}

function complexityLabel(event: RunEvent): string {
  if (event.type !== 'analysis_done') return ''
  const complexity = dataString(event, 'complexity').toLowerCase()
  return ({ simple: '简单任务', medium: '中等复杂度', complex: '复杂任务' } as Record<string, string>)[complexity] || ''
}

function planSteps(event: RunEvent): PlanStepView[] {
  const rawPlan = event.data.plan
  if (!Array.isArray(rawPlan)) return []
  return rawPlan.flatMap((rawStep, index) => {
    if (!rawStep || typeof rawStep !== 'object') return []
    const step = rawStep as Record<string, unknown>
    const description = typeof step.description === 'string' ? step.description : ''
    if (!description) return []
    const rawStepId = step.step_id
    const stepId = typeof rawStepId === 'string' || typeof rawStepId === 'number' ? String(rawStepId) : String(index + 1)
    return [{
      stepId,
      description,
      subagentType: typeof step.subagent_type === 'string' ? step.subagent_type : '',
    }]
  })
}

function formatAgent(value: string): string {
  if (!value || value === 'main') return '主智能体'
  if (value === 'general_assistant') return '通用助手'
  if (value === 'workspace_file_agent') return '工作区文件助手'
  if (value === 'vision_agent') return '视觉助手'
  return value.replaceAll('_', ' ')
}

function elapsedLabel(event: RunEvent): string {
  if (!runStartedAt.value) return '刚刚'
  const seconds = Math.max(0, (event.receivedAt - runStartedAt.value) / 1000)
  return `+${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`
}

function pushEvent(type: string, data: Record<string, unknown>) {
  if (type === 'done' && events.value.some((event) => event.type === 'done')) return
  events.value.push({ id: ++eventSequence, type, data, receivedAt: Date.now() })
  scrollTraceToBottom()
  scrollToBottom()
}

function parseSseFrame(frame: string): { type: string; data: Record<string, unknown> } | null {
  let type = 'message'
  const dataLines: string[] = []
  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(':')) continue
    const separator = rawLine.indexOf(':')
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator)
    let value = separator === -1 ? '' : rawLine.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') type = value
    if (field === 'data') dataLines.push(value)
  }
  if (!dataLines.length) return null
  const rawData = dataLines.join('\n')
  try {
    const parsed = JSON.parse(rawData) as unknown
    return { type, data: parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : { text: parsed } }
  } catch {
    return { type, data: { text: rawData } }
  }
}

function handleOutputScroll() {
  const panel = outputPanel.value
  if (!panel) return
  shouldAutoScroll.value = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 96
}

function handleTraceScroll() {
  const element = traceTimeline.value
  if (!element) return
  traceShouldAutoScroll.value = element.scrollHeight - element.scrollTop - element.clientHeight < 64
}

function scrollTraceToBottom() {
  if (!traceShouldAutoScroll.value) return
  nextTick(() => {
    const element = traceTimeline.value
    if (element) element.scrollTop = element.scrollHeight
  })
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const panel = outputPanel.value
    if (!panel || (!force && !shouldAutoScroll.value)) return
    panel.scrollTop = panel.scrollHeight
  })
}

function inferAttachmentKind(filename: string, mimeType: string): MultiAgentAttachmentKind {
  const extension = filename.toLocaleLowerCase().match(/\.[^.]+$/)?.[0] || ''
  if (mimeType.startsWith('image/') || ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff'].includes(extension)) return 'image'
  if (['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'].includes(extension)) return 'pdf_office_unparsed'
  if (mimeType.startsWith('text/') || [
    '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.jsonl', '.yaml', '.yml',
    '.xml', '.html', '.css', '.js', '.ts', '.tsx', '.jsx', '.vue', '.py', '.java',
    '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.cs', '.php', '.rb', '.sh', '.ps1',
    '.sql', '.toml', '.ini', '.cfg', '.conf', '.log', '.env',
  ].includes(extension)) return 'text'
  return 'binary'
}

function attachmentKindLabel(kind: MultiAgentAttachmentKind): string {
  if (kind === 'image') return '图片'
  if (kind === 'text') return '可读取文本'
  if (kind === 'pdf_office_unparsed') return '暂不解析内容'
  return '文件'
}

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function messageAttachments(message: Message): Array<{ attachment_id: string; filename: string }> {
  const value = message.metadata?.attachments
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const record = item as Record<string, unknown>
    if (typeof record.attachment_id !== 'string' || typeof record.filename !== 'string') return []
    return [{ attachment_id: record.attachment_id, filename: record.filename }]
  })
}

async function loadWorkspaceRoots() {
  try {
    const response = await api.listMultiAgentWorkspaceRoots()
    workspaceRoots.value = response.roots
    if (!workspacePath.value && response.roots.length) workspacePath.value = response.roots[0] || ''
  } catch (error) {
    workspaceError.value = error instanceof Error ? error.message : '无法加载工作区范围'
  }
}

function openAttachmentPicker() {
  attachmentInput.value?.click()
}

function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  void addAttachmentFiles(Array.from(input.files || []), 'file_picker')
  input.value = ''
}

function handleComposerPaste(event: ClipboardEvent) {
  const images = Array.from(event.clipboardData?.files || []).filter((file) => file.type.startsWith('image/'))
  if (!images.length) return
  event.preventDefault()
  const normalized = images.map((file, index) => {
    const extension = file.type.split('/')[1]?.replace('jpeg', 'jpg') || 'png'
    return new File([file], `pasted-${Date.now()}-${index + 1}.${extension}`, { type: file.type })
  })
  void addAttachmentFiles(normalized, 'clipboard')
}

async function addAttachmentFiles(files: File[], source: 'file_picker' | 'clipboard') {
  const usable = files.filter((file) => file.size > 0)
  if (!usable.length) return
  workspaceError.value = ''
  if (!activeSessionId.value || !workspaceRecord.value) {
    stagedAttachments.value.push(...usable.map((file) => ({
      id: `${Date.now()}-${crypto.randomUUID()}`,
      file,
      source,
    })))
    return
  }

  attachmentUploading.value = true
  try {
    for (const file of usable) {
      const attachment = await api.uploadMultiAgentAttachment(
        activeSessionId.value, file, source,
      )
      pendingAttachments.value.push(attachment)
      sessionAttachments.value.push(attachment)
    }
  } catch (error) {
    workspaceError.value = error instanceof Error ? error.message : '附件上传失败'
  } finally {
    attachmentUploading.value = false
  }
}

async function removePendingAttachment(id: string) {
  const stagedIndex = stagedAttachments.value.findIndex((item) => item.id === id)
  if (stagedIndex >= 0) {
    stagedAttachments.value.splice(stagedIndex, 1)
    return
  }
  const attachment = pendingAttachments.value.find((item) => item.attachment_id === id)
  if (!attachment || !activeSessionId.value) return
  try {
    await api.deleteMultiAgentAttachment(activeSessionId.value, attachment.attachment_id)
    pendingAttachments.value = pendingAttachments.value.filter((item) => item.attachment_id !== id)
    sessionAttachments.value = sessionAttachments.value.filter((item) => item.attachment_id !== id)
  } catch (error) {
    workspaceError.value = error instanceof Error ? error.message : '附件移除失败'
  }
}

async function ensureSessionWorkspace(query: string): Promise<string> {
  if (!workspacePath.value.trim()) throw new Error('请先选择工作区文件夹')
  if (activeSessionId.value && workspaceRecord.value) return activeSessionId.value

  let sessionId = activeSessionId.value
  let created = false
  if (!sessionId) {
    const session = await api.createSession(query.slice(0, 50), 'multi_agent')
    sessionId = session.session_id
    created = true
  }
  try {
    workspaceRecord.value = await api.configureMultiAgentWorkspace(
      sessionId, workspacePath.value, workspacePermission.value,
    )
    activeSessionId.value = sessionId
    return sessionId
  } catch (error) {
    if (created) {
      try { await api.deleteSession(sessionId) } catch { /* best effort */ }
    }
    throw error
  }
}

async function uploadStagedAttachments(sessionId: string) {
  if (!stagedAttachments.value.length) return
  attachmentUploading.value = true
  try {
    for (const item of stagedAttachments.value) {
      const attachment = await api.uploadMultiAgentAttachment(
        sessionId, item.file, item.source,
      )
      pendingAttachments.value.push(attachment)
      sessionAttachments.value.push(attachment)
    }
    stagedAttachments.value = []
  } finally {
    attachmentUploading.value = false
  }
}

function choosePrompt(value: string) {
  taskInput.value = value
  nextTick(() => composerInput.value?.focus())
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void submitTask()
}

function resetRun() {
  if (running.value) stopRun()
  const sessionId = activeSessionId.value
  const pendingIds = pendingAttachments.value.map((item) => item.attachment_id)
  if (sessionId && pendingIds.length) {
    void Promise.allSettled(
      pendingIds.map((id) => api.deleteMultiAgentAttachment(sessionId, id)),
    )
  }
  events.value = []
  currentTask.value = ''
  activeSessionId.value = ''
  activeTurnId.value = ''
  conversationMessages.value = []
  workspaceRecord.value = null
  workspacePermission.value = 'read_only'
  workspaceError.value = ''
  stagedAttachments.value = []
  pendingAttachments.value = []
  sessionAttachments.value = []
  workspacePath.value = workspaceRoots.value[0] || ''
  shouldAutoScroll.value = true
  traceShouldAutoScroll.value = true
  nextTick(() => composerInput.value?.focus())
}

async function stopRun() {
  const sessionId = activeSessionId.value
  if (sessionId) {
    const headers = new Headers()
    const apiKey = localStorage.getItem(STORAGE_KEYS.apiKey)
    if (apiKey) headers.set('Authorization', `Bearer ${apiKey}`)
    try {
      const response = await fetch(
        `${getSavedApiBase()}/multi-agent/chat/${encodeURIComponent(sessionId)}/cancel`,
        { method: 'POST', headers },
      )
      if (response.ok) {
        const result = await response.json() as { cancelled?: boolean }
        if (result.cancelled) return
      }
    } catch {
      // 无法送达协作式中止时，再终止本地流连接。
    }
  }
  activeController.value?.abort()
}

function formatSessionTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function loadMultiAgentSessions(showError = true) {
  sessionsLoading.value = true
  sessionsError.value = ''
  try {
    multiAgentSessions.value = await api.listSessions('multi_agent')
  } catch (error) {
    sessionsError.value = error instanceof Error ? error.message : '历史任务加载失败'
    if (!showError) sessionsError.value = ''
  } finally {
    sessionsLoading.value = false
  }
}

async function loadHistoricalSession(session: Session) {
  if (running.value) return
  loadingSessionId.value = session.session_id
  activeSessionId.value = session.session_id
  events.value = []
  activeTurnId.value = ''
  currentTask.value = ''
  workspaceError.value = ''
  stagedAttachments.value = []
  pendingAttachments.value = []
  runStartedAt.value = new Date(session.created_at).getTime() || Date.now()
  try {
    const [messages, workspace, attachments] = await Promise.all([
      api.getMessages(session.session_id),
      api.getMultiAgentWorkspace(session.session_id),
      api.listMultiAgentAttachments(session.session_id),
    ])
    conversationMessages.value = messages
    workspaceRecord.value = workspace
    sessionAttachments.value = attachments
    if (workspace) {
      workspacePath.value = workspace.root_path
      workspacePermission.value = workspace.permission
    } else {
      workspacePath.value = workspaceRoots.value[0] || ''
      workspacePermission.value = 'read_only'
    }
    scrollToBottom(true)
  } catch (error) {
    pushEvent('error', {
      message: error instanceof Error ? error.message : '无法加载历史任务',
    })
  } finally {
    loadingSessionId.value = ''
  }
}

async function confirmDeleteSession() {
  const session = sessionToDelete.value
  if (!session || deleting.value || running.value) return

  deleting.value = true
  sessionsError.value = ''
  try {
    await api.deleteSession(session.session_id)
    multiAgentSessions.value = multiAgentSessions.value.filter(
      (item) => item.session_id !== session.session_id,
    )
    if (activeSessionId.value === session.session_id) resetRun()
    sessionToDelete.value = null
  } catch (error) {
    sessionsError.value = error instanceof Error ? error.message : '历史任务删除失败'
  } finally {
    deleting.value = false
  }
}

async function copyAnswer() {
  if (!answerText.value) return
  await navigator.clipboard.writeText(answerText.value)
  copied.value = true
  window.clearTimeout(copyTimer)
  copyTimer = window.setTimeout(() => { copied.value = false }, 1600)
}

async function submitTask() {
  const query = taskInput.value.trim()
  if (!query || running.value) return

  const controller = new AbortController()
  activeController.value = controller
  running.value = true
  currentTask.value = query
  taskInput.value = ''
  events.value = []
  activeTurnId.value = ''
  runStartedAt.value = Date.now()
  shouldAutoScroll.value = true
  traceShouldAutoScroll.value = true
  copied.value = false
  scrollToBottom(true)

  const headers = new Headers({
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  })
  const apiKey = localStorage.getItem(STORAGE_KEYS.apiKey)
  if (apiKey) headers.set('Authorization', `Bearer ${apiKey}`)

  let requestStarted = false
  try {
    const sessionId = await ensureSessionWorkspace(query)
    await uploadStagedAttachments(sessionId)
    const attachmentIds = pendingAttachments.value.map((item) => item.attachment_id)
    const response = await fetch(`${getSavedApiBase()}/multi-agent/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        query,
        session_id: sessionId,
        attachment_ids: attachmentIds,
      }),
      signal: controller.signal,
    })
    if (!response.ok) {
      if (response.status === 401) window.dispatchEvent(new Event('mka:unauthorized'))
      let message = `${response.status} ${response.statusText}`.trim()
      try {
        const body = await response.json() as { detail?: string; error?: { message?: string } }
        message = body.error?.message || body.detail || message
      } catch {
        // 非 JSON 错误响应使用 HTTP 状态文本。
      }
      throw new Error(message || '请求失败')
    }
    if (!response.body) throw new Error('浏览器未提供流式响应内容')
    requestStarted = true

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let terminalEventReceived = false

    while (!terminalEventReceived) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })

      while (true) {
        const boundary = /\r?\n\r?\n/.exec(buffer)
        if (!boundary || boundary.index === undefined) break
        const frame = buffer.slice(0, boundary.index)
        buffer = buffer.slice(boundary.index + boundary[0].length)
        const parsed = parseSseFrame(frame)
        if (!parsed) continue
        pushEvent(parsed.type, parsed.data)
        if (parsed.type === 'start') {
          activeSessionId.value = typeof parsed.data.session_id === 'string'
            ? parsed.data.session_id
            : ''
        }
        if (parsed.type === 'turn_started') {
          activeTurnId.value = typeof parsed.data.turn_id === 'string'
            ? parsed.data.turn_id
            : ''
        }
        if (parsed.type === 'done' || parsed.type === 'error') {
          terminalEventReceived = true
          break
        }
      }

      if (done) break
    }

    if (!terminalEventReceived && buffer.trim()) {
      const parsed = parseSseFrame(buffer)
      if (parsed) {
        pushEvent(parsed.type, parsed.data)
        if (parsed.type === 'start') {
          activeSessionId.value = typeof parsed.data.session_id === 'string'
            ? parsed.data.session_id
            : ''
        }
        if (parsed.type === 'turn_started') {
          activeTurnId.value = typeof parsed.data.turn_id === 'string'
            ? parsed.data.turn_id
            : ''
        }
        terminalEventReceived = parsed.type === 'done' || parsed.type === 'error'
      }
    }

    if (terminalEventReceived) await reader.cancel()
    else if (!controller.signal.aborted) pushEvent('error', { message: '流式连接提前结束，请重试。' })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      pushEvent('cancelled', { message: '已停止本次任务。' })
    } else {
      pushEvent('error', { message: error instanceof Error ? error.message : '无法连接到多智能体服务' })
    }
  } finally {
    if (requestStarted) {
      stagedAttachments.value = []
      pendingAttachments.value = []
    }
    if (activeController.value === controller) activeController.value = null
    running.value = false
    if (activeSessionId.value) {
      try {
        conversationMessages.value = await api.getMessages(activeSessionId.value)
      } catch {
        // SSE 结果仍可展示，下次加载会话时再同步历史。
      }
    }
    await loadMultiAgentSessions(false)
    scrollToBottom()
  }
}

function renderConversationMessage(content: string): string {
  return DOMPurify.sanitize(marked.parse(content) as string)
}

onMounted(() => {
  void loadWorkspaceRoots()
  void loadMultiAgentSessions(false)
})

onBeforeUnmount(() => {
  activeController.value?.abort()
  window.clearTimeout(copyTimer)
})
</script>

<style scoped>
.ma-workspace {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  overflow: hidden;
  background: var(--surface);
}

.ma-rail {
  min-height: 0;
  padding: 21px 18px 18px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--line);
  background: var(--surface-raised);
}

.ma-back-link {
  width: fit-content;
  min-height: 32px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 650;
  transition: color 150ms ease, background-color 150ms ease;
}

.ma-back-link:hover { color: var(--text); background: var(--surface-hover); }

.ma-agent-intro {
  margin-top: 24px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.ma-agent-mark {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: var(--radius-md);
  color: var(--accent);
  background: var(--accent-soft);
}

.ma-product-name { color: var(--text-muted); font-size: 0.64rem; font-weight: 700; }
.ma-agent-intro h1 { margin-top: 2px; font-size: 1.04rem; letter-spacing: -0.025em; }
.ma-agent-description { margin-top: 14px; color: var(--text-soft); font-size: 0.73rem; line-height: 1.65; }

.ma-history { min-height: 0; margin-top: 22px; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 9px; }
.ma-history > header { display: flex; align-items: center; justify-content: space-between; }
.ma-history h2 { color: var(--text-soft); font-size: 0.7rem; }
.ma-history > header button { width: 27px; height: 27px; display: grid; place-items: center; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; }
.ma-history > header button:hover { background: var(--surface-hover); color: var(--text); }
.ma-history-list { max-height: 176px; overflow-y: auto; display: grid; gap: 4px; }
.ma-history-item { min-width: 0; min-height: 48px; padding: 0 5px 0 0; display: flex; align-items: center; gap: 3px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); }
.ma-history-item:hover, .ma-history-item.is-active { border-color: var(--line); background: var(--surface-hover); color: var(--text); }
.ma-history-main { min-width: 0; min-height: 46px; padding: 7px 5px 7px 10px; flex: 1; display: flex; align-items: center; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.ma-history-main:disabled, .ma-history-delete:disabled { cursor: default; opacity: 0.55; }
.ma-history-main > span { min-width: 0; display: grid; gap: 3px; }
.ma-history-main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-soft); font-size: 0.66rem; }
.ma-history-main small { font-size: 0.58rem; }
.ma-history-delete { width: 29px; height: 29px; display: grid; place-items: center; flex: 0 0 auto; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; opacity: 0; transition: color 150ms ease, background-color 150ms ease, opacity 150ms ease; }
.ma-history-item:hover .ma-history-delete, .ma-history-item:focus-within .ma-history-delete, .ma-history-item.is-active .ma-history-delete { opacity: 1; }
.ma-history-delete:hover:not(:disabled) { background: var(--danger-soft); color: var(--danger); }
.ma-history-delete:focus-visible { opacity: 1; outline: 2px solid var(--accent); outline-offset: 1px; }
.ma-history-state { padding: 8px 2px; color: var(--text-muted); font-size: 0.63rem; }
.ma-history-state.is-error { color: var(--danger); }

.ma-pipeline {
  margin: 22px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
}

.ma-pipeline li {
  min-height: 67px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  position: relative;
  color: var(--text-muted);
}

.ma-pipeline li:not(:last-child)::after {
  content: '';
  width: 1px;
  position: absolute;
  top: 33px;
  bottom: 0;
  left: 16px;
  background: var(--line-strong);
}

.ma-pipeline li.is-complete:not(:last-child)::after { background: var(--success); }

.ma-stage-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  position: relative;
  z-index: 1;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  color: var(--text-muted);
}

.ma-stage-copy { min-width: 0; padding-top: 2px; display: grid; gap: 4px; }
.ma-stage-copy strong { color: var(--text-soft); font-size: 0.73rem; }
.ma-stage-copy small { font-size: 0.62rem; }
.ma-pipeline li.is-active .ma-stage-icon { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.ma-pipeline li.is-active .ma-stage-copy strong { color: var(--text); }
.ma-pipeline li.is-complete .ma-stage-icon { border-color: color-mix(in srgb, var(--success) 30%, var(--line)); background: var(--success-soft); color: var(--success); }
.ma-pipeline li.is-error .ma-stage-icon { border-color: color-mix(in srgb, var(--danger) 30%, var(--line)); background: var(--danger-soft); color: var(--danger); }
.ma-pipeline li.is-stopped .ma-stage-icon { border-color: color-mix(in srgb, var(--warning) 30%, var(--line)); background: var(--warning-soft); color: var(--warning); }

.ma-architecture {
  margin-top: auto;
  padding-top: 15px;
  display: grid;
  gap: 11px;
  border-top: 1px solid var(--line);
}

.ma-architecture div { display: grid; gap: 4px; }
.ma-architecture span { display: flex; align-items: center; gap: 7px; color: var(--text-soft); font-size: 0.7rem; font-weight: 680; }
.ma-architecture svg { color: var(--accent); }
.ma-architecture small { padding-left: 24px; color: var(--text-muted); font-size: 0.61rem; }

.ma-main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 72px auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.ma-header {
  min-width: 0;
  padding: 0 clamp(20px, 3vw, 36px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

.ma-header > div:first-child { min-width: 0; display: grid; gap: 4px; }
.ma-header h2 { font-size: 0.94rem; letter-spacing: -0.02em; }
.ma-header p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted); font-size: 0.66rem; }
.ma-header-actions { display: flex; align-items: center; gap: 9px; }

.ma-icon-button,
.ma-copy-button,
.ma-stop-button,
.ma-submit-button {
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, transform 100ms ease;
}

.ma-icon-button:active,
.ma-copy-button:active,
.ma-stop-button:active,
.ma-submit-button:active:not(:disabled) { transform: translateY(1px); }

.ma-icon-button {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text-muted);
}

.ma-icon-button:hover { background: var(--surface-hover); color: var(--text); }

.ma-runtime-status {
  min-height: 30px;
  padding: 0 9px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  background: var(--surface-subtle);
  color: var(--text-soft);
  font-size: 0.66rem;
  font-weight: 700;
  white-space: nowrap;
}

.ma-runtime-status.is-running { background: var(--warning-soft); color: var(--warning); }
.ma-runtime-status.is-complete { background: var(--success-soft); color: var(--success); }
.ma-runtime-status.is-error { background: var(--danger-soft); color: var(--danger); }
.ma-runtime-status.is-stopped { background: var(--warning-soft); color: var(--warning); }
.ma-spinning { animation: ma-spin 0.9s linear infinite; }
@keyframes ma-spin { to { transform: rotate(360deg); } }

.ma-resource-bar {
  padding: 9px clamp(20px, 3vw, 36px) 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-raised);
}
.ma-workspace-picker { min-width: 0; display: flex; align-items: center; gap: 8px; }
.ma-workspace-picker > svg { flex: 0 0 auto; color: var(--accent); }
.ma-workspace-picker label { color: var(--text-soft); font-size: 0.66rem; font-weight: 720; }
.ma-workspace-picker input { min-width: 120px; flex: 1; }
.ma-workspace-picker input,
.ma-workspace-picker select { height: 33px; padding: 0 9px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface); color: var(--text); font-size: 0.67rem; outline: none; }
.ma-workspace-picker input:focus,
.ma-workspace-picker select:focus { border-color: var(--accent); }
.ma-workspace-picker input:disabled,
.ma-workspace-picker select:disabled { opacity: 0.72; cursor: not-allowed; }
.ma-workspace-picker select { flex: 0 0 auto; }
.ma-resource-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.ma-resource-note,
.ma-resource-error { max-width: 310px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.61rem; }
.ma-resource-note { color: var(--text-muted); }
.ma-resource-error { color: var(--danger); }
.ma-attach-button { min-height: 33px; padding: 0 10px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface); color: var(--text-soft); font-size: 0.66rem; font-weight: 700; cursor: pointer; }
.ma-attach-button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.ma-attach-button:disabled { opacity: 0.48; cursor: not-allowed; }
.ma-attachment-list { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 7px; }
.ma-attachment-chip { max-width: 290px; min-height: 37px; padding: 5px 6px 5px 8px; display: flex; align-items: center; gap: 7px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface); color: var(--text-soft); }
.ma-attachment-chip > svg { flex: 0 0 auto; color: var(--accent); }
.ma-attachment-chip > span { min-width: 0; display: grid; gap: 1px; }
.ma-attachment-chip strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.64rem; }
.ma-attachment-chip small { color: var(--text-muted); font-size: 0.55rem; }
.ma-attachment-chip button { width: 24px; height: 24px; display: grid; place-items: center; border: 0; border-radius: 7px; background: transparent; color: var(--text-muted); cursor: pointer; }
.ma-attachment-chip button:hover { background: var(--surface-hover); color: var(--danger); }

.ma-output {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  padding: clamp(20px, 3vw, 36px);
  background: var(--bg);
  scroll-behavior: smooth;
}

.ma-empty {
  width: min(100%, 1080px);
  min-height: 100%;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(360px, 1.1fr);
  align-items: center;
  gap: clamp(38px, 6vw, 84px);
  padding: 32px 0 72px;
}

.ma-empty-copy { max-width: 520px; }
.ma-empty-mark { width: 62px; height: 62px; display: grid; place-items: center; margin-bottom: 24px; border-radius: var(--radius-lg); background: var(--accent-soft); color: var(--accent); }
.ma-empty h2 { max-width: 14ch; font-size: clamp(2rem, 4vw, 3.5rem); line-height: 1.05; letter-spacing: -0.055em; font-weight: 710; }
.ma-empty-copy p { max-width: 47ch; margin-top: 17px; color: var(--text-soft); font-size: 0.84rem; line-height: 1.72; }

.ma-prompt-starters { display: grid; gap: 9px; }
.ma-prompt-starters button {
  min-height: 82px;
  padding: 15px 15px 15px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-soft);
  text-align: left;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: background-color 160ms ease, border-color 160ms ease, transform 130ms ease;
}

.ma-prompt-starters button:first-child { min-height: 104px; }
.ma-prompt-starters button:hover { background: var(--surface-raised); border-color: var(--line-strong); transform: translateY(-1px); }
.ma-prompt-starters button:active { transform: translateY(1px); }
.ma-prompt-starters button > span { display: grid; gap: 6px; }
.ma-prompt-starters strong { color: var(--text); font-size: 0.8rem; }
.ma-prompt-starters small { color: var(--text-muted); font-size: 0.67rem; line-height: 1.5; }
.ma-prompt-starters svg { flex: 0 0 auto; color: var(--accent); }

.ma-conversation {
  width: min(100%, 920px);
  min-width: 0;
  margin: 0 auto 24px;
  display: grid;
  gap: 14px;
}

.ma-conversation-message {
  width: min(82%, 760px);
  min-width: 0;
  max-width: 100%;
  padding: 14px 16px;
  display: grid;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.ma-conversation-message.is-user {
  justify-self: end;
  border-color: color-mix(in srgb, var(--accent) 22%, var(--line));
  background: var(--accent-soft);
}

.ma-conversation-message.is-assistant { justify-self: start; }
.ma-conversation-message .message-markdown { min-width: 0; max-width: 100%; }
.ma-conversation-role { color: var(--text-muted); font-size: 0.61rem; font-weight: 750; }
.ma-conversation-message > p { color: var(--text); font-size: 0.79rem; line-height: 1.62; white-space: pre-wrap; overflow-wrap: anywhere; }
.ma-conversation-message > small { color: var(--warning); font-size: 0.62rem; font-weight: 680; }
.ma-message-attachments { display: flex; flex-wrap: wrap; gap: 5px; }
.ma-message-attachments span { padding: 4px 7px; display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; background: var(--surface); color: var(--text-muted); font-size: 0.58rem; }

.ma-user-brief {
  width: min(100%, 1180px);
  margin: 0 auto 16px;
  padding: 16px 18px;
  display: grid;
  grid-template-columns: 37px minmax(0, 1fr);
  gap: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.ma-brief-icon { width: 37px; height: 37px; display: grid; place-items: center; border-radius: 10px; color: var(--accent); background: var(--accent-soft); }
.ma-user-brief > div { min-width: 0; display: grid; gap: 5px; }
.ma-user-brief span:not(.ma-brief-icon) { color: var(--text-muted); font-size: 0.62rem; font-weight: 700; }
.ma-user-brief p { color: var(--text); font-size: 0.82rem; line-height: 1.62; overflow-wrap: anywhere; }

.ma-results-grid {
  width: min(100%, 1180px);
  min-width: 0;
  min-height: 0;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(330px, 0.82fr) minmax(0, 1.18fr);
  align-items: stretch;
  gap: 16px;
}

.ma-trace-panel,
.ma-answer-panel {
  width: 100%;
  min-width: 0;
  min-height: 0;
  height: clamp(400px, calc(100dvh - 300px), 640px);
  max-height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.ma-panel-header { flex: 0 0 auto; min-height: 57px; padding: 0 17px; display: flex; align-items: center; justify-content: space-between; gap: 14px; border-bottom: 1px solid var(--line); background: var(--surface-raised); }
.ma-panel-header > div { display: flex; align-items: center; gap: 8px; }
.ma-panel-header svg { color: var(--accent); }
.ma-panel-header h3 { font-size: 0.79rem; letter-spacing: -0.01em; }
.ma-panel-header > span { color: var(--text-muted); font-size: 0.62rem; }

.ma-copy-button {
  min-height: 31px;
  padding: 0 9px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 0.65rem;
}

.ma-copy-button:hover { background: var(--surface-hover); color: var(--text); }

.ma-timeline {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  padding: 8px 17px 15px;
}
.ma-trace-event {
  min-width: 0;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  padding: 11px 0 12px;
  position: relative;
  animation: ma-enter 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes ma-enter { from { opacity: 0; transform: translateY(4px); } }
.ma-trace-event:not(:last-child)::after { content: ''; width: 1px; position: absolute; top: 38px; bottom: -1px; left: 14px; background: var(--line); }
.ma-trace-icon { width: 30px; height: 30px; display: grid; place-items: center; position: relative; z-index: 1; border-radius: 9px; background: var(--surface-subtle); color: var(--text-muted); }
.ma-trace-event.is-accent .ma-trace-icon { background: var(--accent-soft); color: var(--accent); }
.ma-trace-event.is-success .ma-trace-icon { background: var(--success-soft); color: var(--success); }
.ma-trace-event.is-error .ma-trace-icon { background: var(--danger-soft); color: var(--danger); }
.ma-trace-copy { min-width: 0; max-width: 100%; padding-top: 3px; }
.ma-trace-copy > header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.ma-trace-copy > header strong { min-width: 0; color: var(--text); font-size: 0.72rem; overflow-wrap: anywhere; word-break: break-word; }
.ma-trace-copy time { flex: 0 0 auto; color: var(--text-muted); font: 0.58rem 'Cascadia Code', 'SFMono-Regular', monospace; }
.ma-trace-copy > p { max-width: 100%; margin-top: 5px; color: var(--text-soft); font-size: 0.68rem; line-height: 1.55; overflow-wrap: anywhere; word-break: break-word; }

.ma-plan-list { margin: 11px 0 1px; padding: 0; list-style: none; display: grid; gap: 8px; }
.ma-plan-list li { min-width: 0; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 8px; }
.ma-plan-list li > span { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 7px; background: var(--surface-subtle); color: var(--text-muted); font: 0.58rem 'Cascadia Code', 'SFMono-Regular', monospace; }
.ma-plan-list li > div { min-width: 0; display: grid; gap: 3px; }
.ma-plan-list strong { color: var(--text-soft); font-size: 0.66rem; line-height: 1.45; overflow-wrap: anywhere; }
.ma-plan-list small { width: fit-content; max-width: 100%; color: var(--accent); font-size: 0.58rem; font-weight: 650; overflow-wrap: anywhere; word-break: break-word; }
.ma-complexity { display: inline-flex; margin-top: 8px; padding: 4px 7px; border-radius: 6px; background: var(--accent-soft); color: var(--accent); font-size: 0.58rem; font-weight: 700; }

.ma-trace-skeleton {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 18px;
  display: grid;
  gap: 13px;
}
.ma-trace-skeleton span { display: block; height: 48px; border-radius: var(--radius-sm); background: var(--surface-subtle); animation: ma-skeleton 1.3s ease-in-out infinite alternate; }
.ma-trace-skeleton span:nth-child(2) { width: 88%; }.ma-trace-skeleton span:nth-child(3) { width: 72%; }
@keyframes ma-skeleton { to { opacity: 0.45; } }

.ma-answer-content {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  padding: 24px 25px 28px;
  font-size: 0.82rem;
}
.ma-answer-content:deep(h1:first-child),
.ma-answer-content:deep(h2:first-child),
.ma-answer-content:deep(h3:first-child) { margin-top: 0; }
.ma-answer-content:deep(p:last-child) { margin-bottom: 0; }
.ma-conversation-message .message-markdown:deep(p),
.ma-conversation-message .message-markdown:deep(li),
.ma-conversation-message .message-markdown:deep(blockquote),
.ma-answer-content:deep(p),
.ma-answer-content:deep(li),
.ma-answer-content:deep(blockquote) { max-width: 100%; overflow-wrap: anywhere; word-break: break-word; }
.ma-conversation-message .message-markdown:deep(pre),
.ma-answer-content:deep(pre) { max-width: 100%; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }
.ma-conversation-message .message-markdown:deep(table),
.ma-answer-content:deep(table) { width: 100%; max-width: 100%; table-layout: fixed; }
.ma-conversation-message .message-markdown:deep(th),
.ma-conversation-message .message-markdown:deep(td),
.ma-answer-content:deep(th),
.ma-answer-content:deep(td) { overflow-wrap: anywhere; word-break: break-word; }

.ma-answer-skeleton {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  padding: 27px 25px;
  display: grid;
  align-content: start;
  gap: 13px;
}
.ma-answer-skeleton div { margin-bottom: 6px; display: flex; align-items: center; gap: 9px; }
.ma-answer-skeleton span,
.ma-answer-skeleton i { display: block; height: 13px; border-radius: 5px; background: var(--surface-subtle); animation: ma-skeleton 1.3s ease-in-out infinite alternate; }
.ma-answer-skeleton span:first-child { width: 41%; height: 19px; }.ma-answer-skeleton span:last-child { width: 16%; height: 19px; }
.ma-answer-skeleton i:nth-of-type(1) { width: 96%; }.ma-answer-skeleton i:nth-of-type(2) { width: 91%; }.ma-answer-skeleton i:nth-of-type(3) { width: 78%; }.ma-answer-skeleton i:nth-of-type(4) { width: 86%; }

.ma-answer-state {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  padding: 34px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: safe center;
  text-align: center;
  color: var(--text-muted);
}
.ma-answer-state svg { margin-bottom: 12px; }
.ma-answer-state strong { color: var(--text); font-size: 0.8rem; }
.ma-answer-state p { max-width: 38ch; margin-top: 6px; font-size: 0.68rem; line-height: 1.55; }
.ma-answer-state.is-error { color: var(--danger); background: color-mix(in srgb, var(--danger-soft) 38%, var(--surface)); }
.ma-answer-state.is-error strong { color: var(--danger); }
.ma-answer-state.is-stopped { color: var(--warning); background: color-mix(in srgb, var(--warning-soft) 38%, var(--surface)); }
.ma-answer-state.is-stopped strong { color: var(--warning); }
.ma-answer-footer { flex: 0 0 auto; min-height: 42px; padding: 0 17px; display: flex; align-items: center; gap: 7px; border-top: 1px solid var(--line); background: var(--success-soft); color: var(--success); font-size: 0.64rem; font-weight: 680; }

.ma-composer-wrap { padding: 11px clamp(20px, 3vw, 36px) 13px; border-top: 1px solid var(--line); background: var(--surface); }
.ma-composer { width: min(100%, 900px); margin: 0 auto; padding: 10px 11px 9px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); background: var(--surface-raised); box-shadow: var(--shadow-sm); transition: border-color 150ms ease, box-shadow 150ms ease; }
.ma-composer.is-focused { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 11%, transparent), var(--shadow-sm); }
.ma-composer textarea { width: 100%; min-height: 38px; max-height: 160px; padding: 3px 2px; resize: vertical; border: 0; outline: 0; background: transparent; color: var(--text); font-size: 0.82rem; line-height: 1.55; }
.ma-composer textarea::placeholder { color: var(--text-muted); }
.ma-composer textarea:disabled { cursor: not-allowed; opacity: 0.68; }
.ma-composer-tools { min-height: 35px; margin-top: 7px; display: flex; align-items: center; gap: 10px; }
.ma-composer-hint { color: var(--text-muted); font-size: 0.61rem; }
.ma-character-count { margin-left: auto; color: var(--text-muted); font: 0.58rem 'Cascadia Code', 'SFMono-Regular', monospace; }
.ma-stop-button,
.ma-submit-button { min-height: 35px; padding: 0 12px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; white-space: nowrap; font-size: 0.72rem; font-weight: 700; }
.ma-stop-button { border: 1px solid var(--line-strong); background: var(--surface); color: var(--danger); }
.ma-stop-button:hover { background: var(--danger-soft); border-color: color-mix(in srgb, var(--danger) 26%, var(--line)); }
.ma-submit-button { border: 1px solid var(--accent); background: var(--accent); color: var(--accent-contrast); }
.ma-submit-button:hover:not(:disabled) { border-color: var(--accent-hover); background: var(--accent-hover); }
.ma-submit-button:disabled { opacity: 0.46; cursor: not-allowed; }

@media (max-width: 1180px) {
  .ma-results-grid { grid-template-columns: 1fr; }
  .ma-answer-panel { position: static; }
}

@media (max-width: 960px) {
  .ma-workspace { grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); }
  .ma-rail { padding: 14px 20px; display: grid; grid-template-columns: auto minmax(180px, 0.7fr) minmax(430px, 1.3fr); align-items: center; gap: 17px; border-right: 0; border-bottom: 1px solid var(--line); }
  .ma-back-link { display: none; }
  .ma-agent-intro { margin: 0; }
  .ma-agent-description, .ma-architecture { display: none; }
  .ma-history { display: none; }
  .ma-pipeline { margin: 0; grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .ma-pipeline li { min-height: auto; grid-template-columns: 30px minmax(0, 1fr); gap: 7px; }
  .ma-pipeline li:not(:last-child)::after { width: auto; height: 1px; top: 15px; right: -1px; bottom: auto; left: 29px; }
  .ma-stage-icon { width: 30px; height: 30px; border-radius: 9px; }
  .ma-stage-copy { padding-top: 0; }
  .ma-stage-copy strong { font-size: 0.65rem; }
  .ma-stage-copy small { display: none; }
}

@media (max-width: 820px) {
  .ma-workspace { height: calc(100dvh - 124px); }
  .ma-rail { grid-template-columns: minmax(150px, 0.65fr) minmax(360px, 1.35fr); padding: 12px 14px; }
  .ma-agent-mark { width: 40px; height: 40px; }
  .ma-product-name { display: none; }
  .ma-agent-intro h1 { margin-top: 0; font-size: 0.82rem; }
  .ma-header { padding: 0 15px; }
  .ma-resource-bar { padding-inline: 14px; grid-template-columns: 1fr; }
  .ma-resource-actions { justify-content: space-between; }
  .ma-output { padding: 18px 14px; }
  .ma-composer-wrap { padding: 9px 11px 10px; }
}

@media (max-width: 640px) {
  .ma-rail { grid-template-columns: 1fr; gap: 10px; }
  .ma-agent-intro { display: none; }
  .ma-stage-copy strong { font-size: 0.59rem; }
  .ma-header p { display: none; }
  .ma-header h2 { font-size: 0.86rem; }
  .ma-workspace-picker { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; }
  .ma-workspace-picker label { display: none; }
  .ma-resource-note, .ma-resource-error { display: none; }
  .ma-empty { grid-template-columns: 1fr; align-content: start; gap: 30px; padding: 28px 2px 48px; }
  .ma-empty-mark { width: 52px; height: 52px; margin-bottom: 19px; }
  .ma-empty h2 { font-size: clamp(1.85rem, 9vw, 2.55rem); }
  .ma-prompt-starters button, .ma-prompt-starters button:first-child { min-height: 76px; }
  .ma-user-brief { padding: 13px; grid-template-columns: 32px minmax(0, 1fr); }
  .ma-brief-icon { width: 32px; height: 32px; }
  .ma-panel-header { padding: 0 14px; }
  .ma-timeline { padding-inline: 14px; }
  .ma-answer-content { min-height: 220px; padding: 20px 17px 24px; }
  .ma-answer-state, .ma-answer-skeleton { min-height: 235px; padding: 24px 18px; }
  .ma-composer { border-radius: var(--radius-md); }
  .ma-composer-hint { display: none; }
  .ma-character-count { margin-left: 0; }
  .ma-stop-button, .ma-submit-button { margin-left: auto; }
}
</style>
