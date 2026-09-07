<template>
  <main class="connect-page">
    <section class="connect-intro">
      <RouterLink class="brand connect-brand" :to="{ name: 'connect' }">
        <span class="brand-mark">M</span>
        <span><strong>M Knowledge</strong><small>Agent Workspace</small></span>
      </RouterLink>

      <div class="connect-copy">
        <span class="connect-kicker">从单点能力，到统一协作</span>
        <h1>一个工作台，连接每个 Agent。</h1>
        <p>统一管理 Agent 应用、知识库、对话与成员权限，并持续接入新的智能能力。</p>
      </div>

      <div class="connect-features" aria-label="工作台能力">
        <div><ChatsCircle :size="22" aria-hidden="true" /><span><strong>Agent 应用</strong><small>一个入口使用不同智能能力</small></span></div>
        <div><Books :size="22" aria-hidden="true" /><span><strong>知识中枢</strong><small>让可信资料服务每个 Agent</small></span></div>
        <div><StackPlus :size="22" aria-hidden="true" /><span><strong>持续扩展</strong><small>按注册机制接入更多 Agent</small></span></div>
      </div>
    </section>

    <section class="connect-form-wrap">
      <form class="connect-card" @submit.prevent="submit">
        <div class="connect-form-heading">
          <div class="form-icon"><Key :size="24" weight="duotone" aria-hidden="true" /></div>
          <h2>连接工作台</h2>
          <p>使用服务地址和 API Key 验证身份，进入统一的 Agent 工作台。</p>
        </div>

        <div class="field-group">
          <label for="api-base">API 地址</label>
          <input id="api-base" v-model.trim="base" type="text" autocomplete="url" placeholder="http://127.0.0.1:8000/api/v1" required />
          <small>本地开发可直接使用 <code>/api/v1</code></small>
        </div>

        <div class="field-group">
          <label for="api-key">API Key</label>
          <div class="input-with-action">
            <input id="api-key" v-model.trim="key" :type="showKey ? 'text' : 'password'" autocomplete="current-password" placeholder="sk-..." required />
            <button type="button" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey">
              <EyeSlash v-if="showKey" :size="19" aria-hidden="true" />
              <Eye v-else :size="19" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div v-if="error" class="inline-alert is-error" role="alert">
          <WarningCircle :size="19" weight="fill" aria-hidden="true" />
          <span>{{ error }}</span>
        </div>

        <button class="button primary connect-submit" type="submit" :disabled="store.connecting || !base || !key">
          <span>{{ store.connecting ? '正在验证' : '进入工作台' }}</span>
          <span v-if="store.connecting" class="button-loader" aria-hidden="true"></span>
          <ArrowRight v-else :size="19" aria-hidden="true" />
        </button>

        <p class="connect-security"><LockKey :size="15" aria-hidden="true" /> API Key 仅保存在当前浏览器。</p>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowRight as ArrowRight, PhBooks as Books, PhChatsCircle as ChatsCircle, PhEye as Eye, PhEyeSlash as EyeSlash, PhKey as Key, PhLockKey as LockKey, PhStackPlus as StackPlus, PhWarningCircle as WarningCircle } from '@phosphor-icons/vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const base = ref(store.apiBase)
const key = ref(store.apiKey)
const showKey = ref(false)
const error = ref(store.connectionError)

async function submit() {
  error.value = ''
  try {
    await store.connect(base.value, key.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/apps'
    await router.replace(redirect)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '连接失败，请检查配置。'
  }
}
</script>
