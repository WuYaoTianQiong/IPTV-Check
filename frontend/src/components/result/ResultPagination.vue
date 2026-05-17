<template>
  <div class="flex items-center justify-between">
    <div class="text-sm text-muted-foreground">第 {{ currentPage }} 页 · 共 {{ totalPages }} 页</div>
    <div class="flex gap-1">
      <Button
        variant="outline"
        size="icon"
        class="h-8 w-8"
        :disabled="currentPage <= 1"
        @click="$emit('change-page', currentPage - 1)"
      >
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <Button
        v-for="p in visiblePages"
        :key="p"
        variant="outline"
        size="sm"
        class="h-8 min-w-[2rem]"
        :class="p === currentPage ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
        @click="$emit('change-page', p)"
      >
        {{ p }}
      </Button>
      <Button
        variant="outline"
        size="icon"
        class="h-8 w-8"
        :disabled="currentPage >= totalPages"
        @click="$emit('change-page', currentPage + 1)"
      >
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { Button } from '../ui/button'

const props = defineProps({
  currentPage: { type: Number, default: 1 },
  totalPages: { type: Number, default: 1 },
})

defineEmits(['change-page'])

const visiblePages = computed(() => {
  const pages = []
  const maxVisible = 7
  let start = Math.max(1, props.currentPage - Math.floor(maxVisible / 2))
  let end = Math.min(props.totalPages, start + maxVisible - 1)
  if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})
</script>
