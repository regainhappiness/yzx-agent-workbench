<template>
  <div class="page-scroll knowledge-page">
    <PageHeader title="知识库" description="上传资料并跟踪索引状态，为 Agent 提供可检索的上下文。">
      <template #actions>
        <button class="button secondary" type="button" :disabled="store.documentsLoading" @click="refresh">
          <ArrowClockwise :size="18" :class="{ spinning: store.documentsLoading }" /> 刷新
        </button>
        <button class="button primary" type="button" @click="openPicker"><UploadSimple :size="18" weight="bold" /> 上传文档</button>
      </template>
    </PageHeader>

    <section class="knowledge-overview" aria-label="知识库概览">
      <div><span class="overview-icon"><Files :size="21" /></span><dl><dt>{{ hasFilters ? '匹配文档' : '全部文档' }}</dt><dd>{{ store.documentsTotal }}</dd></dl></div>
      <div><span class="overview-icon"><CheckCircle :size="21" /></span><dl><dt>本页可检索</dt><dd>{{ indexedCount }}</dd></dl></div>
      <div><span class="overview-icon"><Stack :size="21" /></span><dl><dt>本页内容分块</dt><dd>{{ totalChunks }}</dd></dl></div>
      <div><span class="overview-icon"><HardDrives :size="21" /></span><dl><dt>本页存储用量</dt><dd>{{ formatSize(totalSize) }}</dd></dl></div>
    </section>

    <section
      class="upload-dropzone"
      :class="{ dragover, disabled: uploading }"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
      @click="openPicker"
    >
      <input ref="fileInput" type="file" multiple hidden accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf" @change="onFilesSelected" />
      <div class="dropzone-icon"><CloudArrowUp :size="28" weight="duotone" /></div>
      <div><strong>{{ uploading ? '正在批量上传并创建索引任务' : '拖放文件到这里' }}</strong><span>支持多选 TXT、Markdown、PDF，单个文件不超过 {{ MAX_UPLOAD_SIZE_MB }} MB，PDF 不超过 200 页</span></div>
      <label class="scope-control" @click.stop>
        <span>存储范围</span>
        <select v-model="uploadScope" :disabled="!store.isAdmin || uploading">
          <option value="private">仅自己可用</option>
          <option v-if="store.isAdmin" value="shared">团队共享</option>
        </select>
      </label>
    </section>

    <div v-if="uploadQueue.length" class="upload-queue" aria-live="polite">
      <div v-for="item in uploadQueue" :key="item.id" class="upload-queue-item">
        <FileText :size="19" aria-hidden="true" />
        <span><strong>{{ item.name }}</strong><small>{{ item.message }}</small></span>
        <StatusBadge :status="item.status" :label="item.status === 'done' ? '已提交' : item.status === 'failed' ? '失败' : '上传中'" />
        <button
          v-if="item.status === 'failed'"
          class="icon-button quiet danger-icon upload-queue-dismiss"
          type="button"
          :aria-label="`移除 ${item.name} 的失败提示`"
          title="移除提示"
          @click="removeUploadItem(item.id)"
        >
          <X :size="16" weight="bold" aria-hidden="true" />
        </button>
      </div>
    </div>

    <section class="content-section document-section">
      <div class="section-toolbar">
        <div class="section-title"><h2>文档</h2><span>{{ store.documentsTotal }} 项</span></div>
        <div class="document-filters">
          <label class="search-field wide"><MagnifyingGlass :size="17" /><input v-model="search" type="search" placeholder="搜索文件名" aria-label="搜索文档" /></label>
          <select v-model="scopeFilter" class="toolbar-select" aria-label="按范围筛选">
            <option value="all">全部范围</option><option value="private">私有</option><option value="shared">共享</option>
          </select>
          <select v-model="statusFilter" class="toolbar-select" aria-label="按状态筛选">
            <option value="all">全部状态</option><option value="indexed">可检索</option><option value="processing">处理中</option><option value="failed">失败</option>
          </select>
        </div>
      </div>

      <div v-if="store.documentsError" class="inline-alert is-error">
        <WarningCircle :size="19" weight="fill" /><span><strong>知识库服务暂不可用</strong>{{ store.documentsError }}</span>
        <button type="button" @click="refresh">重试</button>
      </div>

      <div v-if="store.documentsLoading && !pageDocuments.length" class="document-skeleton">
        <span v-for="index in 5" :key="index"></span>
      </div>
      <EmptyState v-else-if="!pageDocuments.length" :icon="FileSearch" :title="hasFilters ? '没有匹配的文档' : '知识库还是空的'" :description="hasFilters ? '调整搜索词或筛选条件。' : '上传第一份资料，索引完成后即可在对话中检索。'">
        <button v-if="!hasFilters" class="button secondary" type="button" @click="openPicker"><UploadSimple :size="18" /> 选择文件</button>
      </EmptyState>
      <div v-else class="document-table-wrap">
        <table class="document-table">
          <thead><tr><th>文档</th><th>范围</th><th>状态</th><th>分块</th><th>更新于</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <tr v-for="document in pageDocuments" :key="document.document_id" @click="showDocument(document)">
              <td><div class="file-cell"><span class="file-icon"><FilePdf v-if="document.filename.toLowerCase().endsWith('.pdf')" :size="21" /><MarkdownLogo v-else-if="document.filename.toLowerCase().endsWith('.md')" :size="21" /><FileText v-else :size="21" /></span><span><strong>{{ document.filename }}</strong><small>{{ formatSize(document.file_size) }} · {{ document.mime_type }}</small></span></div></td>
              <td><StatusBadge :status="document.scope" /></td>
              <td><StatusBadge :status="taskStatus(document)" :show-dot="isProcessing(document.status)" /></td>
              <td><span class="tabular">{{ document.chunk_count || '0' }}</span></td>
              <td><span class="date-cell">{{ formatDate(document.updated_at) }}</span></td>
              <td><button class="icon-button quiet" type="button" aria-label="打开文档详情" @click.stop="showDocument(document)"><DotsThree :size="20" weight="bold" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="store.documentsTotal > 0" class="document-pagination" aria-label="文档分页">
        <span class="pagination-summary">第 {{ store.documentsPage }} / {{ store.documentsTotalPages }} 页</span>
        <label class="page-size-control">
          <span>每页</span>
          <select :value="store.documentsPageSize" :disabled="store.documentsLoading" @change="changePageSize">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
        </label>
        <button class="button secondary pagination-button" type="button" :disabled="store.documentsLoading || store.documentsPage <= 1" @click="goToPage(store.documentsPage - 1)"><CaretLeft :size="16" /> 上一页</button>
        <button class="button secondary pagination-button" type="button" :disabled="store.documentsLoading || store.documentsPage >= store.documentsTotalPages" @click="goToPage(store.documentsPage + 1)">下一页 <CaretRight :size="16" /></button>
      </div>
    </section>

    <BaseModal :open="Boolean(selectedDocument)" title="文档详情" :description="selectedDocument?.filename" width="560px" @close="selectedDocument = null">
      <div v-if="detailLoading" class="detail-loading"><span></span><span></span><span></span></div>
      <div v-else-if="selectedDocument" class="document-detail">
        <div class="document-detail-status"><span class="file-icon large"><FileText :size="25" /></span><div><strong>{{ selectedDocument.filename }}</strong><span>{{ formatSize(selectedDocument.file_size) }}</span></div><StatusBadge :status="taskStatus(selectedDocument)" /></div>
        <dl class="detail-grid">
          <div><dt>文档 ID</dt><dd><code>{{ selectedDocument.document_id }}</code><button type="button" @click="copyId"><Copy :size="15" />复制</button></dd></div>
          <div><dt>知识范围</dt><dd>{{ selectedDocument.scope === 'shared' ? '团队共享' : '仅自己可用' }}</dd></div>
          <div><dt>内容分块</dt><dd>{{ selectedDocument.chunk_count }}</dd></div>
          <div><dt>文件类型</dt><dd>{{ selectedDocument.mime_type }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ formatFullDate(selectedDocument.created_at) }}</dd></div>
          <div><dt>最后更新</dt><dd>{{ formatFullDate(selectedDocument.updated_at) }}</dd></div>
        </dl>
        <div v-if="selectedDocument.error_message" class="inline-alert is-error"><WarningCircle :size="19" /><span>{{ selectedDocument.error_message }}</span></div>
      </div>
      <template #footer>
        <button class="button danger ghost-danger" type="button" @click="requestDelete(selectedDocument!)"><Trash :size="18" /> 删除</button>
        <span class="footer-spacer"></span>
        <button class="button secondary" type="button" @click="download(selectedDocument!)"><DownloadSimple :size="18" /> 下载原文件</button>
      </template>
    </BaseModal>

    <ConfirmDialog :open="Boolean(documentToDelete)" title="删除这份文档？" description="原文件、索引和向量数据都会被清理，此操作无法撤销。" :detail="documentToDelete?.filename" :busy="deleting" @cancel="documentToDelete = null" @confirm="confirmDelete" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PhArrowClockwise as ArrowClockwise, PhCaretLeft as CaretLeft, PhCaretRight as CaretRight, PhCheckCircle as CheckCircle, PhCloudArrowUp as CloudArrowUp, PhCopy as Copy, PhDotsThree as DotsThree, PhDownloadSimple as DownloadSimple, PhFilePdf as FilePdf, PhFileSearch as FileSearch, PhFiles as Files, PhFileText as FileText, PhHardDrives as HardDrives, PhMagnifyingGlass as MagnifyingGlass, PhMarkdownLogo as MarkdownLogo, PhStack as Stack, PhTrash as Trash, PhUploadSimple as UploadSimple, PhWarningCircle as WarningCircle, PhX as X } from '@phosphor-icons/vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'
