<template>
  <p :class="cn('text-sm text-muted-foreground', $attrs.class ?? '')" v-bind="$attrs">
    <slot />
  </p>
</template>

<script setup>
import { cn } from '../../../lib/utils'
</script>
