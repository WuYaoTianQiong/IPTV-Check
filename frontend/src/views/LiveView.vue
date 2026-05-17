<template>
  <div class="flex flex-col lg:flex-row gap-6 items-stretch h-[calc(100vh-8rem)] min-h-[480px]">
    <aside
      :class="cn(
        'bg-card border rounded-xl p-4 flex flex-col shadow-sm transition-all duration-300',
        immersiveMode ? 'lg:w-0 lg:p-0 overflow-hidden' : 'w-full lg:w-72',
      )"
    >
      <div class="relative mb-3 flex-shrink-0">
        <Search class="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
        <Input v-model="searchQuery" placeholder="快速过滤频道..." class="pl-9 text-xs" />
      </div>
      <div class="flex items-center justify-between pb-3 mb-2 border-b border-border flex-shrink-0">
        <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">频道分组列表</span>
        <label class="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <Checkbox v-model="showFavoritesOnly" />
          仅看收藏
        </label>
      </div>
      <ScrollArea class="flex-1">
        <div class="space-y-1.5 pr-1 text-sm">
          <div v-if="loading" class="space-y-2 py-4">
            <div v-for="i in 6" :key="i" class="h-8 rounded-lg bg-muted animate-pulse" />
          </div>
          <div v-else-if="groups.length === 0" class="text-center py-8 text-muted-foreground text-sm">
            <Tv class="h-12 w-12 mx-auto mb-3 opacity-40" />
            <p>还没有有效频道</p>
            <Button size="sm" class="mt-3" @click="router.push('/source')">去选源检测</Button>
          </div>
          <template v-else>
            <div v-for="group in filteredGroups" :key="group.name" class="mb-1">
              <button
                class="w-full flex items-center justify-between px-2 py-1 text-xs font-bold text-muted-foreground"
                @click="toggleGroup(group.name)"
              >
                <span class="flex items-center gap-1">
                  <component :is="expandedGroups.has(group.name) ? ChevronDown : ChevronRight" class="w-3 h-3" />
                  📺 {{ group.name }}
                </span>
                <span class="text-[10px]">{{ group.channels.length }}</span>
              </button>
              <div v-show="expandedGroups.has(group.name)" class="mt-1 space-y-0.5 pl-2">
                <button
                  v-for="ch in group.channels" :key="ch.url"
                  class="w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between group/ch transition"
                  :class="currentChannel?.url === ch.url ? 'bg-primary/10 text-primary font-semibold' : 'text-foreground hover:bg-accent'"
                  @click="changeChannel(ch)"
                >
                  <span class="flex items-center gap-2">
                    <span :class="cn('w-1.5 h-1.5 rounded-full', ch.is_valid !== false ? 'bg-success' : 'bg-destructive')" />
                    <span class="truncate">{{ ch.name }}</span>
                  </span>
                  <Play class="w-3 h-3 opacity-0 group-hover/ch:opacity-40 transition-opacity" />
                </button>
              </div>
            </div>
          </template>
        </div>
      </ScrollArea>
    </aside>

    <div class="flex-1 bg-slate-950 rounded-xl relative overflow-hidden flex flex-col shadow-lg border border-slate-800">
      <div class="h-14 bg-slate-900/80 backdrop-blur-md px-4 flex justify-between items-center text-white border-b border-white/5 z-10 flex-shrink-0">
        <div class="flex items-center gap-3">
          <h4 class="font-bold text-sm tracking-wide">{{ currentChannel?.name || '选择频道开始观看' }}</h4>
          <span v-if="currentChannel" class="text-[10px] px-2 py-0.5 rounded bg-white/10 text-slate-300 font-mono">
            {{ currentChannel.group || '' }} · {{ currentChannel.latency || '-' }}ms
          </span>
        </div>
        <div class="flex items-center gap-2">
          <select
            v-if="history.length > 0"
            v-model="selectedSessionId"
            class="rounded border bg-slate-800/80 text-white/90 px-2 py-1 text-xs max-w-[180px]"
            @change="onSessionChange"
          >
            <option value="" disabled>📋 历史记录</option>
            <option
              v-for="h in history"
              :key="h.session_id"
              :value="h.session_id"
            >
              {{ formatHistoryLabel(h) }}
            </option>
          </select>
          <Button variant="ghost" size="sm" class="bg-white/10 hover:bg-white/20 text-white text-xs gap-1.5" @click="epgOpen = true">
            <ListVideo class="w-3.5 h-3.5" />
            查看节目单 (EPG)
          </Button>
          <Button
            :class="cn('text-xs gap-1.5 shadow-sm', immersiveMode ? 'bg-slate-800 hover:bg-slate-700' : 'bg-primary hover:bg-primary/90')"
            size="sm"
            @click="toggleImmersiveMode"
          >
            <Maximize2 class="w-3.5 h-3.5" />
            {{ immersiveMode ? '常规模式' : '沉浸模式' }}
          </Button>
        </div>
      </div>

      <div class="flex-1 relative flex items-center justify-center bg-black group">
        <Transition
          enter-active-class="ease-out duration-200"
          enter-from-class="opacity-0"
          enter-to-class="opacity-100"
          leave-active-class="ease-in duration-150"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div v-if="showSkeleton" class="absolute inset-0 bg-slate-950/90 z-20 flex flex-col items-center justify-center space-y-6">
            <div class="flex flex-col items-center space-y-2">
              <div class="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
              <span class="text-xs text-slate-400 font-medium">正在秒级建立切台信道连接...</span>
            </div>
            <div class="w-full max-w-md px-6 py-4 border border-white/5 bg-white/[0.02] rounded-xl space-y-2.5 animate-pulse">
              <div class="h-4 bg-white/10 rounded w-1/3" />
              <div class="h-3 bg-white/5 rounded w-3/4" />
              <div class="h-3 bg-white/5 rounded w-1/2" />
            </div>
          </div>
        </Transition>

        <div v-if="groups.length === 0" class="text-center text-white/50">
          <Tv class="h-16 w-16 mx-auto mb-4 opacity-30" />
          <p class="text-lg">频道列表为空</p>
          <p class="text-sm mt-1 opacity-70">请先去源配置页执行检测</p>
        </div>

        <div v-else-if="!iframeCreated" class="text-center space-y-2 select-none">
          <div class="w-16 h-16 rounded-full bg-white/10 text-white flex items-center justify-center mx-auto shadow-2xl backdrop-blur border border-white/10 cursor-pointer hover:scale-105 transition-transform" @click="currentChannel && playChannel(currentChannel)">
            <PlayCircle class="w-8 h-8 fill-white/10" />
          </div>
          <span class="text-xs text-slate-500 font-mono block">M3U8 HLS 直播流拉取成功 · 1080P 60FPS</span>
        </div>

        <iframe
          v-if="iframeCreated"
          ref="playerIframe"
          :src="iframeSrc"
          class="w-full h-full border-0 absolute inset-0"
          allow="autoplay; encrypted-media; fullscreen"
          allowfullscreen
        />

        <Transition
          enter-active-class="ease-out duration-200"
          enter-from-class="opacity-0"
          enter-to-class="opacity-100"
          leave-active-class="ease-in duration-150"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div v-if="immersiveMode && !showSkeleton" class="absolute bottom-4 left-4 text-[11px] text-white/30 pointer-events-none">
            💡 沉浸模式已开启，鼠标移动至最左侧可临时拉出频道树。
          </div>
        </Transition>
      </div>
    </div>

    <Sheet v-model:open="epgOpen" side="right" width="320px">
      <SheetHeader>
        <h5 class="font-bold text-sm flex items-center gap-1.5">
          <Calendar class="w-4 w-4 text-primary" />
          今日全天节目单 (EPG)
        </h5>
        <button @click="epgOpen = false" class="text-muted-foreground hover:text-foreground">
          <X class="w-4 h-4" />
        </button>
      </SheetHeader>
      <SheetContent>
        <div class="space-y-3 text-xs">
          <div v-if="epgLoading" class="space-y-2 py-4">
            <div v-for="i in 4" :key="i" class="h-12 rounded-lg bg-muted animate-pulse" />
          </div>
          <div v-else-if="epgPrograms.length === 0" class="text-center py-8 text-muted-foreground">
            暂无节目数据
          </div>
          <template v-else>
            <div
              v-for="(prog, idx) in epgPrograms" :key="idx"
              :class="cn(
                'p-2.5 rounded-lg transition',
                prog.is_current ? 'bg-primary/5 border border-primary/20 text-foreground relative' : 'hover:bg-accent',
              )"
            >
              <div v-if="prog.is_current" class="absolute right-2 top-2.5 w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              <span :class="prog.is_current ? 'text-primary font-mono font-bold' : 'text-muted-foreground font-mono'" class="block">{{ prog.start }} - {{ prog.stop }}</span>
              <span class="font-semibold block mt-1 text-sm">{{ prog.title }}</span>
              <span v-if="prog.desc" class="text-muted-foreground block mt-0.5">{{ prog.desc }}</span>
            </div>
          </template>
        </div>
      </SheetContent>
    </Sheet>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Tv, Search, Play, PlayCircle, ChevronDown, ChevronRight,
  ListVideo, Maximize2, Calendar, X, Loader2,
} from 'lucide-vue-next'
import { getLiveChannels, getChannelEpg, getCheckHistory } from '../api'
import { cn } from '../lib/utils'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import { ScrollArea } from '../components/ui/scroll-area'
import { Sheet, SheetHeader, SheetContent } from '../components/ui/sheet'

