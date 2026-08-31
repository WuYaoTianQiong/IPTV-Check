<template>
  <div v-if="hasError" class="min-h-screen flex items-center justify-center bg-background">
    <div class="max-w-md w-full mx-4 rounded-lg border bg-card text-card-foreground shadow-sm">
      <div class="flex flex-col space-y-1.5 p-6 text-center">
        <div class="mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-destructive"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>
        </div>
        <h3 class="text-xl font-semibold leading-none tracking-tight">页面出现错误</h3>
        <p class="text-sm text-muted-foreground">
          抱歉，页面遇到了意外错误。您可以尝试刷新页面。
        </p>
      </div>
      <div class="p-6 pt-0 space-y-4">
        <div v-if="errorInfo" class="rounded-lg bg-muted p-3 text-xs font-mono text-muted-foreground overflow-auto max-h-32">
          {{ errorInfo }}
        </div>
        <div class="flex gap-2">
          <button class="flex-1 inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2" @click="reload">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
            刷新页面
          </button>
        </div>
      </div>
    </div>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'

const hasError = ref(false)
const errorInfo = ref('')

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorInfo.value = `${err?.message || 'Unknown error'}\n\nInfo: ${info}`
  console.error('[ErrorBoundary]', err, instance, info)
  return false
})

function reload() {
  window.location.reload()
}
</script>
