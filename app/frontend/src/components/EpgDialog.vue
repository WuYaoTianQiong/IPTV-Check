<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle class="flex items-center gap-2">
        <Tv class="h-5 w-5 text-primary" />
        节目单 · {{ epg?.display_name || channelName || '加载中...' }}
        <Badge v-if="epg" variant="secondary" class="text-[10px]">{{ epg.program_count }} 条节目</Badge>
      </DialogTitle>
    </DialogHeader>
    <div class="p-6 pt-0 space-y-3">
      <div v-if="loading" class="text-sm text-muted-foreground py-8 text-center">加载节目单中...</div>
      <div v-else-if="error" class="text-sm text-destructive py-8 text-center">{{ error }}</div>
      <div v-else-if="!epg" class="text-sm text-muted-foreground py-8 text-center">未匹配到该频道的节目单数据</div>
      <template v-else>
        <div v-if="epg.current" class="rounded-lg border border-primary/30 bg-primary/5 p-3">
          <div class="text-xs text-primary font-medium mb-1">正在播出</div>
          <div class="text-sm font-semibold">{{ epg.current.title }}</div>
          <div v-if="epg.current.desc" class="text-xs text-muted-foreground mt-1 line-clamp-2">{{ epg.current.desc }}</div>
        </div>
        <div v-if="epg.programs.length === 0" class="text-sm text-muted-foreground py-6 text-center">暂无节目数据</div>
        <div v-else class="max-h-[50vh] overflow-y-auto space-y-1.5 pr-1">
          <div
            v-for="(p, idx) in epg.programs" :key="idx"
            class="rounded-lg border px-3 py-2"
            :class="p.is_current ? 'border-primary/40 bg-primary/5' : 'border-border'"
          >
            <div class="flex items-center gap-2 text-xs">
              <span class="font-medium shrink-0">{{ formatTime(p.start) }} ~ {{ formatTime(p.stop) }}</span>
              <span v-if="p.category" class="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{{ p.category }}</span>
              <Badge v-if="p.is_current" class="text-[10px] shrink-0">当前</Badge>
            </div>
            <div class="text-sm font-medium mt-1">{{ p.title }}</div>
            <div v-if="p.desc" class="text-xs text-muted-foreground mt-0.5 line-clamp-2">{{ p.desc }}</div>
          </div>
        </div>
      </template>
    </div>
    <DialogFooter>
      <Button variant="outline" @click="$emit('update:open', false)">关闭</Button>
    </DialogFooter>
  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Tv } from 'lucide-vue-next'
import { getChannelEpg } from '../api'
import { Dialog, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

const props = defineProps({
  open: { type: Boolean, default: false },
  channelName: { type: String, default: '' },
})

defineEmits(['update:open'])

const epg = ref(null)
const loading = ref(false)
const error = ref('')

watch(() => [props.open, props.channelName], async ([open, name]) => {
  if (!open || !name) return
  epg.value = null
  error.value = ''
  loading.value = true
  try {
    const { data } = await getChannelEpg(name)
    epg.value = data.epg || null
    if (!data.epg) error.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
  }
})

function formatTime(xmltvTime) {
  if (!xmltvTime || xmltvTime.length < 14) return xmltvTime || ''
  const y = xmltvTime.slice(0, 4)
  const mo = xmltvTime.slice(4, 6)
  const d = xmltvTime.slice(6, 8)
  const h = xmltvTime.slice(8, 10)
  const mi = xmltvTime.slice(10, 12)
  return `${y}-${mo}-${d} ${h}:${mi}`
}
</script>
