<template>
  <AppLayout>
    <RouterView />
  </AppLayout>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'
import { createSSEConnection } from './api'
import AppLayout from './components/layout/AppLayout.vue'

const store = useAppStore()
let sse = null

onMounted(async () => {
  await store.fetchInfo()
  await store.fetchOnlineSources()
  sse = createSSEConnection((msg) => store.handleSSEMessage(msg))
  store.startReconciliation()
})

onUnmounted(() => {
  if (sse) sse.close()
  store.stopReconciliation()
})
</script>
