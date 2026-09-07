<template>
  <div class="page-scroll admin-page">
    <PageHeader title="用户与 API Key" description="创建成员、分配角色，并管理调用服务所需的访问凭证。">
      <template #actions>
        <button class="button secondary" type="button" :disabled="loading" @click="loadUsers"><ArrowClockwise :size="18" :class="{ spinning: loading }" /> 刷新</button>
        <button class="button primary" type="button" @click="createOpen = true"><UserPlus :size="18" weight="bold" /> 创建用户</button>
      </template>
    </PageHeader>

    <div v-if="!store.isAdmin" class="access-denied">
      <ShieldWarning :size="34" weight="duotone" /><h2>需要管理员权限</h2><p>当前 API Key 不能访问用户与密钥管理。</p><RouterLink class="button secondary" :to="{ name: 'agents' }">返回应用</RouterLink>
    </div>

    <template v-else>
      <section class="admin-summary">
        <div><UsersThree :size="23" /><span><strong>{{ users.length }}</strong><small>全部用户</small></span></div>
        <div><ShieldCheck :size="23" /><span><strong>{{ adminCount }}</strong><small>管理员</small></span></div>
        <div><Key :size="23" /><span><strong>{{ activeKeyCount }}</strong><small>已加载有效 Key</small></span></div>
      </section>

      <section class="content-section user-section">
        <div class="section-toolbar">
          <div class="section-title"><h2>用户列表</h2><span>点击管理访问凭证</span></div>
          <label class="search-field wide"><MagnifyingGlass :size="17" /><input v-model="search" type="search" placeholder="搜索用户名或 ID" aria-label="搜索用户" /></label>
        </div>
        <div v-if="loading" class="document-skeleton"><span v-for="index in 5" :key="index"></span></div>
        <EmptyState v-else-if="!filteredUsers.length" :icon="UserCircleDashed" :title="users.length ? '没有匹配的用户' : '还没有用户'" description="创建用户后即可生成独立的 API Key。" />
        <div v-else class="user-grid">
          <article v-for="user in filteredUsers" :key="user.user_id" class="user-card">
            <div class="user-card-main">
              <span class="user-avatar card-avatar">{{ user.name.trim()[0]?.toUpperCase() || 'U' }}</span>
              <span><strong>{{ user.name }}</strong><small>{{ user.user_id }}</small></span>
            </div>
            <div class="user-card-meta"><StatusBadge :status="user.role === 'admin' ? 'shared' : 'private'" :label="user.role === 'admin' ? '管理员' : '成员'" /><span>{{ formatDate(user.created_at) }} 创建</span></div>
            <div class="user-card-actions">
              <button class="button secondary compact" type="button" @click="manageUser(user)"><Key :size="17" /> 管理密钥</button>
              <button class="icon-button quiet danger-icon" type="button" :aria-label="`删除用户 ${user.name}`" @click="userToDelete = user"><Trash :size="18" /></button>
            </div>
          </article>
        </div>
      </section>
    </template>

    <BaseModal :open="createOpen" title="创建用户" description="用户创建后仍需生成 API Key 才能连接工作台。" width="480px" @close="createOpen = false">
      <form id="create-user-form" class="stack-form" @submit.prevent="createUser">
        <div class="field-group"><label for="new-user-name">显示名称</label><input id="new-user-name" v-model.trim="newUserName" maxlength="100" placeholder="例如：知识运营团队" required /></div>
        <div class="field-group"><label for="new-user-role">角色</label><select id="new-user-role" v-model="newUserRole"><option value="user">成员，可使用对话和私有知识库</option><option value="admin">管理员，可管理用户和共享知识</option></select></div>
      </form>
      <template #footer><button class="button secondary" type="button" @click="createOpen = false">取消</button><button class="button primary" type="submit" form="create-user-form" :disabled="creating || !newUserName">{{ creating ? '正在创建' : '创建用户' }}</button></template>
    </BaseModal>

    <BaseModal :open="Boolean(managedUser)" title="访问凭证" :description="managedUser?.name" width="620px" @close="managedUser = null">
      <div v-if="managedUser" class="key-management">
        <div class="managed-user-row"><span class="user-avatar card-avatar">{{ managedUser.name[0]?.toUpperCase() }}</span><div><strong>{{ managedUser.name }}</strong><code>{{ managedUser.user_id }}</code></div><StatusBadge :status="managedUser.role === 'admin' ? 'shared' : 'private'" :label="managedUser.role === 'admin' ? '管理员' : '成员'" /></div>
        <div class="key-section-head"><h3>API Keys</h3><button class="button secondary compact" type="button" :disabled="creatingKey" @click="createKey"><Plus :size="16" weight="bold" /> 生成新 Key</button></div>
        <div v-if="keysLoading" class="key-skeleton"><span v-for="index in 3" :key="index"></span></div>
        <EmptyState v-else-if="!managedKeys.length" :icon="Key" title="没有 API Key" description="生成后完整 Key 只会显示一次。" compact />
        <div v-else class="key-list">
          <div v-for="item in managedKeys" :key="item.prefix" class="key-item">
            <span class="key-glyph"><Key :size="18" /></span><span><code>{{ item.prefix }}</code><small>{{ formatFullDate(item.created_at) }}</small></span><StatusBadge :status="item.revoked_at ? 'revoked' : 'active'" />
            <button v-if="!item.revoked_at" class="text-button danger-text" type="button" @click="keyToRevoke = item">撤销</button>
          </div>
        </div>
      </div>
    </BaseModal>

    <BaseModal :open="Boolean(createdKey)" title="复制新的 API Key" description="离开此窗口后将无法再次查看完整 Key。" width="540px" @close="closeCreatedKey">
      <div class="created-key-box"><code>{{ createdKey?.key }}</code><button class="button secondary compact" type="button" @click="copyCreatedKey"><Check v-if="keyCopied" :size="17" /><Copy v-else :size="17" />{{ keyCopied ? '已复制' : '复制' }}</button></div>
      <div class="inline-alert is-warning"><WarningCircle :size="19" weight="fill" /><span>请立即保存到安全的位置，不要通过聊天或邮件发送。</span></div>
      <template #footer><button class="button primary" type="button" @click="closeCreatedKey">我已安全保存</button></template>
    </BaseModal>

    <ConfirmDialog :open="Boolean(userToDelete)" title="删除这个用户？" description="该用户的所有 API Key 会同步撤销。" :detail="userToDelete?.name" :busy="deletingUser" @cancel="userToDelete = null" @confirm="deleteUser" />
    <ConfirmDialog :open="Boolean(keyToRevoke)" title="撤销这个 API Key？" description="使用该 Key 的客户端会立即失去访问权限。" :detail="keyToRevoke?.prefix" confirm-label="确认撤销" :busy="revokingKey" @cancel="keyToRevoke = null" @confirm="revokeKey" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { PhArrowClockwise as ArrowClockwise, PhCheck as Check, PhCopy as Copy, PhKey as Key, PhMagnifyingGlass as MagnifyingGlass, PhPlus as Plus, PhShieldCheck as ShieldCheck, PhShieldWarning as ShieldWarning, PhTrash as Trash, PhUserCircleDashed as UserCircleDashed, PhUserPlus as UserPlus, PhUsersThree as UsersThree, PhWarningCircle as WarningCircle } from '@phosphor-icons/vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'
