<template>
  <div class="app-shell">
    <button class="mobile-overlay" :class="{ visible: mobileOpen }" type="button" aria-label="关闭导航" @click="mobileOpen = false"></button>
    <aside class="app-sidebar" :class="{ open: mobileOpen }">
      <RouterLink class="brand" :to="{ name: 'agents' }" @click="mobileOpen = false">
        <span class="brand-mark">M</span>
        <span><strong>M Knowledge</strong><small>Agent Workspace</small></span>
      </RouterLink>

      <nav class="side-navigation" aria-label="主导航">
        <p class="nav-group-label">工作台</p>
        <RouterLink v-for="item in primaryNav" :key="item.name" :to="{ name: item.name }" @click="mobileOpen = false">
          <component :is="item.icon" :size="20" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </RouterLink>

        <p class="nav-group-label manage-label">管理</p>
        <RouterLink v-if="store.isAdmin" :to="{ name: 'admin' }" @click="mobileOpen = false">
          <UsersThree :size="20" aria-hidden="true" />
          <span>用户与密钥</span>
        </RouterLink>
        <RouterLink v-if="store.isAdmin" :to="{ name: 'settings' }" @click="mobileOpen = false">
          <SlidersHorizontal :size="20" aria-hidden="true" />
          <span>配置中心</span>
        </RouterLink>
        <RouterLink :to="{ name: 'system' }" @click="mobileOpen = false">
          <Pulse :size="20" aria-hidden="true" />
          <span>系统状态</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="user-block">
          <span class="user-avatar">{{ userInitial }}</span>
          <span class="user-copy"><strong>{{ store.userDisplayName }}</strong><small>{{ roleLabel }}</small></span>
          <button class="icon-button quiet" type="button" title="断开连接" aria-label="断开连接" @click="disconnect">
            <SignOut :size="19" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>

    <main class="app-main">
      <div class="mobile-topbar">
        <button class="icon-button" type="button" aria-label="打开导航" @click="mobileOpen = true">
          <List :size="22" aria-hidden="true" />
        </button>
        <RouterLink class="mobile-brand" :to="{ name: 'agents' }"><span class="brand-mark small">M</span> M Knowledge</RouterLink>
        <span class="mobile-avatar">{{ userInitial }}</span>
      </div>
      <RouterView />
    </main>

    <nav class="mobile-navigation" aria-label="移动端导航">
      <RouterLink v-for="item in mobileNav" :key="item.name" :to="{ name: item.name }">
        <component :is="item.icon" :size="21" aria-hidden="true" />
        <span>{{ item.shortLabel || item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhBooks as Books, PhChatCircleDots as ChatCircleDots, PhGraph as Graph, PhGridFour as GridFour, PhList as List, PhPulse as Pulse, PhSignOut as SignOut, PhSlidersHorizontal as SlidersHorizontal, PhUsersThree as UsersThree } from '@phosphor-icons/vue'
import { useAppStore } from '../../stores/app'

const store = useAppStore()
const router = useRouter()
const mobileOpen = ref(false)

const primaryNav = [
  { name: 'agents', label: 'Agent 应用', shortLabel: '应用', icon: GridFour },
  { name: 'chat', label: 'Chat Agent', shortLabel: '对话', icon: ChatCircleDots },
  { name: 'multi-agent', label: 'Multi-Agent', shortLabel: '协作', icon: Graph },
  { name: 'knowledge', label: '知识库', shortLabel: '知识', icon: Books },
]
const mobileNav = computed(() => [...primaryNav, { name: 'system', label: '系统状态', shortLabel: '状态', icon: Pulse }])
const userInitial = computed(() => (store.userDisplayName.trim()[0] || 'M').toUpperCase())
const roleLabel = computed(() => store.isAdmin ? '管理员' : '成员')

async function disconnect() {
  store.disconnect()
  mobileOpen.value = false
  await router.replace({ name: 'connect' })
}
</script>
