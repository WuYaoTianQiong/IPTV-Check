<template>
  <div class="flex flex-col sm:flex-row items-center justify-between gap-3 py-1">
    <!-- 左侧：每页条数 + 统计 -->
    <div class="flex items-center gap-2 text-sm text-muted-foreground">
      <span class="whitespace-nowrap">每页</span>
      <select
        :value="perPage"
        class="h-8 rounded-md border border-input bg-background px-2 text-sm"
        @change="$emit('update:perPage', Number($event.target.value))"
      >
        <option v-for="opt in perPageOptions" :key="opt" :value="opt">{{ opt }}</option>
      </select>
      <span class="whitespace-nowrap">条 · 共 {{ total }} 条</span>
    </div>

    <!-- 右侧：分页按钮 -->
    <div class="flex items-center gap-1">
      <!-- 上一页 -->
      <Button
        variant="outline"
        size="icon"
        class="h-8 w-8"
        :disabled="currentPage <= 1"
        @click="$emit('update:currentPage', currentPage - 1)"
      >
        <ChevronLeft class="h-4 w-4" />
      </Button>

      <!-- 页码 -->
      <template v-for="(p, idx) in pages" :key="idx">
        <span v-if="p === '...'" class="px-1 text-muted-foreground select-none">…</span>
        <Button
          v-else
          variant="outline"
          size="sm"
          class="h-8 min-w-[2rem]"
          :class="p === currentPage ? 'bg-primary text-primary-foreground hover:bg-primary/90 border-primary shadow-sm' : ''"
          @click="$emit('update:currentPage', p)"
        >
          {{ p }}
        </Button>
      </template>

      <!-- 下一页 -->
      <Button
        variant="outline"
        size="icon"
        class="h-8 w-8"
        :disabled="currentPage >= totalPages"
        @click="$emit('update:currentPage', currentPage + 1)"
      >
        <ChevronRight class="h-4 w-4" />
      </Button>

      <!-- 跳页 -->
      <div class="flex items-center gap-1 ml-3">
        <span class="text-xs text-muted-foreground whitespace-nowrap">跳至</span>
        <Input
          v-model.number="jumpInput"
          type="number"
          :min="1"
          :max="totalPages"
          class="h-8 w-16 text-xs text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          placeholder=""
          @keyup.enter="handleJump"
          @blur="handleJump"
        />
        <span class="text-xs text-muted-foreground whitespace-nowrap">页</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

const props = defineProps({
  currentPage: { type: Number, default: 1 },
  totalPages: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  perPage: { type: Number, default: 50 },
  perPageOptions: { type: Array, default: () => [10, 20, 30, 50, 100] },
})

const emit = defineEmits(['update:currentPage', 'update:perPage'])

const jumpInput = ref('')

const pages = computed(() => {
  const total = props.totalPages
  const current = props.currentPage
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const result = []
  // 始终显示第一页
  result.push(1)

  if (current > 3) {
    result.push('...')
  }

  // 当前页附近
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  if (start > 2) {
    // 已经在上面加了省略号
  }
  for (let i = start; i <= end; i++) {
    result.push(i)
  }

  if (current < total - 2) {
    result.push('...')
  }

  // 始终显示最后一页
  if (total > 1) {
    result.push(total)
  }

  return result
})

function handleJump() {
  const page = parseInt(jumpInput.value, 10)
  if (isNaN(page) || page < 1) {
    jumpInput.value = ''
    return
  }
  const clamped = Math.min(page, props.totalPages)
  emit('update:currentPage', clamped)
  jumpInput.value = ''
}
</script>
