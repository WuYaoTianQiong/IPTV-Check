<template>
  <div class="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
    <div
      class="h-full bg-primary transition-all duration-300 ease-out"
      :style="{ width: `${Math.min(100, Math.max(0, modelValue))}%` }"
    />
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: Number, default: 0 },
})
</script>
