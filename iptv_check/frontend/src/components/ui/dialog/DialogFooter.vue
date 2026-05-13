<template>
  <div :class="cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-2 p-6 pt-0', $attrs.class ?? '')" v-bind="$attrs">
    <slot />
  </div>
</template>

<script setup>
import { cn } from '../../../lib/utils'
</script>
