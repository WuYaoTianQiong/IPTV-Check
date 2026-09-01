<template>
  <div class="space-y-6">
    <div class="rounded-2xl border bg-gradient-to-br from-primary/10 via-background to-background p-8">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
        <div class="space-y-1.5">
          <h1 class="text-2xl md:text-3xl font-bold tracking-tight">电视直播源检测</h1>
          <p class="text-sm text-muted-foreground">
            <span v-if="matchedSourceCount > 0">已为您匹配 {{ matchedSourceCount }} 条 {{ ispLabel }}线路，共 {{ matchedChannelCount }} 个频道</span>
            <span v-else>从下方选择检测源开始 · 系统将智能并发测速并生成可订阅的 M3U</span>
          </p>
        </div>
        <Button
          size="lg"
          class="gap-2 px-8 shadow-sm"
          :disabled="!canStart || starting || fetching"
          @click="doStart"
        >
          <Loader2 v-if="starting" class="h-5 w-5 animate-spin" />
          <Rocket v-else class="h-5 w-5" />
          {{ starting ? '启动中...' : '一键开始检测' }}
        </Button>
      </div>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader class="flex flex-row items-start justify-between gap-4 space-y-0">
          <div class="space-y-1.5 min-w-0">
            <CardTitle class="flex items-center gap-2">
              <CloudDownload class="h-5 w-5 text-primary" />
              在线直播源
            </CardTitle>
            <CardDescription>
              从在线源库选择，已根据您的运营商自动匹配推荐
              <span v-if="totalSourceCount > 0" class="ml-2 font-semibold text-primary">{{ totalSourceCount }} 个源 / {{ totalChannelCount }} 个频道</span>
            </CardDescription>
          </div>
          <div class="flex flex-col items-end gap-1 shrink-0">
            <Button variant="outline" size="sm" @click="handleSync" :disabled="syncing" class="gap-1.5">
              <RefreshCw v-if="syncing" class="h-3.5 w-3.5 animate-spin" />
              <RefreshCw v-else class="h-3.5 w-3.5" />
              {{ syncing ? '同步中...' : '同步上游源' }}
            </Button>
            <span v-if="syncStatus?.last_sync" class="text-xs text-muted-foreground flex items-center gap-1">
              <Clock class="h-3 w-3" />
              {{ formatSyncTime(syncStatus.last_sync.synced_at) }}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="syncing || backgroundFetching" class="mb-3 p-3 rounded-lg border border-primary/30 bg-primary/5">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 text-primary">
                <RefreshCw class="h-4 w-4 animate-spin" />
                <span class="text-sm font-medium">
                  <template v-if="store.syncProgress.stage === 'fetching_channels'">
                    正在拉取频道 ({{ store.syncProgress.current_url_index || '-' }}/{{ store.syncProgress.total_urls || '-' }})
                    <template v-if="store.syncProgress.fetched_channel_count > 0">，已获取 {{ store.syncProgress.fetched_channel_count }} 个</template>
                  </template>
                  <template v-else>
                    正在同步上游源 ({{ store.syncProgress.current_url_index || '-' }}/{{ store.syncProgress.total_urls || '-' }})
                    <template v-if="store.syncProgress.current_url_label"> — {{ store.syncProgress.current_url_label }}</template>
                  </template>
                </span>
              </div>
              <span v-if="syncPercent > 0" class="text-sm font-bold text-primary">{{ syncPercent }}%</span>
            </div>
            <Progress v-if="syncPercent > 0" :model-value="syncPercent" class="mt-2 h-1.5" />
            <div class="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
              <span>当前显示的是上次同步的源，同步完成后将自动刷新</span>
              <span v-if="syncEtaText">{{ syncEtaText }}</span>
            </div>
          </div>
          <div class="space-y-3">
            <div v-if="pageLoading" class="space-y-3">
              <div
                v-for="i in 6" :key="i"
                class="rounded-lg bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 dark:from-gray-700 dark:via-gray-600 dark:to-gray-700 animate-pulse"
                style="height:52px"
              />
              <p class="text-xs text-center text-muted-foreground mt-2">加载源中...</p>
            </div>
            <div v-else-if="loadError" class="text-center py-8">
              <p class="text-sm text-destructive mb-3">{{ loadError }}</p>
              <Button variant="outline" size="sm" @click="sourceStore.fetchOnlineSources()">重新加载</Button>
            </div>
            <div v-else-if="totalSourceCount === 0" class="text-sm text-muted-foreground py-8 text-center">
              <p>暂无在线源数据</p>
            </div>
            <template v-else>
              <div class="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>共 {{ categorizedSources.length }} 个分类</span>
                <span class="hidden sm:inline">勾选=全选该分类 · 横杠=部分选中</span>
              </div>
              <div class="grid gap-1.5 sm:grid-cols-2">
                <div
                  v-for="cat in categorizedSources"
                  :key="cat.category"
                  class="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-accent transition-colors group"
                  :title="`勾选=全选${cat.category}，取消=清空；横杠=部分选中`"
                >
                  <Checkbox
                    :model-value="isCategoryFullySelected(cat.category)"
                    :indeterminate="isCategoryPartiallySelected(cat.category)"
                    @update:model-value="toggleCategorySelect(cat.category)"
                    @click.stop
                    class="shrink-0"
                  />
                  <button
                    class="flex items-center gap-2 flex-1 min-w-0 text-left"
                    @click="openCategory(cat.category)"
                  >
                    <span class="text-base leading-none">{{ getCategoryIcon(cat.category) }}</span>
                    <span class="text-sm font-medium truncate">{{ cat.category }}</span>
                    <span class="text-xs text-muted-foreground shrink-0 ml-auto">{{ cat.sources.length }}</span>
                    <ChevronRight class="h-3.5 w-3.5 text-muted-foreground shrink-0 transition-transform group-hover:translate-x-0.5" />
                  </button>
                </div>
              </div>
            </template>
          </div>
          <div class="flex items-center justify-between mt-4">
            <span class="text-xs text-muted-foreground">
              已选 <span class="font-semibold text-foreground">{{ selectedOnlineIds.length }}</span> 个源<template v-if="selectedOnlineIds.length"> / {{ selectedChannelCount }} 频道</template>
            </span>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" :disabled="sourceStore.isLoading" @click="handleSelectAllMatched" title="选中运营商匹配的源，以及广播电台和国际电视分类">按推荐选择</Button>
              <Button variant="outline" size="sm" :disabled="sourceStore.isLoading" @click="handleSelectAllCompatible" title="仅选中运营商匹配的源">仅运营商兼容</Button>
              <Button variant="ghost" size="sm" @click="sourceStore.clearOnline" :disabled="selectedOnlineIds.length === 0">清空</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div class="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <FileUp class="h-5 w-5 text-primary" />
              本地文件
            </CardTitle>
            <CardDescription>上传 M3U / M3U8 / TXT 格式的直播源文件</CardDescription>
          </CardHeader>
        <CardContent>
            <div
              @click="fileInput?.click()"
              @dragover.prevent
              @drop.prevent="handleDrop"
              :class="cn(
                'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors',
                'hover:border-primary/50 hover:bg-primary/5',
                uploadedFiles.length > 0 ? 'border-primary bg-primary/5' : 'border-border'
              )"
            >
              <Upload class="h-8 w-8 mx-auto text-muted-foreground mb-3" />
              <p class="text-sm font-medium">点击或拖拽文件到此处</p>
              <p class="text-xs text-muted-foreground mt-1">支持 .m3u, .m3u8, .txt</p>
              <input ref="fileInput" type="file" accept=".m3u,.m3u8,.txt" multiple class="hidden" @change="handleFileChange" />
            </div>
            <div v-if="uploadedFiles.length > 0" class="mt-4 space-y-2">
              <div v-for="(file, idx) in uploadedFiles" :key="idx" class="flex items-center gap-2 rounded-lg bg-accent px-3 py-2">
                <FileText class="h-4 w-4 text-muted-foreground" />
                <span class="text-sm flex-1 truncate">{{ file.name }}</span>
                <button @click="removeFile(idx)" class="text-muted-foreground hover:text-destructive">
                  <X class="h-4 w-4" />
                </button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <Link class="h-5 w-5 text-primary" />
              自定义源
            </CardTitle>
            <CardDescription>添加您自己的 M3U 源地址</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3">
            <div class="flex gap-2">
              <Input v-model="customSrcName" placeholder="源名称" class="flex-1" />
              <Input v-model="customSrcUrl" placeholder="M3U 地址 (http://...)" class="flex-[2]" />
              <Button size="sm" @click="addCustomSource" :disabled="!customSrcUrl">添加</Button>
            </div>
            <div v-for="(src, idx) in customSources" :key="idx" class="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
              <span class="font-medium truncate">{{ src.name }}</span>
              <span class="text-xs text-muted-foreground truncate flex-1">{{ src.url }}</span>
              <button class="text-muted-foreground hover:text-destructive" @click="removeCustomSource(idx)">
                <X class="h-3.5 w-3.5" />
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <details class="group rounded-xl border bg-card transition-colors open:bg-accent/5">
      <summary class="flex items-center justify-between gap-3 px-5 py-4 cursor-pointer list-none select-none">
        <div class="flex items-center gap-2 min-w-0">
          <Settings2 class="h-5 w-5 text-muted-foreground shrink-0" />
          <span class="font-semibold">检测参数</span>
          <span class="hidden sm:inline text-xs text-muted-foreground truncate">连接 {{ config.timeout_connect }}s · 读取 {{ config.timeout_read }}s · 并发 {{ config.max_threads }} · 方案 {{ { quick: '快速', standard: '标准', deep: '深度' }[config.check_mode] || '标准' }}</span>
        </div>
        <ChevronDown class="h-4 w-4 text-muted-foreground transition-transform duration-200 group-open:rotate-180 shrink-0" />
      </summary>
      <div class="px-5 pb-5 space-y-5 border-t pt-4">
        <div class="grid gap-6 lg:grid-cols-3">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">连接超时</label>
              <span class="text-sm text-muted-foreground">{{ config.timeout_connect }} 秒</span>
            </div>
            <Slider v-model="config.timeout_connect" :min="1" :max="10" :step="1" />
          </div>
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">读取超时</label>
              <span class="text-sm text-muted-foreground">{{ config.timeout_read }} 秒</span>
            </div>
            <Slider v-model="config.timeout_read" :min="3" :max="30" :step="1" />
          </div>
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">并发线程数</label>
              <span class="text-sm text-muted-foreground">{{ config.max_threads }}</span>
            </div>
            <Slider v-model="config.max_threads" :min="5" :max="100" :step="5" />
          </div>
        </div>
        <Separator />
        <div>
          <div class="text-sm font-medium mb-2">检测方案</div>
          <Tabs class="w-full">
            <TabButton class="flex-1" :active="config.check_mode === 'quick'" @click="config.check_mode = 'quick'">快速</TabButton>
            <TabButton class="flex-1" :active="config.check_mode === 'standard'" @click="config.check_mode = 'standard'">标准</TabButton>
            <TabButton class="flex-1" :active="config.check_mode === 'deep'" @click="config.check_mode = 'deep'">深度</TabButton>
          </Tabs>
          <div class="text-xs text-muted-foreground mt-1.5">
            <template v-if="config.check_mode === 'quick'">仅测可达性（HTTP 200 + 延迟），速度最快</template>
            <template v-else-if="config.check_mode === 'deep'">可达性 + 拉流验证 + 下载测速，最准但最慢</template>
            <template v-else>可达性 + 拉流验证（推荐）</template>
          </div>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-medium">使用缓存</div>
            <div class="text-xs text-muted-foreground">加速重复检测</div>
          </div>
          <Switch v-model="config.use_cache" />
        </div>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-medium">复检无效频道</div>
            <div class="text-xs text-muted-foreground">对无效频道二次验证（耗时翻倍）</div>
          </div>
          <Switch v-model="config.enable_recheck" />
        </div>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-medium">智能筛选</div>
            <div class="text-xs text-muted-foreground">仅拉取历史有效率≥阈值的源（0=不筛选）</div>
          </div>
          <div class="flex items-center gap-2">
            <Input v-model.number="config.min_valid_rate" type="number" :min="0" :max="100" :step="5" class="w-16 text-right text-sm" />
            <span class="text-xs text-muted-foreground">%</span>
          </div>
        </div>
      </div>
    </details>

    <div class="flex justify-end gap-3 flex-wrap">
      <Button
        variant="outline"
        :disabled="!canStart || fetching || starting"
        @click="doFetch"
        class="gap-2 px-6"
        title="只下载并解析选中源的频道列表（不测速），供「一键检测」自动复用"
      >
        <CloudDownload v-if="!fetching" class="h-4 w-4" />
        <Loader2 v-else class="h-4 w-4 animate-spin" />
        {{ fetching ? `拉取中 ${fetchProgress.done_sources}/${fetchProgress.total_sources}` : '仅拉取频道列表' }}
      </Button>
      <Button
        size="lg"
        :disabled="!canStart || starting || fetching"
        @click="doStart"
        class="gap-2 px-8 shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 transition-all"
      >
        <Loader2 v-if="starting" class="h-5 w-5 animate-spin" />
        <Play v-else class="h-5 w-5" />
        {{ starting ? '启动中...' : '一键检测' }}
      </Button>
    </div>

    <SourceDetailDialog v-model:open="showDetailDialog" :source="detailSource" />
    <CategorySourcesDialog v-model:open="showCategoryDialog" :category="activeCategory" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  Rocket, CloudDownload, FileUp, Settings2, Play,
  Upload, FileText, X, Loader2, Link, RefreshCw, Clock,
  ChevronDown, ChevronRight,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useSourceStore } from '../stores/source'
