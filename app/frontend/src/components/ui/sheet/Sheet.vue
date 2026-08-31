<template>
  <Teleport to="body">
    <Transition
      enter-active-class="ease-out duration-300"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" @click="$emit('update:open', false)" />
    </Transition>
    <Transition
      enter-active-class="ease-out duration-300"
      :enter-from-class="side === 'right' ? 'translate-x-full' : '-translate-x-full'"
      enter-to-class="translate-x-0"
      leave-active-class="ease-in duration-200"
      leave-from-class="translate-x-0"
      :leave-to-class="side === 'right' ? 'translate-x-full' : '-translate-x-full'"
    >
      <div
        v-if="open"
        :class="cn(
          'fixed z-50 bg-card shadow-2xl flex flex-col transition-transform',
          side === 'right' && 'right-0 top-0 bottom-0',
          side === 'left' && 'left-0 top-0 bottom-0',
          side === 'top' && 'left-0 right-0 top-0',
          side === 'bottom' && 'left-0 right-0 bottom-0',
        )"
        :style="dimensionStyle"
      >
        <slot />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { cn } from '../../../lib/utils'

const props = defineProps({
  open: { type: Boolean, default: false },
  side: { type: String, default: 'right' },
  width: { type: String, default: '320px' },
  height: { type: String, default: '' },
})
defineEmits(['update:open'])

const dimensionStyle = computed(() => {
  if (props.side === 'right' || props.side === 'left') {
    return { width: props.width }
  }
  if (props.side === 'top' || props.side === 'bottom') {
    return { height: props.height || '400px' }
  }
  return {}
})
</script>
