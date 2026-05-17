<template>
  <button
    type="button"
    role="checkbox"
    :aria-checked="modelValue"
    :class="cn(
      'peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      'disabled:cursor-not-allowed disabled:opacity-50',
      modelValue && 'bg-primary text-primary-foreground',
    )"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <Transition
      enter-active-class="ease-out duration-150"
      enter-from-class="opacity-0 scale-50"
      enter-to-class="opacity-100 scale-100"
    >
      <svg v-if="modelValue" class="h-3 w-3 mx-auto" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2 6l3 3 5-5" />
      </svg>
    </Transition>
  </button>
</template>

<script setup>
import { cn } from '../../../lib/utils'

defineProps({
  modelValue: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>