import { useCheckStore } from '../stores/check'
import { startCheck, uploadFile, triggerSourceSync, getSourceSyncStatus, getSourceSyncProgress, startFetch, getFetchProgress } from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Progress } from '../components/ui/progress'
import { Button } from '../components/ui/button'
import { Slider } from '../components/ui/slider'
import { Switch } from '../components/ui/switch'
import { Separator } from '../components/ui/separator'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import { Tabs, TabButton } from '../components/ui/tabs'
import SourceDetailDialog from '../components/SourceDetailDialog.vue'
import CategorySourcesDialog from '../components/CategorySourcesDialog.vue'

const store = useAppStore()
const sourceStore = useSourceStore()
const checkStore = useCheckStore()
const router = useRouter()
const { toast } = useToast()

const selectedOnlineIds = computed(() => sourceStore.selectedOnlineIds)
const detailSource = ref(null)
const showDetailDialog = ref(false)
const activeCategory = ref('')
const showCategoryDialog = ref(false)
const uploadedFiles = ref([])
const fileInput = ref(null)
const starting = ref(false)
const fetching = ref(false)
const fetchProgress = ref({ is_fetching: false, total_sources: 0, done_sources: 0, fetched_channels: 0 })

const syncing = ref(false)
const syncStatus = ref(null)
const backgroundFetching = ref(false)
let syncProgressTimer = null

