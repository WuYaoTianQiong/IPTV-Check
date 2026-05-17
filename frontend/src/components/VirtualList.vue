<template>
  <div ref="containerRef" class="virtual-list-container" @scroll.passive="onScroll">
    <div :style="{ height: totalHeight + 'px', position: 'relative' }">
      <div :style="{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${offsetY}px)` }">
        <template v-for="src in visibleItems" :key="src.id">
          <div
            :class="cn(
              'source-item flex items-center gap-2 rounded-md px-2.5 py-1.5 cursor-pointer transition-colors',
              selectedIds.includes(src.id)
                ? 'bg-primary/10 border border-primary/20'
                : 'hover:bg-accent border border-transparent',
              !src.isp_compatible && src.category !== '国际电视' && src.category !== '广播电台' && 'opacity-50'
            )"
            @click="toggleOnline(src.id)"
          >
            <Checkbox
              :model-value="selectedIds.includes(src.id)"
              @update:model-value="toggleOnline(src.id)"
              @click.stop
              class="shrink-0"
            />
            <span class="text-sm font-medium truncate flex-1 min-w-0">{{ src.name || '未知频道' }}</span>
            <Badge v-if="src.protocol && src.protocol !== 'unknown'" variant="outline" class="text-[10px] px-1 py-0 h-4 shrink-0">{{ src.protocol }}</Badge>
            <Badge v-if="shouldShowQuality(src.quality_rating)" :variant="src.quality_rating === 'S' ? 'default' : 'outline'" class="text-[10px] px-1 py-0 h-4 shrink-0">{{ src.quality_rating }}</Badge>
            <Badge v-if="!src.isp_compatible && src.category !== '国际电视' && src.category !== '广播电台'" variant="destructive" class="text-[10px] shrink-0">不兼容</Badge>
            <Badge v-else-if="src.isp_compatible" variant="secondary" class="text-[10px] shrink-0">推荐</Badge>
            <button class="text-[10px] text-muted-foreground hover:text-primary shrink-0" @click.stop="onToggleExpand(src.id)">
              {{ expandedId === src.id ? '收起' : '详情' }}
            </button>
          </div>
          <div v-if="expandedId === src.id" class="text-xs text-muted-foreground px-3 pb-2 space-y-1 border-t pt-2 mt-1 bg-accent/30 rounded-b-md">
            <div class="flex gap-1"><span class="font-medium shrink-0">URL:</span><span class="truncate">{{ src.url }}</span></div>
            <div class="flex gap-1"><span class="font-medium shrink-0">分类:</span><span>{{ src.category }}</span></div>
            <div v-if="src.epg_url" class="flex gap-1"><span class="font-medium shrink-0">EPG:</span><span class="truncate">{{ src.epg_url }}</span></div>
            <div v-if="src.channel_count" class="flex gap-1"><span class="font-medium shrink-0">频道数:</span><span>{{ src.channel_count }}</span></div>
            <div v-if="src.description" class="flex gap-1"><span class="font-medium shrink-0">描述:</span><span>{{ src.description }}</span></div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { Checkbox } from './ui/checkbox'
import { Badge } from './ui/badge'
import { cn } from '../lib/utils'

const EXPANDED_DETAIL_HEIGHT = 80

const props = defineProps({
  items: { type: Array, default: () => [] },
  itemHeight: { type: Number, default: 36 },
  visibleCount: { type: Number, default: 14 },
  selectedIds: { type: Array, default: () => [] },
  expandedId: { type: String, default: null },
})

const emit = defineEmits(['toggle-online', 'toggle-expand'])

const containerRef = ref(null)
const scrollTop = ref(0)

const totalHeight = computed(() => {
  const base = props.items.length * props.itemHeight
  if (props.expandedId && props.items.some(s => s.id === props.expandedId)) {
    return base + EXPANDED_DETAIL_HEIGHT
  }
  return base
})

const startIndex = computed(() => {
  const raw = Math.floor(scrollTop.value / props.itemHeight)
  return Math.max(0, raw - 2)
})

const visibleItems = computed(() => {
  const start = startIndex.value
  const end = Math.min(start + props.visibleCount + 4, props.items.length)
  return props.items.slice(start, end)
})

const offsetY = computed(() => startIndex.value * props.itemHeight)

function onScroll() {
  if (containerRef.value) {
    scrollTop.value = containerRef.value.scrollTop
  }
}

function shouldShowQuality(rating) {
  return rating && rating !== 'A' && rating !== 'C'
}

function toggleOnline(id) {
  emit('toggle-online', id)
}

function onToggleExpand(id) {
  emit('toggle-expand', id)
}

onMounted(() => {
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = 0
    }
  })
})
</script>

<style scoped>
.virtual-list-container {
  overflow-y: auto;
  overflow-x: hidden;
  max-height: 480px;
  padding-right: 4px;
}

.source-item {
  height: 36px;
  box-sizing: border-box;
}
</style>
