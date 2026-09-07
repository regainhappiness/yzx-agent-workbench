<template>
  <RouterView />
  <ToastViewport />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from './stores/app'
import ToastViewport from './components/feedback/ToastViewport.vue'

const store = useAppStore()
const router = useRouter()

function handleUnauthorized() {
  store.markDisconnected('API Key 已失效，请重新连接。')
  void router.replace({ name: 'connect' })
}

onMounted(async () => {
  window.addEventListener('mka:unauthorized', handleUnauthorized)
  if (store.apiKey && !store.connected) {
    try {
      await store.bootstrap()
    } catch {
      if (router.currentRoute.value.meta.requiresAuth) {
        await router.replace({ name: 'connect' })
      }
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('mka:unauthorized', handleUnauthorized)
})
</script>