const syncPercent = computed(() => {
  const { current_url_index, total_urls } = store.syncProgress
  if (!total_urls || total_urls === 0) return 0
  return Math.min(Math.round((current_url_index / total_urls) * 100), 100)
})

const syncEtaText = computed(() => {
  const { eta_seconds, elapsed_seconds } = store.syncProgress
  if (eta_seconds != null && eta_seconds > 0) {
    if (eta_seconds < 60) return `约 ${Math.round(eta_seconds)} 秒`
    return `约 ${Math.round(eta_seconds / 60)} 分钟`
  }
  if (elapsed_seconds > 0) {
    const sec = Math.round(elapsed_seconds)
    if (sec < 60) return `已用时 ${sec} 秒`
    return `已用时 ${Math.round(sec / 60)} 分 ${sec % 60} 秒`
  }
  return ''
})

onMounted(() => {
  sourceStore.fetchOnlineSources().catch(() => {})
  loadSyncStatus()
  checkSyncInProgress()
  checkFetchInProgress()
})

onUnmounted(() => {
  stopSyncProgressPolling()
})

async function checkSyncInProgress() {
  try {
    const { data } = await getSourceSyncProgress()
    store.syncProgress = { ...store.syncProgress, ...data }
    if (data.is_syncing) {
      if (data.stage === 'fetching_channels') {
        backgroundFetching.value = true
      } else {
        syncing.value = true
        startSyncProgressPolling()
      }
    }
  } catch {}
}

