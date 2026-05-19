<template>
  <Badge
    v-if="hasLatency"
    :class="badgeClass"
    class="text-[10px] shrink-0 font-medium whitespace-nowrap inline-flex justify-center w-10"
  >
    {{ displayLatency }}ms
  </Badge>
  <Badge v-else class="text-[10px] shrink-0 font-medium whitespace-nowrap inline-flex justify-center w-10 bg-muted text-muted-foreground">
    -
  </Badge>
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from './ui/badge'

const props = defineProps({
  latency: { type: [Number, String], default: null },
})

const numLatency = computed(() => {
  const v = props.latency
  if (v === null || v === undefined || v === '' || v === '-') return NaN
  const n = Number(v)
  return isNaN(n) ? NaN : n
})

const hasLatency = computed(() => {
  return !isNaN(numLatency.value) && numLatency.value > 0
})

const displayLatency = computed(() => Math.round(numLatency.value))

const badgeClass = computed(() => {
  const val = numLatency.value
  if (isNaN(val) || val <= 0) return ''
  if (val < 200) return 'bg-green-600 text-white dark:bg-green-700'
  if (val < 800) return 'bg-yellow-500 text-black dark:bg-yellow-600 dark:text-white'
  return 'bg-red-600 text-white dark:bg-red-700'
})
</script>
