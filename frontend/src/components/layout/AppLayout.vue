<template>
  <div class="flex h-screen flex-col bg-background">
    <AppHeader />
    <div v-if="!sseConnected" class="flex items-center justify-center gap-2 px-4 py-1.5 text-xs font-medium bg-warning/10 text-warning border-b border-warning/20">
      <Loader2 class="h-3 w-3 animate-spin" />
      <span>连接断开，正在尝试重连...</span>
    </div>
    <main class="flex-1 overflow-auto p-4 lg:p-6 pb-20 lg:pb-6">
      <slot />
    </main>
    <ToastContainer />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import AppHeader from './AppHeader.vue'
import ToastContainer from '../ToastContainer.vue'
import { sseStatus } from '../../api'

const sseConnected = ref(true)
let pollTimer = null

onMounted(() => {
  pollTimer = setInterval(() => {
    sseConnected.value = sseStatus.connected
  }, 1000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>