async function checkFetchInProgress() {
  try {
    const { data } = await getFetchProgress()
    if (data.is_fetching) {
      backgroundFetching.value = true
    }
  } catch {}
}

watch(() => store.syncProgress, (val) => {
  if (val.is_syncing && val.stage === 'fetching_channels' && !syncing.value) {
    backgroundFetching.value = true
  }
  if (val.is_syncing && val.stage !== 'fetching_channels' && !syncing.value) {
    syncing.value = true
    if (!syncProgressTimer) startSyncProgressPolling()
  }
  if (!val.is_syncing) {
    if (syncing.value) {
      syncing.value = false
      stopSyncProgressPolling()
      if (val.stage === 'completed') {
        toast.success('同步完成', `新增 ${val.added} 个源，更新 ${val.updated} 个源`)
        sourceStore.reset()
        sourceStore.fetchOnlineSources().catch(() => {})
        loadSyncStatus()
      } else if (val.stage === 'failed') {
        toast.error('同步失败', '上游源同步失败')
        loadSyncStatus()
      }
    }
    if (backgroundFetching.value) {
      backgroundFetching.value = false
      sourceStore.fetchOnlineSources().catch(() => {})
    }
  }
}, { deep: true })

async function loadSyncStatus() {
  try {
    const { data } = await getSourceSyncStatus()
    syncStatus.value = data
  } catch {}
}

