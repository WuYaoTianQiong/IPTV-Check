<template>
  <div class="flex items-center gap-4">
    <input
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      @input="$emit('update:modelValue', Number($event.target.value))"
      class="flex-1 h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
    />
    <span class="text-sm font-medium w-12 text-right">{{ modelValue }}</span>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  step: { type: Number, default: 1 },
})
defineEmits(['update:modelValue'])
</script>
