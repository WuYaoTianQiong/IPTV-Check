<template>
  <div class="space-y-8 py-4">
    <div class="flex flex-col items-center text-center space-y-4">
      <div class="relative w-32 h-32 flex items-center justify-center">
        <svg class="absolute w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" :stroke="'var(--color-secondary)'" stroke-width="6" fill="transparent" />
          <circle
            cx="50" cy="50" r="40"
            :stroke="'var(--color-primary)'"
            stroke-width="6"
            stroke-linecap="round"
            fill="transparent"
            :stroke-dasharray="`${smoothPercent * 2.512} 251.2`"
            class="transition-all duration-500"
          />
        </svg>
        <span class="text-3xl font-extrabold">{{ smoothPercent }}%</span>
      </div>
      <p class="font-semibold text-sm">{{ statusText }}</p>
      <p v-if="checkStore.eta" class="text-xs text-muted-foreground">预计剩余: {{ checkStore.eta }}</p>
    </div>

    <div class="grid grid-cols-4 gap-6 max-w-lg mx-auto">
      <div class="text-center">
        <div class="text-3xl font-bold text-success">{{ checkStore.validCount }}</div>
        <div class="text-sm text-muted-foreground mt-1">有效</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-warning">{{ checkStore.likelyValidCount }}</div>
        <div class="text-sm text-muted-foreground mt-1">疑似有效</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold text-destructive">{{ checkStore.invalidCount }}</div>
        <div class="text-sm text-muted-foreground mt-1">无效</div>
      </div>
      <div class="text-center">
        <div class="text-3xl font-bold">{{ checkStore.checkTotal }}</div>
        <div class="text-sm text-muted-foreground mt-1">总计</div>
      </div>
    </div>

    <div class="max-w-lg mx-auto">
      <Progress :model-value="smoothPercent" class="transition-all duration-300" />
      <div class="flex justify-between mt-2 text-xs text-muted-foreground">
        <span>已检测 {{ checkStore.checkedCount }} / {{ checkStore.checkTotal }}</span>
        <span>有效率 {{ checkStore.validRate }}%</span>
      </div>
    </div>

    <div class="flex flex-col items-center gap-3">
      <div v-if="checkStore.phase === 'completed'" class="flex gap-3">
        <Button @click="router.push('/result')" class="gap-1.5">
          <BarChart3 class="w-3.5 h-3.5" />
          查看检测结果
        </Button>
        <Button variant="outline" size="sm" @click="minimizeToBackground" class="gap-1.5">
          <Minimize2 class="w-3.5 h-3.5" />
          返回源配置
        </Button>
      </div>
      <div v-else class="flex gap-3">
        <Button variant="outline" size="sm" @click="router.push('/result')" class="gap-1.5">
          <ExternalLink class="w-3 h-3" />
          实时查看结果
        </Button>
        <Button variant="outline" size="sm" @click="minimizeToBackground" class="gap-1.5">
          <Minimize2 class="w-3.5 h-3.5" />
          最小化到后台运行
        </Button>
        <Button variant="destructive" size="sm" @click="showStopDialog = true" class="gap-1.5" :disabled="!checkStore.isChecking">
          <Square class="w-3.5 h-3.5" />
          停止检测
        </Button>
      </div>
    </div>

    <AlertDialog v-model:open="showStopDialog">
      <AlertDialogHeader class="text-destructive">
        <AlertTriangle class="w-5 h-5" />
        确定要停止当前检测吗？
      </AlertDialogHeader>
      <AlertDialogDescription>
        停止将强行丢失当前已检测过半的 {{ checkStore.checkedCount }} 个频道进度。
      </AlertDialogDescription>
      <AlertDialogFooter>
        <Button variant="outline" @click="showStopDialog = false">我再等会儿 (取消)</Button>
        <Button variant="destructive" @click="confirmStopCheck">确定强行停止</Button>
      </AlertDialogFooter>
    </AlertDialog>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Minimize2, Square, AlertTriangle, BarChart3, ExternalLink } from 'lucide-vue-next'
import { useCheckStore } from '../stores/check'
import { useToast } from '../composables/useToast'
import { stopCheck, getCheckState } from '../api'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Progress } from '../components/ui/progress'
import { AlertDialog, AlertDialogHeader, AlertDialogDescription, AlertDialogFooter } from '../components/ui/alert-dialog'

const checkStore = useCheckStore()
const router = useRouter()
const { toast } = useToast()
const showStopDialog = ref(false)
const hasShownCompletionToast = ref(false)

const smoothPercent = ref(0)
let animationFrame = null

watch(() => checkStore.progress, (newVal) => {
  if (animationFrame) cancelAnimationFrame(animationFrame)
  const start = smoothPercent.value
  const diff = newVal - start
  const duration = 400
  const startTime = performance.now()
  function step(now) {
    const elapsed = now - startTime
    const t = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - t, 3)
    smoothPercent.value = Math.round(start + diff * eased)
    if (t < 1) animationFrame = requestAnimationFrame(step)
  }
  animationFrame = requestAnimationFrame(step)
})

const statusText = computed(() => {
  if (!checkStore.isChecking) return '准备就绪'
  if (checkStore.stageMessage) return checkStore.stageMessage
  const p = checkStore.progress
  if (p === 0 && checkStore.checkTotal === 0) return '正在加载直播源...'
  if (p < 5) return '正在下载频道列表...'
  if (p < 30) return '正在连接各频道...'
  if (p < 60) return '正在验证流媒体...'
  if (p < 90) return '正在测试分段可用性...'
  if (p < 100) return '正在生成报告...'
  return '检测完成'
})

onMounted(async () => {
  checkStore.startReconciliation()
  if (checkStore.logs.length === 0) {
    try {
      const { data } = await getCheckState()
      if (data.phase === 'checking' || data.is_running) {
        checkStore.isChecking = true
        checkStore.phase = data.phase || 'checking'
        if (data.total) checkStore.checkTotal = data.total
        if (data.checked) checkStore.checkedCount = data.checked
        if (data.valid) checkStore.validCount = data.valid
        if (data.invalid) checkStore.invalidCount = data.invalid
        checkStore.addLog('已恢复检测状态', 'info')
      }
    } catch {}
  }
})

onUnmounted(() => {
  checkStore.stopReconciliation()
})

watch(() => checkStore.phase, (newPhase) => {
  if (newPhase === 'completed' && !hasShownCompletionToast.value) {
    hasShownCompletionToast.value = true
    const total = checkStore.checkTotal
    const valid = checkStore.validCount
    const likelyValid = checkStore.likelyValidCount
    const rate = total ? Math.round((valid / total) * 100) : 0
    
    toast.success(
      '检测完成',
      `共 ${total} 个频道，有效 ${valid}，疑似有效 ${likelyValid}，有效率 ${rate}%`,
      {
        label: '查看检测结果',
        handler: () => router.push('/result')
      }
    )
  }
  if (newPhase === 'checking' || newPhase === 'idle') {
    hasShownCompletionToast.value = false
  }
})

function minimizeToBackground() {
  router.push('/source')
}

async function confirmStopCheck() {
  showStopDialog.value = false
  try {
    await stopCheck()
  } catch (e) {
    console.error(e)
  }
  router.push('/source')
}
</script>