function formatSyncTime(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  } catch {
    return ''
  }
}

function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '0秒'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  if (m < 60) return `${m}分${s}秒`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return `${h}时${rm}分`
}

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    await triggerSourceSync()
    try {
      const { data } = await getSourceSyncProgress()
      store.syncProgress = { ...store.syncProgress, ...data }
    } catch {}
    startSyncProgressPolling()
    toast.success('同步已启动', '正在后台同步上游源，您可以继续操作')
  } catch (e) {
    syncing.value = false
    toast.error('同步启动失败', e.message || '网络错误')
  }
}

function startSyncProgressPolling() {
  stopSyncProgressPolling()
  syncProgressTimer = setInterval(async () => {
    try {
      const { data } = await getSourceSyncProgress()
      store.syncProgress = { ...store.syncProgress, ...data }
    } catch {}
  }, 2000)
}

function stopSyncProgressPolling() {
  if (syncProgressTimer) {
    clearInterval(syncProgressTimer)
    syncProgressTimer = null
  }
}

const config = reactive({
  timeout_connect: 5,
  timeout_read: 15,
  max_threads: 80,
  check_mode: 'standard',
  use_cache: true,
  enable_recheck: false,
  min_valid_rate: 0,
})

const totalSourceCount = computed(() => sourceStore.onlineSources.length || 0)
const totalChannelCount = computed(() => sourceStore.onlineSources.reduce((sum, s) => sum + (s.channel_count || 0), 0) || 0)
const pageLoading = computed(() => sourceStore.isLoading)
const loadError = computed(() => sourceStore.error)
const categorizedSources = computed(() => sourceStore.categorizedSources)

function getCategoryIcon(category) {
  if (/国际|海外/.test(category)) return '🌍'
  if (/广播|Radio/.test(category)) return '📻'
  return '📺'
}

function openCategory(category) {
  activeCategory.value = category
  showCategoryDialog.value = true
}

// 预计算分类 -> 源 id 列表（缓存，避免每帧渲染时对 28980 个源反复 filter）
const categoryIdsMap = computed(() => {
  const map = {}
  for (const s of sourceStore.onlineSources) {
    if (s.disabled) continue
    const cat = s.category || '未分类'
    if (!map[cat]) map[cat] = []
    map[cat].push(s.id)
  }
  return map
})

function isCategoryFullySelected(category) {
  const ids = categoryIdsMap.value[category] || []
  return ids.length > 0 && ids.every(id => sourceStore.selectedIdSet.has(id))
}

function isCategoryPartiallySelected(category) {
  const ids = categoryIdsMap.value[category] || []
  if (ids.length === 0) return false
  let selected = 0
  for (const id of ids) {
    if (sourceStore.selectedIdSet.has(id)) selected++
  }
  return selected > 0 && selected < ids.length
}

function toggleCategorySelect(category) {
  if (isCategoryFullySelected(category)) {
    sourceStore.clearCategory(category)
  } else {
    sourceStore.selectCategory(category)
  }
}

const customSrcName = ref('')
const customSrcUrl = ref('')
const customSources = ref([])

try {
  const saved = localStorage.getItem('iptv_custom_sources')
  if (saved) customSources.value = JSON.parse(saved)
} catch {}

const canStart = computed(() => selectedOnlineIds.value.length > 0 || uploadedFiles.value.length > 0)

const selectedChannelCount = computed(() => {
  let total = 0
  for (const s of sourceStore.onlineSources) {
    if (sourceStore.selectedIdSet.has(s.id)) total += s.channel_count || 0
  }
  return total
})

function showDetail(id) {
  detailSource.value = sourceStore.onlineSources.find(s => s.id === id) || null
  if (detailSource.value) showDetailDialog.value = true
}

function handleSelectAllMatched() {
  const before = sourceStore.selectedOnlineIds.length
  sourceStore.selectAllMatched()
  const total = sourceStore.selectedOnlineIds.length
  const added = total - before
  toast.success(
    '按推荐选择完成',
    added > 0 ? `本次新增 ${added} 个推荐源，当前已选 ${total} 个源` : '当前已选源均已推荐，无需新增'
  )
}

