<template>
  <AppLayout>
    <SourceView v-if="store.activeView === 'source'" />
    <CheckingView v-else-if="store.activeView === 'checking'" />
    <ResultView v-else-if="store.activeView === 'result'" />
    <ReportView v-else-if="store.activeView === 'report'" />
    <TrendView v-else-if="store.activeView === 'trend'" />
    <ToolboxView v-else-if="store.activeView === 'toolbox'" />
  </AppLayout>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'
import { createWebSocket } from './api'
import AppLayout from './components/layout/AppLayout.vue'
import SourceView from './views/SourceView.vue'
import CheckingView from './views/CheckingView.vue'
import ResultView from './views/ResultView.vue'
import ReportView from './views/ReportView.vue'
import TrendView from './views/TrendView.vue'
import ToolboxView from './views/ToolboxView.vue'

const store = useAppStore()
let ws = null

onMounted(async () => {
  await store.fetchInfo()
  await store.fetchOnlineSources()
  ws = createWebSocket((msg) => store.handleWsMessage(msg))
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>
