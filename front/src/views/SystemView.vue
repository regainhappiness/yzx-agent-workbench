<template>
  <div class="page-scroll system-page">
    <PageHeader title="系统状态" description="检查核心依赖、当前身份和前后端连接配置。">
      <template #actions>
        <a class="button secondary" :href="api.docsUrl()" target="_blank" rel="noreferrer"><BookOpenText :size="18" /> API 文档 <ArrowUpRight :size="15" /></a>
        <button class="button primary" type="button" :disabled="checking" @click="checkAll"><ArrowClockwise :size="18" :class="{ spinning: checking }" /> 重新检查</button>
      </template>
    </PageHeader>

    <section class="health-banner" :class="overallHealthy ? 'is-healthy' : 'is-partial'">
      <div class="health-banner-icon"><CheckCircle v-if="overallHealthy" :size="28" weight="fill" /><WarningCircle v-else :size="28" weight="fill" /></div>
      <div><h2>{{ overallHealthy ? '核心服务运行正常' : '部分能力尚未配置' }}</h2><p>{{ overallHealthy ? 'Agent 编排、检索和知识索引均已就绪。' : '基础对话仍可使用，未配置的依赖会限制 RAG 或文档索引。' }}</p></div>
      <span v-if="lastChecked">检查于 {{ lastChecked }}</span>
    </section>

    <div class="system-grid">
      <section class="content-section health-section">
        <div class="section-title with-padding"><h2>服务依赖</h2><span>来自 /health/ready</span></div>
        <div class="health-list">
          <div v-for="service in services" :key="service.key" class="health-row">
            <span class="health-service-icon"><component :is="service.icon" :size="21" /></span>
            <span><strong>{{ service.label }}</strong><small>{{ service.description }}</small></span>
            <StatusBadge :status="service.status" show-dot />
          </div>
        </div>
      </section>

      <section class="content-section connection-section">
        <div class="section-title with-padding"><h2>当前连接</h2><span>本浏览器</span></div>
        <dl class="connection-list">
          <div><dt>用户</dt><dd>{{ store.identity?.name }}</dd></div>
          <div><dt>角色</dt><dd>{{ store.isAdmin ? '管理员' : '成员' }}</dd></div>
          <div><dt>API 地址</dt><dd><code>{{ store.apiBase }}</code></dd></div>
          <div><dt>API Key</dt><dd><code>{{ store.apiKeyMasked }}</code></dd></div>
          <div><dt>存活检查</dt><dd><StatusBadge :status="liveStatus" /></dd></div>
        </dl>
        <button class="button secondary connection-edit" type="button" @click="settingsOpen = true"><SlidersHorizontal :size="18" /> 修改连接</button>
      </section>
    </div>

    <section class="content-section resource-section">
      <div class="section-title with-padding"><h2>工作区数据</h2><span>当前用户可见范围</span></div>
      <div class="resource-grid">
        <RouterLink :to="{ name: 'chat' }"><ChatsCircle :size="24" /><span><strong>{{ store.sessions.length }}</strong><small>历史会话</small></span><CaretRight :size="18" /></RouterLink>
        <RouterLink :to="{ name: 'knowledge' }"><Files :size="24" /><span><strong>{{ store.documentsTotal }}</strong><small>知识文档</small></span><CaretRight :size="18" /></RouterLink>
        <div><Fingerprint :size="24" /><span><strong>{{ store.identity?.user_id.slice(0, 8) }}</strong><small>用户标识</small></span></div>
      </div>
    </section>

    <BaseModal :open="settingsOpen" title="连接设置" description="保存后会立即使用新配置重新验证身份。" width="520px" @close="settingsOpen = false">
      <form id="connection-settings" class="stack-form" @submit.prevent="saveSettings">
        <div class="field-group"><label for="settings-base">API 地址</label><input id="settings-base" v-model.trim="settingsBase" required /></div>
        <div class="field-group"><label for="settings-key">API Key</label><input id="settings-key" v-model.trim="settingsKey" type="password" required /></div>
        <div v-if="settingsError" class="inline-alert is-error"><WarningCircle :size="18" /><span>{{ settingsError }}</span></div>
      </form>
      <template #footer><button class="button secondary" type="button" @click="settingsOpen = false">取消</button><button class="button primary" type="submit" form="connection-settings" :disabled="savingSettings">{{ savingSettings ? '正在验证' : '保存并连接' }}</button></template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { PhArrowClockwise as ArrowClockwise, PhArrowUpRight as ArrowUpRight, PhBookOpenText as BookOpenText, PhCaretRight as CaretRight, PhChatsCircle as ChatsCircle, PhCheckCircle as CheckCircle, PhCpu as Cpu, PhDatabase as Database, PhFiles as Files, PhFingerprint as Fingerprint, PhGraph as Graph, PhMagnifyingGlass as MagnifyingGlass, PhSlidersHorizontal as SlidersHorizontal, PhWarningCircle as WarningCircle } from '@phosphor-icons/vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'
import PageHeader from '../components/layout/PageHeader.vue'
import BaseModal from '../components/feedback/BaseModal.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

const store = useAppStore()
const checking = ref(false)
const liveStatus = ref('unknown')
const lastChecked = ref('')
const settingsOpen = ref(false)
const settingsBase = ref(store.apiBase)
const settingsKey = ref(store.apiKey)
const settingsError = ref('')
const savingSettings = ref(false)

const services = computed(() => {
  const checks = store.health?.checks
  return [
    { key: 'chat_agent', label: 'Chat Agent', description: '语言模型与 Agent 执行器', status: checks?.chat_agent || 'unknown', icon: Cpu },
    { key: 'multi_agent', label: 'Multi-Agent', description: 'Plan-and-Solve 规划与协作执行', status: checks?.multi_agent || 'unknown', icon: Graph },
    { key: 'embedding', label: 'Embedding', description: '文档和查询向量化', status: checks?.embedding || 'unknown', icon: MagnifyingGlass },
    { key: 'milvus', label: 'Milvus', description: '向量数据存储与搜索', status: checks?.milvus || 'unknown', icon: Database },
    { key: 'retrieval', label: 'Retrieval', description: 'RAG 检索增强服务', status: checks?.retrieval || 'unknown', icon: Files },
  ]
})
const overallHealthy = computed(() => liveStatus.value === 'ok' && services.value.every((service) => service.status === 'ok'))

onMounted(checkAll)

async function checkAll() {
  checking.value = true
  const [live, ready] = await Promise.allSettled([api.healthLive(), store.refreshHealth()])
  liveStatus.value = live.status === 'fulfilled' ? live.value.status : 'error'
  if (ready.status === 'rejected') store.notify('就绪检查失败', ready.reason instanceof Error ? ready.reason.message : '', 'error')
  lastChecked.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  checking.value = false
}

async function saveSettings() {
  savingSettings.value = true
  settingsError.value = ''
  try {
    await store.connect(settingsBase.value, settingsKey.value)
    settingsOpen.value = false
    await checkAll()
  } catch (error) { settingsError.value = error instanceof Error ? error.message : '连接失败' }
  finally { savingSettings.value = false }
}
</script>