function handleSelectAllCompatible() {
  const before = sourceStore.selectedOnlineIds.length
  sourceStore.selectAllCompatible()
  const total = sourceStore.selectedOnlineIds.length
  const added = total - before
  toast.success(
    '仅选运营商兼容完成',
    added > 0 ? `本次新增 ${added} 个运营商兼容源（非检测有效，仅表示源适配你的运营商），当前已选 ${total} 个源` : '当前已选源已全部为运营商兼容'
  )
}

const ispLabel = computed(() => {
  const isp = store.localIsp
  if (!isp || isp === '检测中...' || isp === '未知') return '…'
  return isp
})

const matchedSourceCount = computed(() => {
  return sourceStore.onlineSources.filter(s => s.isp_compatible).length || 0
})

const matchedChannelCount = computed(() => {
  return sourceStore.onlineSources
    .filter(s => s.isp_compatible)
    .reduce((sum, s) => sum + (s.channel_count || 0), 0) || 0
})

function addCustomSource() {
  if (!customSrcUrl.value) return
  customSources.value.push({ name: customSrcName.value || '自定义源', url: customSrcUrl.value })
  localStorage.setItem('iptv_custom_sources', JSON.stringify(customSources.value))
  customSrcName.value = ''
  customSrcUrl.value = ''
}

function removeCustomSource(idx) {
  customSources.value.splice(idx, 1)
  localStorage.setItem('iptv_custom_sources', JSON.stringify(customSources.value))
}

function handleFileChange(e) {
  const files = Array.from(e.target.files || [])
  for (const file of files) {
    if (!uploadedFiles.value.find(f => f.name === file.name)) uploadedFiles.value.push(file)
  }
}

function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files || [])
  for (const file of files) {
    if (!uploadedFiles.value.find(f => f.name === file.name)) uploadedFiles.value.push(file)
  }
}

function removeFile(idx) {
  uploadedFiles.value.splice(idx, 1)
}

async function doFetch() {
  fetching.value = true
  fetchProgress.value = { is_fetching: true, total_sources: 0, done_sources: 0, fetched_channels: 0 }
  try {
    const payload = {
      online_source_ids: selectedOnlineIds.value,
      use_cache: config.use_cache,
      min_valid_rate: (config.min_valid_rate || 0) / 100,
    }
    const fetchPromise = startFetch(payload)
    const pollTimer = setInterval(async () => {
      try {
        const { data } = await getFetchProgress()
        fetchProgress.value = data
      } catch {}
    }, 2000)
    const { data } = await fetchPromise
    clearInterval(pollTimer)
    const { data: finalData } = await getFetchProgress()
    fetchProgress.value = finalData
    const channelCount = data.fetched_channels || finalData.fetched_channels || 0
    const rawChannels = data.raw_channels || finalData.raw_channels || 0
    const dedupChannels = data.dedup_channels || finalData.dedup_channels || 0
    if (dedupChannels > 0) {
      toast.success('拉取完成', `共获取 ${channelCount} 个唯一频道（去重前 ${rawChannels}，跨源重复 ${dedupChannels} 个）`)
    } else {
      toast.success('拉取完成', `共获取 ${channelCount} 个频道`)
    }
  } catch (e) {
    console.error('拉取失败:', e)
    let msg = '拉取失败'
    if (e.response?.data?.detail) msg = e.response.data.detail
    else if (e.message) msg = e.message
    toast.error('拉取失败', msg)
  } finally {
    fetching.value = false
  }
}

async function doStart() {
  starting.value = true
  try {
    const filePaths = []
    for (const file of uploadedFiles.value) {
      const reader = new FileReader()
      const content = await new Promise((resolve, reject) => {
        reader.onload = () => resolve(reader.result)
        reader.onerror = reject
        reader.readAsDataURL(file)
      })
      const base64 = content.split(',')[1]
      const { data } = await uploadFile({ filename: file.name, content_base64: base64 })
      filePaths.push(data.path)
    }

    const payload = {
      online_source_ids: selectedOnlineIds.value,
      file_paths: filePaths,
      ...config,
    }

    router.push('/checking')
    checkStore.startCheckState(0)
    await startCheck(payload)
  } catch (e) {
    console.error('启动检测失败:', e)
    checkStore.resetCheckState()
    router.push('/source')
    let msg = '启动检测失败'
    if (e.code === 'ECONNABORTED') msg = '启动检测超时，请减少在线源数量或稍后重试'
    else if (e.response?.data?.detail) msg = e.response.data.detail
    else if (e.message) msg = e.message
    toast.error('启动失败', msg)
  } finally {
    starting.value = false
  }
}
</script>


