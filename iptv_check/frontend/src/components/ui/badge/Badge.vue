<template>
  <div :class="cn(badgeVariants({ variant }), $attrs.class ?? '')" v-bind="$attrs">
    <slot />
  </div>
</template>

<script setup>
import { cn } from '../../../lib/utils'
import { badgeVariants } from './index'

defineProps({
  variant: { type: String, default: 'default' },
})
</script>