import type { DocumentRecord, DocumentScope, DocumentStatusFilter } from '../types/api'
import PageHeader from '../components/layout/PageHeader.vue'
import BaseModal from '../components/feedback/BaseModal.vue'
import ConfirmDialog from '../components/feedback/ConfirmDialog.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

interface UploadQueueItem { id: number; name: string; status: 'queued' | 'done' | 'failed'; message: string }

const MAX_UPLOAD_SIZE_MB = 200
const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

const store = useAppStore()
const fileInput = ref<HTMLInputElement | null>(null)
const uploadScope = ref<DocumentScope>('private')
const dragover = ref(false)
const dragDepth = ref(0)
const uploading = ref(false)
const uploadQueue = ref<UploadQueueItem[]>([])
const search = ref(store.documentsSearch || '')
const scopeFilter = ref<'all' | DocumentScope>(store.documentsScopeFilter || 'all')
const statusFilter = ref<'all' | DocumentStatusFilter>(store.documentsStatusFilter || 'all')
const selectedDocument = ref<DocumentRecord | null>(null)
const documentToDelete = ref<DocumentRecord | null>(null)
const detailLoading = ref(false)
const deleting = ref(false)

const pageDocuments = computed(() => Array.isArray(store.documents) ? store.documents : [])
const indexedCount = computed(() => pageDocuments.value.filter((item) => item.status === 'indexed').length)
const totalChunks = computed(() => pageDocuments.value.reduce((total, item) => total + item.chunk_count, 0))
const totalSize = computed(() => pageDocuments.value.reduce((total, item) => total + item.file_size, 0))
const hasFilters = computed(() => Boolean(search.value.trim()) || scopeFilter.value !== 'all' || statusFilter.value !== 'all')

