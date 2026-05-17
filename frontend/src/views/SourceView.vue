<template>
  <div class="space-y-6">
    <div class="p-6 rounded-xl border border-blue-100 bg-blue-50/50 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 shadow-sm">
      <div class="flex items-start gap-4">
        <div class="p-3 bg-blue-600 rounded-lg text-white">
          <Sparkles class="w-6 h-6 animate-pulse" />
        </div>
        <div>
          <h3 class="font-bold text-lg text-slate-900">✨ 智能推荐 (已匹配{{ ispLabel }})</h3>
          <p class="text-sm text-slate-600 mt-1">系统已为您智能同步 {{ matchedSourceCount }} 个最适配的专属极速线路，包含 {{ matchedChannelCount }} 个高清源。</p>
        </div>
      </div>
      <Button
        class="px-6 py-3 gap-2 shadow-sm"
        @click="handleStartCheck"
      >
        <Rocket class="w-4 h-4" />
        一键开始检测
      </Button>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <CloudDownload class="h-5 w-5 text-primary" />
            在线直播源
          </CardTitle>
          <CardDescription>
            从在线源库选择，已根据您的运营商自动匹配推荐
            <span v-if="totalSourceCount > 0" class="ml-2 font-semibold text-primary">共 {{ totalSourceCount }} 个源（含 {{ totalChannelCount }} 个频道，检测时自动去重）</span>
          </CardDescription>
          <div class="flex items-center gap-2 mt-1">
            <Button variant="outline" size="sm" @click="handleSync" :disabled="syncing" class="gap-1.5">
              <RefreshCw v-if="syncing" class="h-3.5 w-3.5 animate-spin" />
              <RefreshCw v-else class="h-3.5 w-3.5" />
              {{ syncing ? '同步中...' : '同步上游源' }}
            </Button>
            <span v-if="syncStatus?.last_sync" class="text-xs text-muted-foreground flex items-center gap-1">
              <Clock class="h-3 w-3" />
              上次同步: {{ formatSyncTime(syncStatus.last_sync.synced_at) }}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="syncing || backgroundFetching" class="mb-3 p-3 rounded-lg border border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/50">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 text-blue-700 dark:text-blue-300">
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
              <span v-if="syncPercent > 0" class="text-sm font-bold text-blue-700 dark:text-blue-300">{{ syncPercent }}%</span>
            </div>
            <Progress v-if="syncPercent > 0" :model-value="syncPercent" class="mt-2 h-1.5" />
            <div class="mt-1.5 flex items-center justify-between text-xs text-blue-600 dark:text-blue-400">
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
              <p class="text-xs text-center text-muted-foreground mt-2">正在加载在线源列表...</p>
            </div>
            <div v-else-if="loadError" class="text-center py-8">
              <p class="text-sm text-destructive mb-3">{{ loadError }}</p>
              <Button variant="outline" size="sm" @click="sourceStore.fetchOnlineSources()">重新加载</Button>
            </div>
            <div v-else-if="categorizedSources.length === 0" class="text-sm text-muted-foreground py-8 text-center">
              <p>暂无在线源数据</p>
            </div>
            <template v-else>
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs text-muted-foreground">共 {{ categorizedSources.length }} 个分类</span>
                <Button variant="ghost" size="sm" class="h-6 text-xs gap-1" @click="toggleAllCategories">
                  <ChevronsUpDown class="h-3.5 w-3.5" />
                  全部{{ allCollapsed ? '展开' : '折叠' }}
                </Button>
              </div>
              <div v-for="cat in categorizedSources" :key="cat.category" class="space-y-1">
                <h4 class="text-xs font-semibold tracking-wider px-2 flex items-center gap-1.5 cursor-pointer hover:text-primary transition-colors" :class="getCategoryStyle(cat.category)" @click="toggleCategory(cat.category)">
                  <ChevronDown v-if="!isCategoryCollapsed(cat.category)" class="h-3 w-3" />
                  <ChevronRight v-else class="h-3 w-3" />
                  <span>{{ getCategoryIcon(cat.category) }}</span>
                  {{ cat.category }}
                  <span class="text-muted-foreground font-normal">({{ cat.sources.length }}个源)</span>
                </h4>
                <div v-if="!isCategoryCollapsed(cat.category)">
                  <VirtualList
                    :items="cat.sources"
                    :item-height="36"
                    :visible-count="14"
                    :selected-ids="selectedOnlineIds"
                    :expanded-id="expandedSourceId"
                    @toggle-online="toggleOnline"
                    @toggle-expand="toggleExpand"
                  />
                </div>
              </div>
            </template>
          </div>
          <div class="flex gap-2 mt-4">
            <Button variant="outline" size="sm" @click="selectAllMatched">全选匹配</Button>
            <Button variant="outline" size="sm" @click="clearOnline">取消全选</Button>
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

    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <Settings2 class="h-5 w-5 text-primary" />
          检测参数
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-5">
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
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-medium">测速</div>
            <div class="text-xs text-muted-foreground">检测下载速度（较慢但更准确）</div>
          </div>
          <Switch v-model="config.run_speed_test" />
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
      </CardContent>
    </Card>

    <div class="flex justify-end gap-3 flex-wrap">
      <Button
        variant="outline"
        :disabled="!canStart || fetching || starting"
        @click="doFetch"
        class="gap-2 px-6"
      >
        <CloudDownload v-if="!fetching" class="h-4 w-4" />
        <Loader2 v-else class="h-4 w-4 animate-spin" />
        {{ fetching ? `拉取中 ${fetchProgress.done_sources}/${fetchProgress.total_sources}` : '拉取数据' }}
      </Button>
      <Button
        variant="outline"
        :disabled="!hasFetchedData || starting || fetching"
        @click="doCheckFromFetched"
        class="gap-2 px-6"
      >
        <Play class="h-4 w-4" />
        使用已拉取数据检测
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  Sparkles, Rocket, CloudDownload, FileUp, Settings2, Play,
  Upload, FileText, X, Loader2, Link, RefreshCw, Clock,
  ChevronDown, ChevronRight, ChevronsUpDown,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useSourceStore } from '../stores/source'