import type { ApiKeyInfo, CreatedApiKey, User } from '../types/api'
import PageHeader from '../components/layout/PageHeader.vue'
import BaseModal from '../components/feedback/BaseModal.vue'
import ConfirmDialog from '../components/feedback/ConfirmDialog.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'

const store = useAppStore()
const users = ref<User[]>([])
const keyCache = reactive<Record<string, ApiKeyInfo[]>>({})
const loading = ref(false)
const search = ref('')
const createOpen = ref(false)
const creating = ref(false)
const newUserName = ref('')
const newUserRole = ref<'user' | 'admin'>('user')
const managedUser = ref<User | null>(null)
const managedKeys = ref<ApiKeyInfo[]>([])
const keysLoading = ref(false)
const creatingKey = ref(false)
const createdKey = ref<CreatedApiKey | null>(null)
const keyCopied = ref(false)
const userToDelete = ref<User | null>(null)
const deletingUser = ref(false)
const keyToRevoke = ref<ApiKeyInfo | null>(null)
const revokingKey = ref(false)

const filteredUsers = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return keyword ? users.value.filter((user) => `${user.name} ${user.user_id}`.toLowerCase().includes(keyword)) : users.value
})
const adminCount = computed(() => users.value.filter((user) => user.role === 'admin').length)
const activeKeyCount = computed(() => Object.values(keyCache).flat().filter((item) => !item.revoked_at).length)

