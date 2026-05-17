<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'
import { createSSEConnection, setToastHandler } from './api'
import AppLayout from './components/layout/AppLayout.vue'

const store = useAppStore()
let sse = null

setToastHandler((message, type) => {
  store.showToast?.(message, type)
})

onMounted(async () => {
  await store.fetchInfo()
  sse = createSSEConnection((msg) => store.handleSSEMessage(msg))
  store.startReconciliation()

  if (store.localIsp === '检测中...' || store.localIsp === '未知') {
    setTimeout(() => {
      if (store.localIsp === '检测中...' || store.localIsp === '未知') {
        store.doRefreshIsp()
      }
    }, 10000)
  }
})

onUnmounted(() => {
  if (sse) sse.close()
  store.stopReconciliation()
})
</script>