import { useCheckStore } from '../stores/check'
import { startCheck, checkFromFetched, uploadFile, triggerSourceSync, getSourceSyncStatus, getSourceSyncProgress, startFetch, getFetchProgress, getFetchedChannels } from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Progress } from '../components/ui/progress'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Slider } from '../components/ui/slider'
import { Switch } from '../components/ui/switch'
import { Separator } from '../components/ui/separator'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import VirtualList from '../components/VirtualList.vue'

const store = useAppStore()
const sourceStore = useSourceStore()
const checkStore = useCheckStore()
const router = useRouter()
const { toast } = useToast()

const selectedOnlineIds = ref([])
const uploadedFiles = ref([])
const fileInput = ref(null)
const starting = ref(false)
const fetching = ref(false)
const fetchProgress = ref({ is_fetching: false, total_sources: 0, done_sources: 0, fetched_channels: 0 })
const hasFetchedData = ref(false)

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
  checkFetchedData()
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

async function checkFetchedData() {
  try {
    const { data } = await getFetchedChannels()
    hasFetchedData.value = data.count > 0
  } catch {}
}

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
  run_speed_test: false,
  use_cache: true,
  enable_recheck: false,
  min_valid_rate: 0,
})

const categorizedSources = computed(() => sourceStore.categorizedSources)
const totalSourceCount = computed(() => sourceStore.onlineSources.length || 0)
const totalChannelCount = computed(() => sourceStore.onlineSources.reduce((sum, s) => sum + (s.channel_count || 0), 0) || 0)
const pageLoading = computed(() => sourceStore.isLoading)
const loadError = computed(() => sourceStore.error)

const PROTOCOL_MAP = { hls: 'HLS', http: 'HTTP', rtmp: 'RTMP', rtsp: 'RTSP', ts: 'TS' }
const QUALITY_MAP = { S: 'S级', A: 'A级', B: 'B级', C: 'C级' }

const expandedSourceId = ref(null)
function toggleExpand(id) {
  expandedSourceId.value = expandedSourceId.value === id ? null : id
}

