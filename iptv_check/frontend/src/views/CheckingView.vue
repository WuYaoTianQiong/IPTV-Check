<template>
  <div class="space-y-6 max-w-4xl mx-auto">
    <div class="text-center">
      <h1 class="text-2xl font-bold tracking-tight">检测中</h1>
      <p class="text-muted-foreground mt-1">{{ currentStatus }}</p>
    </div>

    <Card class="overflow-hidden">
      <CardContent class="p-8">
        <div class="flex flex-col items-center">
          <div class="relative w-48 h-48">
            <svg class="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle
                cx="50" cy="50" r="42"
                fill="none"
                stroke="hsl(var(--color-secondary))"
                stroke-width="8"
              />
              <circle
                cx="50" cy="50" r="42"
                fill="none"
                stroke="hsl(var(--color-primary))"
                stroke-width="8"
                stroke-linecap="round"
                :stroke-dasharray="`${store.progress * 2.64} 264`"
                class="transition-all duration-500 ease-out"
              />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="text-4xl font-bold">{{ store.progress }}%</span>
              <span class="text-sm text-muted-foreground">完成</span>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-8 mt-8 w-full max-w-md">
            <div class="text-center">
              <div class="text-3xl font-bold text-success">{{ store.validCount }}</div>
              <div class="text-sm text-muted-foreground mt-1">有效</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-destructive">{{ store.invalidCount }}</div>
              <div class="text-sm text-muted-foreground mt-1">无效</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold">{{ store.checkTotal }}</div>
              <div class="text-sm text-muted-foreground mt-1">总计</div>
            </div>
          </div>

          <div class="w-full mt-6">
            <Progress :model-value="store.progress" />
            <div class="flex justify-between mt-2 text-xs text-muted-foreground">
              <span>已检测 {{ store.checkedCount }} / {{ store.checkTotal }}</span>
              <span>有效率 {{ store.validRate }}%</span>
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
              v-for="log in store.logs"
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
            <div v-if="store.logs.length === 0" class="text-muted-foreground text-center py-8">
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
            :disabled="!store.isChecking"
          >
            <Square class="h-4 w-4" />
            停止检测
          </Button>
          <Button
            class="w-full gap-2"
            @click="goResults"
            :disabled="store.isChecking && store.checkedCount === 0"
          >
            <BarChart3 class="h-4 w-4" />
            查看结果
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import {
  Terminal,
  Gauge,
  Square,
  BarChart3,
} from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { stopCheck } from '../api'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Progress } from '../components/ui/progress'

const store = useAppStore()
const logContainer = ref(null)

watch(() => store.logs.length, () => {
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
  store.activeView = 'result'
  store.fetchResults()
}
</script>