const router = useRouter()

const groups = ref([])
const loading = ref(false)
const searchQuery = ref('')
const expandedGroups = ref(new Set())
const currentChannel = ref(null)
const showFavoritesOnly = ref(false)
const allChannelsFlat = ref([])
const playerIframe = ref(null)
const iframeCreated = ref(false)
const iframeSrc = ref('')

const immersiveMode = ref(false)
const showSkeleton = ref(false)
const epgOpen = ref(false)
const epgPrograms = ref([])
const epgLoading = ref(false)

const history = ref([])
const selectedSessionId = ref('')

const filteredGroups = computed(() => {
  let result = groups.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.map(g => ({
      ...g,
      channels: g.channels.filter(ch => ch.name.toLowerCase().includes(q)),
    })).filter(g => g.channels.length > 0)
  }
  return result
})

function buildPlayerUrl(ch) {
  const encoded = btoa(encodeURIComponent(ch.url))
  return `/player?url=${encoded}&name=${encodeURIComponent(ch.name)}`
}

function changeChannel(ch) {
  showSkeleton.value = true
  currentChannel.value = ch
  localStorage.setItem('iptv_last_channel', JSON.stringify(ch))
  loadEpg(ch.name)

  setTimeout(() => {
    if (!iframeCreated.value) {
      iframeSrc.value = buildPlayerUrl(ch)
      iframeCreated.value = true
    } else if (playerIframe.value?.contentWindow) {
      playerIframe.value.contentWindow.postMessage({
        type: 'switch-channel',
        name: ch.name,
        url: ch.url,
      }, '*')
    }
    showSkeleton.value = false
  }, 400)
}