const collapsedCategories = ref(new Set())
try {
  const saved = localStorage.getItem('iptv_collapsed_categories')
  if (saved) collapsedCategories.value = new Set(JSON.parse(saved))
} catch {}

function isCategoryCollapsed(category) {
  return collapsedCategories.value.has(category)
}

function toggleCategory(category) {
  if (collapsedCategories.value.has(category)) {
    collapsedCategories.value.delete(category)
  } else {
    collapsedCategories.value.add(category)
  }
  try {
    localStorage.setItem('iptv_collapsed_categories', JSON.stringify([...collapsedCategories.value]))
  } catch {}
}

function getCategoryIcon(category) {
  if (/国际|海外/.test(category)) return '🌍'
  if (/广播|Radio/.test(category)) return '📻'
  return '📺'
}

function getCategoryStyle(category) {
  if (/国际|海外/.test(category)) return 'text-primary'
  if (/广播|Radio/.test(category)) return 'text-primary'
  return 'text-muted-foreground'
}

const allCollapsed = computed(() => {
  return categorizedSources.value.length > 0 && categorizedSources.value.every(cat => isCategoryCollapsed(cat.category))
})

function toggleAllCategories() {
  if (allCollapsed.value) {
    collapsedCategories.value.clear()
  } else {
    categorizedSources.value.forEach(cat => collapsedCategories.value.add(cat.category))
  }
  try {
    localStorage.setItem('iptv_collapsed_categories', JSON.stringify([...collapsedCategories.value]))
  } catch {}
}

function shouldShowProtocol(protocol) {
  return protocol && protocol !== 'unknown'
}

function getProtocolLabel(protocol) {
  return PROTOCOL_MAP[protocol] || protocol
}

function shouldShowQuality(rating) {
  return rating && rating !== 'A' && rating !== 'C'
}

function getQualityLabel(rating) {
  return QUALITY_MAP[rating] || rating
}

function shouldShowIsp(isp) {
  if (!isp || !isp.length) return false
  return !(isp.length === 1 && isp[0] === '其他')
}

const customSrcName = ref('')
const customSrcUrl = ref('')
const customSources = ref([])

try {
  const saved = localStorage.getItem('iptv_custom_sources')
  if (saved) customSources.value = JSON.parse(saved)
} catch {}

const canStart = computed(() => selectedOnlineIds.value.length > 0 || uploadedFiles.value.length > 0)

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

function isIspMatch(src) {
  return src.isp_compatible
}

function toggleOnline(id) {
  const idx = selectedOnlineIds.value.indexOf(id)
  if (idx >= 0) selectedOnlineIds.value.splice(idx, 1)
  else selectedOnlineIds.value.push(id)
}

function selectAllMatched() {
  const matched = sourceStore.onlineSources
    .filter(s => !s.disabled && (s.isp_compatible || s.category === '广播电台' || s.category === '国际电视'))
    .map(s => s.id)
  selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...matched])]
}

function clearOnline() {
  selectedOnlineIds.value = []
}

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

function handleStartCheck() {
  router.push('/checking')
}

async function doFetch() {
  fetching.value = true
  fetchProgress.value = { is_fetching: true, total_sources: 0, done_sources: 0, fetched_channels: 0 }
  try {
    const payload = {
      online_source_ids: selectedOnlineIds.value,
      use_cache: true,
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
    hasFetchedData.value = true
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

async function doCheckFromFetched() {
  starting.value = true
  try {
    const payload = {
      timeout_connect: config.timeout_connect,
      timeout_read: config.timeout_read,
      max_threads: config.max_threads,
      run_speed_test: config.run_speed_test,
      use_cache: config.use_cache,
      enable_recheck: config.enable_recheck,
    }
    router.push('/checking')
    checkStore.startCheckState(0)
    await checkFromFetched(payload)
  } catch (e) {
    console.error('检测失败:', e)
    checkStore.resetCheckState()
    router.push('/source')
    let msg = '启动检测失败'
    if (e.response?.data?.detail) msg = e.response.data.detail
    else if (e.message) msg = e.message
    toast.error('启动失败', msg)
  } finally {
    starting.value = false
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
