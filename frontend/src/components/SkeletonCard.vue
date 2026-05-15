<template>
  <div class="space-y-3">
    <div
      v-for="i in rows"
      :key="i"
      class="rounded-lg bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 dark:from-gray-700 dark:via-gray-600 dark:to-gray-700 animate-pulse"
      :style="{ height: itemHeight + 'px' }"
    />
    <p v-if="showText" class="text-xs text-center text-muted-foreground mt-2">
      {{ loadingText }}
    </p>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 5 },
  itemHeight: { type: Number, default: 48 },
  showText: { type: Boolean, default: true },
  loadingText: { type: String, default: '加载中...' },
})
</script>