onMounted(() => { if (store.isAdmin) void loadUsers() })

async function loadUsers() {
  loading.value = true
  try { users.value = await api.listUsers() }
  catch (error) { store.notify('用户列表加载失败', error instanceof Error ? error.message : '', 'error') }
  finally { loading.value = false }
}

async function createUser() {
  creating.value = true
  try {
    const user = await api.createUser(newUserName.value, newUserRole.value)
    users.value.unshift(user)
    createOpen.value = false
    newUserName.value = ''
    newUserRole.value = 'user'
    store.notify('用户已创建', user.name, 'success')
  } catch (error) { store.notify('创建失败', error instanceof Error ? error.message : '', 'error') }
  finally { creating.value = false }
}

async function manageUser(user: User) {
  managedUser.value = user
  keysLoading.value = true
  try {
    const [detail, keys] = await Promise.all([api.getUser(user.user_id), api.listUserKeys(user.user_id)])
    managedUser.value = detail
    managedKeys.value = keys
    keyCache[user.user_id] = keys
  } catch (error) { store.notify('访问凭证加载失败', error instanceof Error ? error.message : '', 'error') }
  finally { keysLoading.value = false }
}

async function createKey() {
  if (!managedUser.value) return
  creatingKey.value = true
  try {
    createdKey.value = await api.createApiKey(managedUser.value.user_id)
    await reloadManagedKeys()
  } catch (error) { store.notify('生成 Key 失败', error instanceof Error ? error.message : '', 'error') }
  finally { creatingKey.value = false }
}

async function reloadManagedKeys() {
  if (!managedUser.value) return
  managedKeys.value = await api.listUserKeys(managedUser.value.user_id)
  keyCache[managedUser.value.user_id] = managedKeys.value
}

async function copyCreatedKey() {
  if (!createdKey.value) return
  await navigator.clipboard.writeText(createdKey.value.key)
  keyCopied.value = true
  window.setTimeout(() => { keyCopied.value = false }, 1800)
}

function closeCreatedKey() { createdKey.value = null; keyCopied.value = false }

async function deleteUser() {
  if (!userToDelete.value) return
  deletingUser.value = true
  try {
    await api.deleteUser(userToDelete.value.user_id)
    users.value = users.value.filter((item) => item.user_id !== userToDelete.value?.user_id)
    userToDelete.value = null
    store.notify('用户已删除', '', 'success')
  } catch (error) { store.notify('删除失败', error instanceof Error ? error.message : '', 'error') }
  finally { deletingUser.value = false }
}

async function revokeKey() {
  if (!keyToRevoke.value) return
  revokingKey.value = true
  try {
    await api.revokeApiKey(keyToRevoke.value.prefix)
    keyToRevoke.value = null
    await reloadManagedKeys()
    store.notify('API Key 已撤销', '', 'success')
  } catch (error) { store.notify('撤销失败', error instanceof Error ? error.message : '', 'error') }
  finally { revokingKey.value = false }
}

function formatDate(value: string) { return new Date(value).toLocaleDateString('zh-CN') }
function formatFullDate(value: string) { return new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) }
</script>
