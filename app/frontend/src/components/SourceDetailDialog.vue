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
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          role="dialog"
          aria-modal="true"
          class="pointer-events-auto w-full max-w-md rounded-xl border bg-card text-card-foreground shadow-2xl overflow-hidden"
        >
          <div class="flex items-start justify-between gap-3 px-5 py-4 border-b">
            <div class="min-w-0">
              <h2 class="font-semibold text-lg leading-tight break-words">{{ source?.name || '源详情' }}</h2>
              <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <Badge>{{ qualityLabel }}</Badge>
                <Badge variant="secondary">{{ source?.category || '未分类' }}</Badge>
                <Badge variant="outline">{{ protocolLabel }}</Badge>
                <Badge v-if="source?.has_epg" variant="outline">EPG</Badge>
                <Badge v-if="source?.has_logo_support" variant="outline">台标</Badge>
              </div>
            </div>
            <button
              class="inline-flex items-center justify-center rounded-md h-8 w-8 shrink-0 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              @click="$emit('update:open', false)"
              aria-label="关闭"
            >
              <X class="h-5 w-5" />
            </button>
          </div>

          <div class="px-5 py-4 space-y-4 max-h-[55vh] overflow-y-auto">
            <div>
              <div class="text-xs font-medium text-muted-foreground mb-1">源地址</div>
              <div class="flex items-start justify-between gap-2">
                <code class="text-xs break-all leading-relaxed">{{ source?.url || '-' }}</code>
                <Button variant="outline" size="sm" class="shrink-0 h-7 px-2 gap-1 text-xs" @click="copy(source?.url)">
                  <Check v-if="copied" class="h-3.5 w-3.5" />
                  <Copy v-else class="h-3.5 w-3.5" />
                  {{ copied ? '已复制' : '复制' }}
                </Button>
              </div>
            </div>

            <div>
              <div class="text-xs font-medium text-muted-foreground mb-1">运营商兼容</div>
              <div class="flex items-center gap-1.5 flex-wrap">
                <Badge :variant="source?.isp_compatible ? 'default' : 'secondary'">{{ source?.isp_compatible ? '兼容' : '不兼容' }}</Badge>
                <span class="text-xs text-muted-foreground">{{ ispLabel }}</span>
              </div>
            </div>

            <div class="grid grid-cols-3 gap-3">
              <div>
                <div class="text-xs font-medium text-muted-foreground mb-1">频道数</div>
                <div class="text-sm font-semibold">{{ source?.channel_count || 0 }}</div>
              </div>
              <div>
                <div class="text-xs font-medium text-muted-foreground mb-1">更新频率</div>
                <div class="text-sm font-semibold">{{ updateFrequencyLabel }}</div>
              </div>
              <div>
                <div class="text-xs font-medium text-muted-foreground mb-1">上次更新</div>
                <div class="text-sm font-semibold">{{ source?.last_updated ? source.last_updated.slice(0, 10) : '-' }}</div>
              </div>
            </div>

            <div v-if="source?.mirror_url">
              <div class="text-xs font-medium text-muted-foreground mb-1">镜像源</div>
              <code class="text-xs break-all leading-relaxed">{{ source.mirror_url }}</code>
            </div>

            <div v-if="source?.epg_url">
              <div class="text-xs font-medium text-muted-foreground mb-1">EPG 地址</div>
              <code class="text-xs break-all leading-relaxed">{{ source.epg_url }}</code>
            </div>

            <div v-if="source?.description">
              <div class="text-xs font-medium text-muted-foreground mb-1">描述</div>
              <p class="text-sm leading-relaxed">{{ source.description }}</p>
            </div>

            <div v-if="source?.features?.length">
              <div class="text-xs font-medium text-muted-foreground mb-1">特性</div>
              <div class="flex gap-1.5 flex-wrap">
                <Badge v-for="f in source.features" :key="f" variant="outline">{{ f }}</Badge>
              </div>
            </div>
          </div>

          <div class="px-5 py-3 border-t flex justify-end gap-2">
            <Button variant="outline" size="sm" @click="$emit('update:open', false)">关闭</Button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { X, Copy, Check } from 'lucide-vue-next'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { useToast } from '../composables/useToast'

const props = defineProps({
  open: { type: Boolean, default: false },
  source: { type: Object, default: null },
})
const emit = defineEmits(['update:open'])
const { toast } = useToast()

const copied = ref(false)
let copyTimer = null

function onKeydown(e) {
  if (e.key === 'Escape' && props.open) {
    emit('update:open', false)
  }
}

watch(() => props.open, (val) => {
  if (val) {
    document.addEventListener('keydown', onKeydown)
  } else {
    copied.value = false
    clearTimeout(copyTimer)
    document.removeEventListener('keydown', onKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})

const PROTOCOL_MAP = { hls: 'HLS', http: 'HTTP', rtmp: 'RTMP', rtsp: 'RTSP', ts: 'TS' }
const QUALITY_MAP = { S: 'S级', A: 'A级', B: 'B级', C: 'C级' }
const FREQ_MAP = { hourly: '每小时', daily: '每天', weekly: '每周', monthly: '每月' }

const protocolLabel = computed(() => PROTOCOL_MAP[props.source?.protocol] || props.source?.protocol || '未知')
const qualityLabel = computed(() => QUALITY_MAP[props.source?.quality_rating] || props.source?.quality_rating || '未知')
const updateFrequencyLabel = computed(() => FREQ_MAP[props.source?.update_frequency] || props.source?.update_frequency || '未知')

// 后端 isp 字段类型不一致（可能为数组/字符串），统一兼容处理
const ispLabel = computed(() => {
  const isp = props.source?.isp
  if (Array.isArray(isp) && isp.length) return isp.join(' / ')
  if (typeof isp === 'string' && isp) return isp
  return '未知'
})

async function copy(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 1500)
    toast.success('已复制', '源地址已复制到剪贴板')
  } catch {
    toast.error('复制失败', '浏览器不支持自动复制')
  }
}
</script>