let searchTimer: number | undefined

watch(search, (value) => {
  store.documentsSearch = value.trim()
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void store.loadDocuments(false, { page: 1 }).catch(() => undefined)
  }, 300)
})

watch([scopeFilter, statusFilter], ([scope, status]) => {
  window.clearTimeout(searchTimer)
  store.documentsScopeFilter = scope === 'all' ? '' : scope
  store.documentsStatusFilter = status === 'all' ? '' : status
  void store.loadDocuments(false, { page: 1 }).catch(() => undefined)
})

onMounted(() => { if (!pageDocuments.value.length) void store.loadDocuments() })
onBeforeUnmount(() => window.clearTimeout(searchTimer))

function openPicker() { if (!uploading.value) fileInput.value?.click() }
function onDragEnter() { dragDepth.value += 1; dragover.value = true }
function onDragLeave() { dragDepth.value = Math.max(0, dragDepth.value - 1); if (!dragDepth.value) dragover.value = false }
function onDrop(event: DragEvent) { dragover.value = false; dragDepth.value = 0; void uploadFiles(Array.from(event.dataTransfer?.files || [])) }
function onFilesSelected(event: Event) { void uploadFiles(Array.from((event.target as HTMLInputElement).files || [])); (event.target as HTMLInputElement).value = '' }
function removeUploadItem(id: number) { uploadQueue.value = uploadQueue.value.filter((item) => item.id !== id) }

