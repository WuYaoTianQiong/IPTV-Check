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
      <div v-if="open" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" @click="$emit('update:open', false)" />
    </Transition>
    <Transition
      enter-active-class="ease-out duration-200"
      enter-from-class="opacity-0 translate-y-4 sm:scale-95"
      enter-to-class="opacity-100 translate-y-0 sm:scale-100"
      leave-active-class="ease-in duration-150"
      leave-from-class="opacity-100 translate-y-0 sm:scale-100"
      leave-to-class="opacity-0 translate-y-4 sm:scale-95"
    >
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 pointer-events-none">
        <div
          role="dialog"
          aria-modal="true"
          class="pointer-events-auto flex w-full max-w-2xl h-[80vh] max-h-[680px] flex-col rounded-2xl border bg-card text-card-foreground shadow-2xl overflow-hidden"
        >
          <div class="flex items-start justify-between gap-3 px-5 py-4 border-b shrink-0">
            <div class="min-w-0">
              <h2 class="text-lg font-semibold leading-tight truncate">{{ category }}</h2>
              <p class="text-xs text-muted-foreground mt-0.5">共 {{ sources.length }} 个源 · 点击条目查看详情，勾选后用于检测</p>
            </div>
            <button
              class="inline-flex items-center justify-center rounded-md h-8 w-8 shrink-0 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              @click="$emit('update:open', false)"
              aria-label="关闭"
            >
              <X class="h-5 w-5" />
            </button>
          </div>

          <div class="flex-1 min-h-0 px-5 py-3 overflow-hidden">
            <div v-if="sources.length === 0" class="h-full flex items-center justify-center text-sm text-muted-foreground">
              该分类暂无源
            </div>
            <VirtualList
              v-else
              :items="sources"
              :item-height="36"
              :visible-count="16"
              :selected-ids="sourceStore.selectedOnlineIds"
              :max-height="'100%'"
              @toggle-online="sourceStore.toggleOnline"
              @toggle-detail="showDetail"
            />
          </div>

          <div class="px-5 py-3 border-t shrink-0 flex flex-wrap items-center justify-between gap-3">
            <div class="text-sm">
              <span class="font-semibold">本分类已选 {{ selectedInCategory.length }}</span>
              <span class="text-muted-foreground ml-1">/ 全部已选 {{ sourceStore.selectedOnlineIds.length }} 个源</span>
            </div>
            <div class="flex items-center gap-2">
              <Button variant="outline" size="sm" @click="sourceStore.selectCategory(category)">全选本分类</Button>
              <Button variant="outline" size="sm" :disabled="compatibleCount === 0" @click="sourceStore.selectCompatibleInCategory(category)">仅运营商兼容 ({{ compatibleCount }})</Button>
              <Button variant="ghost" size="sm" @click="sourceStore.clearCategory(category)" :disabled="selectedInCategory.length === 0">清空本分类</Button>
              <Button size="sm" @click="$emit('update:open', false)">确定</Button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <SourceDetailDialog v-model:open="showDetailDialog" :source="detailSource" />
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { X } from 'lucide-vue-next'
import { useSourceStore } from '../stores/source'
import { Button } from './ui/button'
import VirtualList from './VirtualList.vue'
import SourceDetailDialog from './SourceDetailDialog.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  category: { type: String, default: '' },
})
const emit = defineEmits(['update:open'])
const sourceStore = useSourceStore()

const detailSource = ref(null)
const showDetailDialog = ref(false)

const sources = computed(() => {
  if (!props.category) return []
  return sourceStore.onlineSources.filter(s => !s.disabled && s.category === props.category)
})

const selectedInCategory = computed(() => {
  return sources.value.filter(s => sourceStore.selectedIdSet.has(s.id))
})

const compatibleCount = computed(() => {
  return sources.value.filter(s => s.isp_compatible).length
})

function showDetail(id) {
  detailSource.value = sources.value.find(s => s.id === id) || null
  if (detailSource.value) showDetailDialog.value = true
}

// ESC：优先关闭详情弹窗，再次按 ESC 才关闭本分类弹窗
function onKeydown(e) {
  if (e.key === 'Escape' && props.open && !showDetailDialog.value) {
    emit('update:open', false)
  }
}

watch(() => props.open, (val) => {
  if (val) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>
