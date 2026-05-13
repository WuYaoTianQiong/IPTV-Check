<template>
  <div :class="cn('rounded-xl border bg-card text-card-foreground shadow', $attrs.class ?? '')" v-bind="$attrs">
    <slot />
  </div>
</template>

<script setup>
import { cn } from '../../../lib/utils'
</script>
