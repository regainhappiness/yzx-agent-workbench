<template>
  <div class="page-scroll agent-hub">
    <PageHeader title="Agent 应用" description="从一个入口访问不同能力，知识库和身份在应用之间共享。" />

    <section class="agent-showcase">
      <article v-for="agent in agents" :key="agent.id" class="agent-feature">
        <div class="agent-feature-top">
          <span class="agent-icon"><component :is="agent.icon" :size="30" weight="duotone" aria-hidden="true" /></span>
          <StatusBadge status="active" label="可用" />
        </div>
        <div class="agent-feature-copy">
          <p>当前应用</p>
          <h2>{{ agent.name }}</h2>
          <span>{{ agent.description }}</span>
        </div>
        <div class="agent-capabilities">
          <span v-for="item in agent.capabilities" :key="item"><Check :size="15" weight="bold" aria-hidden="true" />{{ item }}</span>
        </div>
        <RouterLink class="button primary" :to="{ name: agent.routeName }">
          打开应用 <ArrowUpRight :size="18" aria-hidden="true" />
        </RouterLink>
      </article>

      <aside class="workspace-summary">
        <div class="summary-heading">
          <span class="summary-icon"><Database :size="23" weight="duotone" aria-hidden="true" /></span>
          <div><strong>共享知识底座</strong><span>所有 Agent 可按权限使用</span></div>
        </div>
        <dl class="summary-stats">
          <div><dt>知识文档</dt><dd>{{ store.documents.length }}</dd></div>
          <div><dt>已索引</dt><dd>{{ indexedCount }}</dd></div>
          <div><dt>历史会话</dt><dd>{{ store.sessions.length }}</dd></div>
        </dl>
        <RouterLink class="text-link" :to="{ name: 'knowledge' }">管理知识库 <ArrowRight :size="16" aria-hidden="true" /></RouterLink>
      </aside>
    </section>

    <section class="extension-note">
      <div class="extension-mark"><CirclesThreePlus :size="25" aria-hidden="true" /></div>
      <div>
        <h3>为下一个 Agent 留好位置</h3>
        <p>路由、图标、能力说明集中在应用注册表中。新增应用可以复用认证、知识库与系统状态。</p>
      </div>
      <span class="code-label">src/constants/agents.ts</span>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PhArrowRight as ArrowRight, PhArrowUpRight as ArrowUpRight, PhCheck as Check, PhCirclesThreePlus as CirclesThreePlus, PhDatabase as Database } from '@phosphor-icons/vue'
import { agents } from '../constants/agents'
import { useAppStore } from '../stores/app'
import PageHeader from '../components/layout/PageHeader.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

const store = useAppStore()
const indexedCount = computed(() => store.documents.filter((item) => item.status === 'indexed').length)
</script>