function playChannel(ch) {
  changeChannel(ch)
}

function toggleImmersiveMode() {
  immersiveMode.value = !immersiveMode.value
}

async function loadChannels() {
  loading.value = true
  try {
    const params = { media_type: 'all' }
    if (selectedSessionId.value) {
      params.session_id = selectedSessionId.value
    }
    const { data } = await getLiveChannels(params)
    groups.value = data.groups || []
    allChannelsFlat.value = groups.value.flatMap(g => g.channels)
    if (groups.value.length > 0) {
      expandedGroups.value = new Set([groups.value[0].name])
    }
    const saved = localStorage.getItem('iptv_last_channel')
    if (saved && !currentChannel.value) {
      try {
        const ch = JSON.parse(saved)
        if (ch.url) currentChannel.value = ch
      } catch {}
    }
  } catch {} finally {
    loading.value = false
  }
}

function toggleGroup(name) {
  const s = new Set(expandedGroups.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedGroups.value = s
}

async function loadEpg(channelName) {
  epgLoading.value = true
  epgPrograms.value = []
  try {
    const { data } = await getChannelEpg(channelName)
    if (data.programs && data.programs.length > 0) {
      const now = new Date()
      epgPrograms.value = data.programs.map(p => ({
        start: new Date(p.start).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        stop: new Date(p.stop).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        title: p.title,
        desc: p.desc || '',
        is_current: now >= new Date(p.start) && now < new Date(p.stop),
      }))
    }
  } catch {} finally {
    epgLoading.value = false
  }
}

function onKeyDown(e) {
  if (e.target.tagName === 'INPUT') return
  if (e.key === 'ArrowUp') { e.preventDefault(); prevChannel() }
  else if (e.key === 'ArrowDown') { e.preventDefault(); nextChannel() }
}

function prevChannel() {
  if (!currentChannel.value || allChannelsFlat.value.length === 0) return
  const idx = allChannelsFlat.value.findIndex(c => c.url === currentChannel.value.url)
  const prev = idx > 0 ? idx - 1 : allChannelsFlat.value.length - 1
  changeChannel(allChannelsFlat.value[prev])
}

function nextChannel() {
  if (!currentChannel.value || allChannelsFlat.value.length === 0) return
  const idx = allChannelsFlat.value.findIndex(c => c.url === currentChannel.value.url)
  const next = idx < allChannelsFlat.value.length - 1 ? idx + 1 : 0
  changeChannel(allChannelsFlat.value[next])
}

function formatHistoryLabel(h) {
  const date = h.created_at ? new Date(h.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未知时间'
  const validRate = h.total > 0 ? Math.round((h.valid / h.total) * 100) : 0
  return `${date} | ${h.total}频道 | 有效${validRate}%`
}

async function onSessionChange() {
  await loadChannels()
}

async function loadHistory() {
  try {
    const { data } = await getCheckHistory(50)
    history.value = Array.isArray(data) ? data : []
    if (history.value.length > 0 && !selectedSessionId.value) {
      selectedSessionId.value = history.value[0].session_id
    }
  } catch (e) {
    console.warn('加载历史记录失败:', e)
    history.value = []
  }
}

onMounted(async () => {
  await loadHistory()
  loadChannels()
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
})
</script>
