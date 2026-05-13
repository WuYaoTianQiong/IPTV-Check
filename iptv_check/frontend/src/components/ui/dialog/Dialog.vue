<template>
  <Teleport to="body">
    <Transition
      enter-active-class="ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" @click="$emit('update:open', false)" />
    </Transition>
    <Transition
      enter-active-class="ease-out duration-200"
      enter-from-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
      enter-to-class="opacity-100 translate-y-0 sm:scale-100"
      leave-active-class="ease-in duration-150"
      leave-from-class="opacity-100 translate-y-0 sm:scale-100"
      leave-to-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
    >
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          class="pointer-events-auto relative w-full max-w-lg rounded-xl border bg-card text-card-foreground shadow-lg"
          :class="$attrs.class ?? ''"
          v-bind="$attrs"
        >
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
})
defineEmits(['update:open'])
</script>
