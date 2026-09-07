<template>
  <div class="empty-state" :class="{ compact }">
    <div class="empty-icon"><component :is="icon" :size="compact ? 24 : 30" aria-hidden="true" /></div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(defineProps<{
  icon: Component
  title: string
  description: string
  compact?: boolean
}>(), { compact: false })
</script>

