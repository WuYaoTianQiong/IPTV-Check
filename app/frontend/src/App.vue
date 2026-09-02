<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app'
import { useCheckStore } from './stores/check'
import { createSSEConnection, setToastHandler, getCheckState } from './api'
import AppLayout from './components/layout/AppLayout.vue'
import { prefetchAllRoutes } from './router'

const store = useAppStore()
const checkStore = useCheckStore()
let sse = null

setToastHandler((message, type) => {
  store.showToast?.(message, type)
})

async function handleSSEReconnect() {
  try {
    const { data } = await getCheckState()
    if (data.is_running || data.phase === 'checking') {
      checkStore.isChecking = true
      checkStore.phase = data.phase || 'checking'
      if (data.total) checkStore.checkTotal = data.total
      if (data.checked) checkStore.checkedCount = data.checked
      if (data.valid) checkStore.validCount = data.valid
      if (data.likely_valid) checkStore.likelyValidCount = data.likely_valid
      if (data.invalid) checkStore.invalidCount = data.invalid
      if (data.stage) checkStore.stage = data.stage
      if (data.stage_message) checkStore.stageMessage = data.stage_message
      checkStore.addLog('SSE重连后已同步服务端状态', 'info')
    }
  } catch {}
}

onMounted(() => {
  // 先建立 SSE 再拉基础信息：避免 /api/info 慢时整页横幅"连接断开"刷屏，
  // 且 local_isp 可通过 SSE 的 isp_updated 事件及时更新
  sse = createSSEConnection((msg) => store.handleSSEMessage(msg), handleSSEReconnect)
  store.startReconciliation()
  store.fetchInfo().catch(() => {})

  // 后台预热懒加载页签 chunk（不阻塞首屏），消除检测初期切页签的下载卡顿
  prefetchAllRoutes()

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
