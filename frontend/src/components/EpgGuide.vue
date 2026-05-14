<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold">{{ channelName }} · 节目单</h3>
      <Button variant="ghost" size="sm" @click="$emit('close')">
        <X class="h-4 w-4" />
      </Button>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-8">
      <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="!epgData || !epgData.programs || epgData.programs.length === 0" class="text-center text-muted-foreground py-6 text-sm">
      暂无节目信息
    </div>

    <div v-else class="space-y-1 max-h-[400px] overflow-y-auto">
      <div
        v-for="prog in epgData.programs"
        :key="prog.start"
        class="flex items-start gap-3 px-2 py-1.5 rounded-md text-sm transition-colors"
        :class="prog.is_current ? 'bg-primary/10 border border-primary/20' : 'hover:bg-accent'"
      >
        <div class="flex-shrink-0 w-20 text-muted-foreground text-xs font-mono pt-0.5">
          {{ formatTime(prog.start) }}-{{ formatTime(prog.stop) }}
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium truncate" :class="prog.is_current ? 'text-primary' : ''">
            {{ prog.title }}
            <Badge v-if="prog.is_current" variant="default" class="ml-1.5 text-[10px] px-1">正在播放</Badge>
          </div>
          <div v-if="prog.desc" class="text-muted-foreground text-xs mt-0.5 truncate">
            {{ prog.desc }}
          </div>
        </div>
        <div class="flex-shrink-0 text-muted-foreground text-xs">
          {{ prog.duration_minutes }}分钟
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getChannelEpg } from '../api'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { X, Loader2 } from 'lucide-vue-next'

const props = defineProps({
  channelName: { type: String, required: true },
  tvgId: { type: String, default: '' },
  tvgName: { type: String, default: '' },
  sourceId: { type: String, default: '' },
})

defineEmits(['close'])

const loading = ref(true)
const epgData = ref(null)

function formatTime(xmltvTime) {
  if (!xmltvTime) return ''
  const clean = xmltvTime.split('+')[0].split(' ')[0]
  if (clean.length >= 12) {
    return `${clean.slice(8, 10)}:${clean.slice(10, 12)}`
  }
  return ''
}

async function loadEpg() {
  loading.value = true
  try {
    const { data } = await getChannelEpg(props.channelName, {
      tvg_id: props.tvgId,
      tvg_name: props.tvgName,
      source_id: props.sourceId,
    })
    epgData.value = data.epg
  } catch {
    epgData.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadEpg)
</script>
