<template>
  <div v-if="hasError" class="min-h-screen flex items-center justify-center bg-background">
    <Card class="max-w-md w-full mx-4">
      <CardHeader class="text-center">
        <div class="mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
          <AlertTriangle class="h-6 w-6 text-destructive" />
        </div>
        <CardTitle class="text-xl">页面出现错误</CardTitle>
        <CardDescription>
          抱歉，页面遇到了意外错误。您可以尝试刷新页面或返回首页。
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div v-if="errorInfo" class="rounded-lg bg-muted p-3 text-xs font-mono text-muted-foreground overflow-auto max-h-32">
          {{ errorInfo }}
        </div>
        <div class="flex gap-2">
          <Button variant="outline" class="flex-1 gap-2" @click="goHome">
            <Home class="h-4 w-4" />
            返回首页
          </Button>
          <Button class="flex-1 gap-2" @click="reload">
            <RefreshCw class="h-4 w-4" />
            刷新页面
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'
import { AlertTriangle, Home, RefreshCw } from 'lucide-vue-next'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/card'
import { Button } from './ui/button'

const router = useRouter()
const hasError = ref(false)
const errorInfo = ref('')

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorInfo.value = `${err?.message || 'Unknown error'}\n\nComponent: ${instance?.$options?.name || 'unknown'}\nInfo: ${info}`
  console.error('[ErrorBoundary]', err, instance, info)
  return false
})

function goHome() {
  hasError.value = false
  errorInfo.value = ''
  router.push('/')
}

function reload() {
  window.location.reload()
}
</script>