async function uploadFiles(files: File[]) {
  if (!files.length || uploading.value) return
  const supported = files.filter((file) => /\.(txt|md|pdf)$/i.test(file.name) && file.size <= MAX_UPLOAD_SIZE_BYTES)
  if (supported.length !== files.length) store.notify('部分文件未加入队列', `仅支持 TXT、Markdown、PDF，且单个文件不能超过 ${MAX_UPLOAD_SIZE_MB} MB。`, 'error')
  if (!supported.length) return
  uploading.value = true
  const queue: UploadQueueItem[] = supported.map((file, index) => ({ id: Date.now() + index, name: file.name, status: 'queued', message: '等待上传' }))
  uploadQueue.value.push(...queue)
  queue.forEach((item) => { item.message = '正在批量发送' })
  try {
    const response = await store.uploadDocuments(supported, uploadScope.value)
    queue.forEach((item, index) => {
      const result = response.results[index]
      if (result?.success && result.document) {
        item.status = 'done'
        item.message = '已创建索引任务'
      } else {
        item.status = 'failed'
        item.message = result?.error_message || '服务未返回该文件的处理结果'
      }
    })
  } catch (error) {
    queue.forEach((item) => {
      item.status = 'failed'
      item.message = error instanceof Error ? error.message : '上传失败'
    })
  } finally {
    uploading.value = false
  }
  window.setTimeout(() => { uploadQueue.value = uploadQueue.value.filter((item) => item.status !== 'done') }, 5000)
}

async function refresh() { await store.loadDocuments().catch(() => undefined) }
async function goToPage(page: number) {
  if (page < 1 || page > store.documentsTotalPages || page === store.documentsPage) return
  await store.loadDocuments(false, { page }).catch(() => undefined)
}
async function changePageSize(event: Event) {
  const pageSize = Number((event.target as HTMLSelectElement).value)
  await store.loadDocuments(false, { page: 1, pageSize }).catch(() => undefined)
}
function isProcessing(status: string) { return ['uploaded', 'queued', 'parsing', 'chunking', 'embedding'].includes(status) }
function taskStatus(document: DocumentRecord) { return store.tasks[document.document_id]?.status || document.status }

async function showDocument(document: DocumentRecord) {
  selectedDocument.value = document
  detailLoading.value = true
  try { selectedDocument.value = await api.getDocument(document.document_id) }
  catch (error) { store.notify('无法获取文档详情', error instanceof Error ? error.message : '', 'error') }
  finally { detailLoading.value = false }
}

async function download(document: DocumentRecord) {
  try { await api.downloadDocument(document.document_id, document.filename) }
  catch (error) { store.notify('下载失败', error instanceof Error ? error.message : '', 'error') }
}

function requestDelete(document: DocumentRecord) { documentToDelete.value = document; selectedDocument.value = null }
async function confirmDelete() {
  if (!documentToDelete.value) return
  deleting.value = true
  try { await store.deleteDocument(documentToDelete.value.document_id); documentToDelete.value = null }
  catch (error) { store.notify('删除失败', error instanceof Error ? error.message : '', 'error') }
  finally { deleting.value = false }
}

async function copyId() {
  if (!selectedDocument.value) return
  await navigator.clipboard.writeText(selectedDocument.value.document_id)
  store.notify('文档 ID 已复制', '', 'success')
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}
function formatDate(value: string) { return new Date(value).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) }
function formatFullDate(value: string) { return new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) }
</script>
