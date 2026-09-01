<template>
  <div ref="containerRef" class="virtual-list-container" :style="{ maxHeight }" @scroll.passive="onScroll">
    <div :style="{ height: totalHeight + 'px', position: 'relative' }">
      <div class="channel-columns" :style="channelColumnsStyle">
        <div v-for="src in visibleItems" :key="src.id" class="channel-item">
          <div
            :class="cn(
              'source-item flex items-center gap-2 rounded-md px-2.5 py-1.5 cursor-pointer transition-colors overflow-hidden',
              selectedSet.has(src.id)
                ? 'bg-primary/10 border border-primary/20'
                : 'hover:bg-accent border border-transparent',
              !src.isp_compatible && src.category !== '国际电视' && src.category !== '广播电台' && 'opacity-50'
            )"
            @click="onToggleDetail(src.id)"
          >
            <Checkbox
              :model-value="selectedSet.has(src.id)"
              @update:model-value="onToggleOnline(src.id)"
              @click.stop
              class="shrink-0"
            />
            <span class="text-sm font-medium truncate flex-1 min-w-0">{{ src.name || '未知频道' }}</span>
            <Badge v-if="src.protocol && src.protocol !== 'unknown'" variant="outline" class="text-[10px] px-1 py-0 h-4 shrink-0">{{ src.protocol }}</Badge>
            <Badge v-if="shouldShowQuality(src.quality_rating)" :variant="src.quality_rating === 'S' ? 'default' : 'outline'" class="text-[10px] px-1 py-0 h-4 shrink-0">{{ src.quality_rating }}</Badge>
            <Badge v-if="!src.isp_compatible && src.category !== '国际电视' && src.category !== '广播电台'" variant="destructive" class="text-[10px] shrink-0">不兼容</Badge>
            <Badge v-else-if="src.isp_compatible" variant="secondary" class="text-[10px] shrink-0">推荐</Badge>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { Checkbox } from './ui/checkbox'
import { Badge } from './ui/badge'
import { cn } from '../lib/utils'

const props = defineProps({
  items: { type: Array, default: () => [] },
  itemHeight: { type: Number, default: 36 },
  visibleCount: { type: Number, default: 14 },
  selectedIds: { type: Array, default: () => [] },
  maxHeight: { type: String, default: '480px' },
})

const emit = defineEmits(['toggle-online', 'toggle-detail'])

const containerRef = ref(null)
const scrollTop = ref(0)
const columnCount = ref(1)

// Set 化选中项查找，避免 selectedIds 数组（可达数万项）上的 includes O(n) 卡顿
const selectedSet = computed(() => new Set(props.selectedIds))

function updateColumnCount() {
  if (containerRef.value) {
    const width = containerRef.value.clientWidth
    // 更窄也双列：≥400px 即可双列；再窄单列，保证源名称不被 badge 挤没
    columnCount.value = width >= 400 ? 2 : 1
  }
}

const totalHeight = computed(() => {
  return Math.ceil(props.items.length / columnCount.value) * props.itemHeight
})

const startRowIndex = computed(() => {
  const raw = Math.floor(scrollTop.value / props.itemHeight)
  return Math.max(0, raw - 2)
})

const visibleItems = computed(() => {
  const startRow = startRowIndex.value
  const endRow = Math.min(startRow + props.visibleCount + 4, Math.ceil(props.items.length / columnCount.value))
  const startItem = startRow * columnCount.value
  const endItem = Math.min(endRow * columnCount.value, props.items.length)
  return props.items.slice(startItem, endItem)
})

const offsetY = computed(() => {
  return startRowIndex.value * props.itemHeight
})

const channelColumnsStyle = computed(() => ({
  position: 'absolute',
  top: 0,
  left: 0,
  right: 0,
  transform: `translateY(${offsetY.value}px)`,
  // 列数由 JS 的 columnCount 动态控制，避免硬编码 column-count 与响应式计算不一致，
  // 导致源项被压缩、名称文字塌陷为 0 宽
  columnCount: columnCount.value,
}))

function onScroll() {
  if (containerRef.value) {
    scrollTop.value = containerRef.value.scrollTop
  }
}

function shouldShowQuality(rating) {
  return rating && rating !== 'A' && rating !== 'C'
}

function onToggleOnline(id) {
  emit('toggle-online', id)
}

function onToggleDetail(id) {
  emit('toggle-detail', id)
}

onMounted(() => {
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = 0
    }
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
})
</script>

<style scoped>
.virtual-list-container {
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.source-item {
  height: 36px;
  box-sizing: border-box;
}

.channel-columns {
  column-gap: 0.5rem;
}

.channel-item {
  break-inside: avoid;
  margin-bottom: 0;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}
</style>
