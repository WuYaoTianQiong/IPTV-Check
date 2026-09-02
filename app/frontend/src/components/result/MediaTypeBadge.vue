<script setup>
import { Radio, Tv } from 'lucide-vue-next'
import { Badge } from '../ui/badge'

defineProps({
  isRadio: { type: Boolean, default: false },
})
</script>

<template>
  <Badge
    variant="outline"
    :class="[
      'shrink-0 h-4 px-1.5 py-0 text-[10px] gap-1',
      isRadio
        ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-400'
        : 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-500/40 dark:bg-sky-500/10 dark:text-sky-400',
    ]"
  >
    <Radio v-if="isRadio" class="h-3 w-3" />
    <Tv v-else class="h-3 w-3" />
    {{ isRadio ? '电台' : '电视' }}
  </Badge>
</template>
