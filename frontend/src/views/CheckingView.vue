<template>
  <div class="space-y-6 max-w-4xl mx-auto">
    <div class="text-center">
      <h1 class="text-2xl font-bold tracking-tight">检测中</h1>
      <p class="text-muted-foreground mt-1">{{ statusText }}</p>
      <p v-if="checkStore.eta" class="text-xs text-muted-foreground mt-1">
        预计剩余时间: {{ checkStore.eta }}
      </p>
    </div>

    <Card class="overflow-hidden">
      <CardContent class="p-8">
        <div class="flex flex-col items-center">
          <div class="relative w-48 h-48">
            <svg class="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle
                cx="50" cy="50" r="42"
                fill="none"
                stroke="var(--color-secondary)"
                stroke-width="8"
              />
              <circle
                cx="50" cy="50" r="42"
                fill="none"
                stroke="var(--color-primary)"
                stroke-width="8"
                stroke-linecap="round"
                :stroke-dasharray="`${smoothPercent * 2.64} 264`"
                class="transition-all duration-500 ease-out"
              />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="text-4xl font-bold">{{ smoothPercent }}%</span>
              <span class="text-sm text-muted-foreground">完成</span>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-8 mt-8 w-full max-w-md">
            <div class="text-center">
              <div class="text-3xl font-bold text-success">{{ checkStore.validCount }}</div>
              <div class="text-sm text-muted-foreground mt-1">有效</div>
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

          <div class="w-full mt-6">
            <Progress :model-value="smoothPercent" class="transition-all duration-300" />
            <div class="flex justify-between mt-2 text-xs text-muted-foreground">
              <span>已检测 {{ checkStore.checkedCount }} / {{ checkStore.checkTotal }}</span>
              <span>有效率 {{ checkStore.validRate }}%</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-6 lg:grid-cols-3">
      <Card class="lg:col-span-2">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Terminal class="h-5 w-5 text-primary" />
            实时日志
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            ref="logContainer"
            class="h-64 overflow-y-auto rounded-lg bg-muted/50 p-3 font-mono text-xs space-y-1"
          >
            <div
              v-for="log in checkStore.logs"
              :key="log.id"
              :class="cn(
                'px-2 py-1 rounded',
                log.type === 'success' && 'text-success',
                log.type === 'error' && 'text-destructive',
                log.type === 'warning' && 'text-warning',
                log.type === 'info' && 'text-foreground',
              )"
            >
              <span class="text-muted-foreground mr-2">{{ log.time }}</span>
              {{ log.message }}
            </div>
            <div v-if="checkStore.logs.length === 0" class="text-muted-foreground text-center py-8">
              等待检测开始...
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Gauge class="h-5 w-5 text-primary" />
            操作
          </CardTitle>
        </CardHeader>
        <CardContent class="space-y-3">
          <Button
            variant="destructive"
            class="w-full gap-2"
            @click="doStop"
            :disabled="!checkStore.isChecking"
          >
            <Square class="h-4 w-4" />
            停止检测
          </Button>
          <Button
            class="w-full gap-2"
            @click="goResults"
            :disabled="checkStore.checkedCount === 0"
          >
            <BarChart3 class="h-4 w-4" />
            查看结果
            <Badge v-if="checkStore.isChecking" variant="secondary" class="ml-1 text-[10px]">
              检测中
            </Badge>
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Terminal,
  Gauge,
  Square,
  BarChart3,
} from 'lucide-vue-next'
import { useCheckStore } from '../stores/check'
import { useResultStore } from '../stores/result'
import { stopCheck } from '../api'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Progress } from '../components/ui/progress'
import { Badge } from '../components/ui/badge'

const checkStore = useCheckStore()
const resultStore = useResultStore()
const router = useRouter()
const logContainer = ref(null)

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
    if (t < 1) {
      animationFrame = requestAnimationFrame(step)
    }
  }
  animationFrame = requestAnimationFrame(step)
})

const statusText = computed(() => {
  if (!checkStore.isChecking) return '准备就绪'
  const p = checkStore.progress
  if (p === 0 && checkStore.checkTotal === 0) return '正在加载直播源...'
  if (p < 5) return '正在下载频道列表...'
  if (p < 30) return '正在连接各频道...'
  if (p < 60) return '正在验证流媒体...'
  if (p < 90) return '正在测试分段可用性...'
  if (p < 100) return '正在生成报告...'
  return '检测完成'
})

onMounted(() => {
  checkStore.startReconciliation()
})

onUnmounted(() => {
  checkStore.stopReconciliation()
})

watch(() => checkStore.logs.length, () => {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
})

async function doStop() {
  try {
    await stopCheck()
  } catch (e) {
    console.error(e)
  }
}

function goResults() {
  router.push('/result')
  resultStore.fetchResults()
}
</script>
