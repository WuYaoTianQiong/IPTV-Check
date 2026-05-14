<template>
  <div
    :class="cn(
      'shrink-0 bg-border',
      orientation === 'horizontal' ? 'h-[1px] w-full' : 'h-full w-[1px]',
      $attrs.class ?? ''
    )"
    v-bind="$attrs"
  />
</template>

<script setup>
import { cn } from '../../../lib/utils'

defineProps({
  orientation: { type: String, default: 'horizontal' },
})
</script>
