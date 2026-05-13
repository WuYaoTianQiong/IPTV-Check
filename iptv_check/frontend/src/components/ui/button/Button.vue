<template>
  <component
    :is="as"
    :class="cn(buttonVariants({ variant, size }), $attrs.class ?? '')"
    v-bind="$attrs"
  >
    <slot />
  </component>
</template>

<script setup>
import { cn } from '../../../lib/utils'
import { buttonVariants } from './index'

defineProps({
  variant: { type: String, default: 'default' },
  size: { type: String, default: 'default' },
  as: { type: String, default: 'button' },
})
</script>
