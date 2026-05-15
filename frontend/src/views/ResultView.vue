<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">检测结果</h1>
        <p class="text-muted-foreground mt-1">
          共 {{ resultStore.resultsTotal }} 个频道 · 有效 {{ checkStore.validCount }} · 无效 {{ checkStore.invalidCount }}
          <span v-if="historyList.length > 0" class="ml-2 text-xs">
            · 最近 {{ historyList.length }} 次检测
          </span>
        </p>
      </div>
      <div class="flex gap-2 flex-wrap">
        <Button variant="outline" class="gap-2" @click="router.push('/source')">
          <ArrowLeft class="h-4 w-4" /> 返回选源
        </Button>
        <Button variant="outline" class="gap-2" @click="doOptimize">
          <Wand2 class="h-4 w-4" /> 智能优选
        </Button>
        <Button class="gap-2" @click="showExport = true">
          <Download class="h-4 w-4" /> 导出
        </Button>
      </div>
    </div>

    <!-- 历史检测列表（可折叠） -->
    <details class="group" v-if="historyList.length > 0">
      <summary class="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer hover:text-foreground transition-colors select-none py-1">
        <ChevronRight class="h-4 w-4 group-open:rotate-90 transition-transform" />
        历史检测 · 最近 {{ historyList.length }} 次
        <span class="text-xs text-muted-foreground ml-auto">点击切换</span>
      </summary>
      <div class="flex gap-2 overflow-x-auto mt-2 pb-2 scrollbar-thin">
        <div v-for="h in historyList" :key="h.session_id"
             class="flex flex-col gap-1 min-w-[160px] p-3 rounded-lg cursor-pointer border transition-all"
             :class="h.session_id === currentSessionId ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50 hover:bg-accent/50'"
             @click="loadHistorySession(h.session_id)">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium">{{ formatTime(h.created_at) }}</span>
            <Badge v-if="h.session_id === currentSessionId" variant="default" class="text-[10px]">当前</Badge>
          </div>
          <div class="text-xs text-muted-foreground">{{ h.total }} 频道</div>
          <div class="flex gap-2 text-[10px]">
            <span class="text-green-500">✓ {{ h.valid }} 有效</span>
            <span class="text-red-500">✗ {{ h.invalid }} 无效</span>
          </div>
        </div>
      </div>
    </details>

    <div class="grid gap-6 lg:grid-cols-[260px_1fr]">
      <div class="space-y-4">
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium">历史检测</CardTitle>
          </CardHeader>
          <CardContent class="p-2 space-y-1.5 max-h-[40vh] overflow-y-auto">
            <div v-for="h in historyList" :key="h.session_id"
                 class="flex items-center justify-between text-xs px-2 py-1.5 rounded cursor-pointer"
                 :class="h.session_id === currentSessionId ? 'bg-primary/10 border border-primary/30' : 'hover:bg-accent/50'"
                 @click="loadHistorySession(h.session_id)">
              <div class="flex-1 min-w-0">
                <div class="font-medium truncate">{{ formatTime(h.created_at) }}</div>
                <div class="text-muted-foreground">{{ h.total }} 频道 · {{ h.valid }} 有效 · {{ h.invalid }} 无效</div>
              </div>
            </div>
            <div v-if="historyList.length === 0" class="text-xs text-muted-foreground text-center py-2">
              暂无历史记录
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium">分类导航</CardTitle>
          </CardHeader>
          <CardContent class="p-2 max-h-[70vh] overflow-y-auto">
            <div v-for="region in categoryTree" :key="region.name" class="mb-2">
              <button
                class="w-full flex items-center justify-between px-2 py-1.5 rounded text-sm font-medium hover:bg-accent/50"
                :class="selectedRegion === region.name && !selectedGroup ? 'bg-accent text-accent-foreground' : ''"
                @click="selectRegion(region.name)"
              >
                <span>{{ region.name }}</span>
                <span class="text-xs text-muted-foreground">{{ region.valid }}/{{ region.count }}</span>
              </button>
              <div v-if="expandedRegion === region.name" class="ml-3 space-y-0.5">
                <button
                  v-for="grp in region.children"
                  :key="grp.name"
                  class="w-full flex items-center justify-between px-2 py-1 rounded text-xs hover:bg-accent/50"
                  :class="selectedGroup === grp.name ? 'bg-accent text-accent-foreground' : ''"
                  @click="selectGroup(region.name, grp.name)"
                >
                  <span class="truncate">
                    <template v-if="grp.flag">{{ grp.flag }} </template>
                    <template v-if="grp.country_zh">{{ grp.country_zh }} · </template>
                    {{ grp.name }}
                  </span>
                  <span class="text-muted-foreground ml-1 shrink-0">{{ grp.valid }}/{{ grp.count }}</span>
                </button>
              </div>
            </div>
            <div v-if="categoryTree.length === 0" class="text-xs text-muted-foreground text-center py-4">
              暂无分类数据
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium">源健康度</CardTitle>
          </CardHeader>
          <CardContent class="p-2 space-y-1.5">
            <div v-for="src in sourceHealth" :key="src.source_name" class="flex items-center justify-between text-xs px-2 py-1 rounded hover:bg-accent/50">
              <span class="truncate max-w-[120px]">{{ src.source_name }}</span>
              <Badge :variant="src.success ? 'success' : 'destructive'" class="text-[10px] ml-1">
                {{ src.channel_count }} {{ src.success ? '成功' : '失败' }}
              </Badge>
            </div>
            <div v-if="sourceHealth.length === 0" class="text-xs text-muted-foreground text-center py-2">
              暂无数据
            </div>
          </CardContent>
        </Card>
      </div>

      <div class="space-y-4">
        <Card v-if="breadcrumb.length > 0">
          <CardContent class="p-3">
            <div class="flex items-center gap-1 text-sm flex-wrap">
              <button class="text-muted-foreground hover:text-foreground" @click="clearSelection">全部</button>
              <template v-for="(crumb, i) in breadcrumb" :key="i">
                <ChevronRight class="h-3 w-3 text-muted-foreground" />
                <button
                  :class="i === breadcrumb.length - 1 ? 'font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'"
                  @click="breadcrumb.length > 1 && i < breadcrumb.length - 1 && clearSelection()"
                >{{ crumb }}</button>
              </template>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="p-4 space-y-4">
            <div class="flex flex-col sm:flex-row gap-3">
              <div class="relative flex-1">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input v-model="resultStore.searchQuery" placeholder="搜索频道名..." class="pl-9" @input="onSearch" />
              </div>
              <div class="flex gap-2 flex-wrap">
                <select
                  v-if="availableLanguages.length > 0"
                  v-model="selectedLanguage"
                  class="h-9 rounded-md border border-input bg-background px-3 text-sm"
                  @change="switchLanguage(selectedLanguage)"
                >
                  <option value="">全部语言</option>
                  <option v-for="lang in availableLanguages" :key="lang.language" :value="lang.language">
                    {{ lang.language }} ({{ lang.count }})
                  </option>
                </select>
                <Button
                  v-for="tab in tabs" :key="tab.value"
                  variant="outline" size="sm"
                  :class="resultStore.currentTab === tab.value ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
                  @click="switchTab(tab.value)"
                >
                  {{ tab.label }}
                  <Badge variant="secondary" class="ml-1.5">{{ tab.count }}</Badge>
                </Button>
              </div>
              <div class="flex gap-2">
                <Button
                  v-for="mt in mediaTypes" :key="mt.value"
                  variant="outline" size="sm"
                  :class="mediaType === mt.value ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
                  @click="switchMediaType(mt.value)"
                >{{ mt.label }}</Button>
              </div>
              <div class="flex gap-2">
                <Button
                  variant="outline" size="sm"
                  :class="viewMode === 'grouped' ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
                  @click="switchViewMode('grouped')"
                >聚合</Button>
                <Button
                  variant="outline" size="sm"
                  :class="viewMode === 'flat' ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
                  @click="switchViewMode('flat')"
                >平铺</Button>
              </div>
            </div>

            <div v-if="viewMode === 'grouped'" class="space-y-2">
              <div
                v-for="item in resultStore.checkResults" :key="item.index"
                class="rounded-lg border p-3 transition-colors hover:border-primary/30"
                :class="item.has_valid ? 'border-l-2 border-l-success' : 'border-l-2 border-l-destructive'"
              >
                <div class="flex items-center gap-3">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="font-medium">{{ item.name }}</span>
                      <Badge variant="outline" class="text-[10px] shrink-0">{{ item.group || '未分组' }}</Badge>
                      <Badge v-if="item.source_count > 1" variant="secondary" class="text-[10px] shrink-0">
                        {{ item.source_count }}源
                      </Badge>
                      <Badge v-if="item.valid_count > 0 && item.source_count > 1" variant="success" class="text-[10px] shrink-0">
                        推荐
                      </Badge>
                    </div>
                    <div class="text-xs text-muted-foreground mt-0.5">
                      有效 {{ item.valid_count }}/{{ item.source_count }}
                      <span v-if="item.best_latency && item.best_latency !== '-'"> · 最优 {{ item.best_latency }}ms</span>
                    </div>
                  </div>
                  <div class="flex items-center gap-1 shrink-0">
                    <Button variant="ghost" size="icon" class="h-8 w-8" @click="openEpg(item)">
                      <Calendar class="h-4 w-4" />
                    </Button>
                    <Button v-if="item.has_valid" variant="ghost" size="icon" class="h-8 w-8" @click="playRecommended(item)">
                      <PlayCircle class="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" class="h-8 w-8" @click="toggleExpand(item.name)">
                      <ChevronDown v-if="expandedChannels.has(item.name)" class="h-4 w-4" />
                      <ChevronRight v-else class="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div v-if="expandedChannels.has(item.name) && item.sources" class="mt-3 space-y-1.5 border-t pt-2">
                  <div
                    v-for="(src, si) in item.sources" :key="si"
                    class="flex items-center gap-2 px-2 py-1.5 rounded text-xs hover:bg-accent/50"
                    :class="si === item.recommended_source_idx ? 'bg-success/10 border border-success/20' : ''"
                  >
                    <Badge :variant="src.is_valid ? 'success' : 'destructive'" class="text-[10px] shrink-0">
                      {{ src.is_valid ? '有效' : '无效' }}
                    </Badge>
                    <span class="text-muted-foreground w-12 shrink-0">{{ src.latency }}ms</span>
                    <span class="text-muted-foreground w-14 shrink-0">{{ src.speed }}</span>
                    <span class="truncate text-muted-foreground flex-1" :title="src.url">{{ src.url }}</span>
                    <Badge v-if="si === item.recommended_source_idx" variant="success" class="text-[10px] shrink-0">推荐</Badge>
                    <span class="text-muted-foreground w-20 shrink-0 truncate">{{ src.source_name }}</span>
                    <Button v-if="src.is_valid" variant="ghost" size="icon" class="h-6 w-6 shrink-0" @click="openPlayer(item.name, src.url)">
                      <PlayCircle class="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </div>
              <div v-if="resultStore.checkResults.length === 0" class="text-center text-muted-foreground py-12">暂无数据</div>
            </div>

            <div v-else class="rounded-lg border overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b bg-muted/50">
                    <th class="h-10 px-3 text-left font-medium text-muted-foreground w-16">#</th>
                    <th class="h-10 px-3 text-left font-medium text-muted-foreground">频道名</th>
                    <th class="h-10 px-3 text-left font-medium text-muted-foreground hidden md:table-cell">分组</th>
                    <th class="h-10 px-3 text-center font-medium text-muted-foreground w-20">状态</th>
                    <th class="h-10 px-3 text-center font-medium text-muted-foreground w-24">延迟</th>
                    <th class="h-10 px-3 text-center font-medium text-muted-foreground w-24 hidden sm:table-cell">速度</th>
                    <th class="h-10 px-3 text-center font-medium text-muted-foreground w-16">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in resultStore.checkResults" :key="item.index"
                    class="border-b transition-colors hover:bg-accent/50"
                    :class="item.is_valid ? 'border-l-2 border-l-success' : 'border-l-2 border-l-destructive'"
                  >
                    <td class="px-3 py-2.5 text-muted-foreground">{{ item.index }}</td>
                    <td class="px-3 py-2.5">
                      <div class="font-medium">{{ item.name }}</div>
                      <div class="text-xs text-muted-foreground truncate max-w-[200px] md:max-w-[300px] cursor-pointer hover:underline"
                        :title="item.url" @click="copyUrl(item.url)">{{ item.url }}</div>
                    </td>
                    <td class="px-3 py-2.5 hidden md:table-cell">
                      <Badge variant="outline" class="text-xs">{{ item.group || '未分组' }}</Badge>
                    </td>
                    <td class="px-3 py-2.5 text-center">
                      <Badge :variant="item.is_valid ? 'success' : 'destructive'" class="text-xs">
                        {{ item.is_valid ? '有效' : '无效' }}
                      </Badge>
                    </td>
                    <td class="px-3 py-2.5 text-center">{{ item.latency }}</td>
                    <td class="px-3 py-2.5 text-center hidden sm:table-cell">{{ item.speed || '-' }}</td>
                    <td class="px-3 py-2.5 text-center">
                      <div class="flex items-center justify-center gap-1">
                        <Button variant="ghost" size="icon" class="h-8 w-8" @click="openEpg(item)">
                          <Calendar class="h-4 w-4" />
                        </Button>
                        <Button v-if="item.is_valid" variant="ghost" size="icon" class="h-8 w-8" @click="openPlayer(item.name, item.url)">
                          <PlayCircle class="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="resultStore.checkResults.length === 0">
                    <td colspan="7" class="px-3 py-12 text-center text-muted-foreground">暂无数据</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="flex items-center justify-between">
              <div class="text-sm text-muted-foreground">第 {{ resultStore.resultsPage }} 页 · 共 {{ totalPages }} 页</div>
              <div class="flex gap-1">
                <Button variant="outline" size="icon" class="h-8 w-8" :disabled="resultStore.resultsPage <= 1" @click="changePage(resultStore.resultsPage - 1)">
                  <ChevronLeft class="h-4 w-4" />
                </Button>
                <Button v-for="p in visiblePages" :key="p" variant="outline" size="sm" class="h-8 min-w-[2rem]"
                  :class="p === resultStore.resultsPage ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
                  @click="changePage(p)">{{ p }}</Button>
                <Button variant="outline" size="icon" class="h-8 w-8" :disabled="resultStore.resultsPage >= totalPages" @click="changePage(resultStore.resultsPage + 1)">
                  <ChevronRight class="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <ExportDialog v-model:open="showExport" />
    <Dialog v-model:open="showEpg">
      <DialogHeader><DialogTitle>节目单</DialogTitle></DialogHeader>
      <EpgGuide v-if="epgChannel" :channel-name="epgChannel.name" :tvg-id="epgChannel.tvg_id || ''" :tvg-name="epgChannel.tvg_name || ''" @close="showEpg = false" />
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search, ArrowLeft, Wand2, Download, PlayCircle,
  ChevronLeft, ChevronRight, ChevronDown, Calendar,
  History,
} from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { useResultStore } from '../stores/result'
import { useCheckStore } from '../stores/check'
import { smartOptimize, getCategoryTree, getSourceHealth, getAvailableLanguages, getCheckHistory } from '../api'
import { useToast } from '../composables/useToast'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'
import ExportDialog from '../components/ExportDialog.vue'
import EpgGuide from '../components/EpgGuide.vue'

const store = useAppStore()
const resultStore = useResultStore()
const checkStore = useCheckStore()
const router = useRouter()
const { toast } = useToast()
const showExport = ref(false)
const showEpg = ref(false)
const epgChannel = ref(null)
let searchTimer = null

const viewMode = ref('grouped')
const categoryTree = ref([])
const sourceHealth = ref([])
const selectedRegion = ref('')
const selectedGroup = ref('')
const expandedRegion = ref('')
const expandedChannels = ref(new Set())
const mediaType = ref('all')
const selectedLanguage = ref('')
const availableLanguages = ref([])

const mediaTypes = [
  { value: 'all', label: '全部' },
  { value: 'tv', label: '电视' },
  { value: 'radio', label: '广播' },
]

const breadcrumb = computed(() => {
  const parts = []
  if (selectedRegion.value) parts.push(selectedRegion.value)
  if (selectedGroup.value) parts.push(selectedGroup.value)
  return parts
})

const tabs = computed(() => [
  { value: 'all', label: '全部', count: checkStore.checkTotal },
  { value: 'valid', label: '有效', count: checkStore.validCount },
  { value: 'invalid', label: '无效', count: checkStore.invalidCount },
])

const totalPages = computed(() => Math.ceil(resultStore.resultsTotal / resultStore.resultsPerPage) || 1)
const visiblePages = computed(() => {
  const pages = []
  const maxVisible = 7
  let start = Math.max(1, resultStore.resultsPage - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages.value, start + maxVisible - 1)
  if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { resultStore.setPage(1); doFetch() }, 400)
}

function switchTab(tab) {
  resultStore.setTab(tab)
  doFetch()
}

function switchViewMode(mode) {
  viewMode.value = mode
  resultStore.setPage(1)
  doFetch()
}

function switchMediaType(type) {
  mediaType.value = type
  resultStore.setPage(1)
  doFetch()
  loadCategoryTree()
}

function changePage(page) {
  resultStore.setPage(page)
  doFetch()
}

function selectRegion(regionName) {
  if (expandedRegion.value === regionName && selectedRegion.value === regionName && !selectedGroup.value) {
    expandedRegion.value = ''
    selectedRegion.value = ''
    resultStore.setPage(1)
    doFetch()
    return
  }
  selectedRegion.value = regionName
  selectedGroup.value = ''
  expandedRegion.value = regionName
  resultStore.setPage(1)
  doFetch()
}

function selectGroup(regionName, groupName) {
  selectedRegion.value = regionName
  selectedGroup.value = groupName
  resultStore.setPage(1)
  doFetch()
}

function clearSelection() {
  selectedRegion.value = ''
  selectedGroup.value = ''
  expandedRegion.value = ''
  resultStore.setPage(1)
  doFetch()
}

function toggleExpand(name) {
  const s = new Set(expandedChannels.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedChannels.value = s
}

function playRecommended(item) {
  const idx = item.recommended_source_idx
  if (idx >= 0 && item.sources && item.sources[idx]) {
    openPlayer(item.name, item.sources[idx].url, item.sources)
  }
}

function openPlayer(name, url, sources) {
  const encoded = btoa(encodeURIComponent(url))
  let playerUrl = `/player?url=${encoded}&name=${encodeURIComponent(name)}`
  if (sources && sources.length > 1) {
    const srcData = sources.map((s, i) => ({
      url: s.url,
      is_valid: s.is_valid,
      latency: s.latency,
      recommended: i === (sources.recommended_source_idx ?? 0),
    }))
    playerUrl += `&sources=${btoa(JSON.stringify(srcData))}`
  }
  window.open(playerUrl, '_blank')
}

function openEpg(item) {
  epgChannel.value = item
  showEpg.value = true
}

async function copyUrl(url) {
  try {
    await navigator.clipboard.writeText(url)
    toast.success('已复制', 'URL 已复制到剪贴板')
  } catch { toast.error('复制失败', '无法访问剪贴板') }
}

async function doOptimize() {
  try {
    const { data } = await smartOptimize()
    toast.success('优选完成', `移除 ${data.removed} 个重复/无效频道`)
    doFetch()
  } catch (e) { console.error(e) }
}

function doFetch() {
  if (checkStore.isChecking && resultStore.checkResults.length > 0) {
    return
  }
  resultStore.fetchResults({
    view_mode: viewMode.value,
    group_path: selectedGroup.value || '',
    sort: 'best',
    media_type: mediaType.value,
    language: selectedLanguage.value || '',
  })
}

async function loadCategoryTree() {
  try {
    const { data } = await getCategoryTree({ media_type: mediaType.value })
    categoryTree.value = data
  } catch {}
}

async function loadSourceHealth() {
  try {
    const { data } = await getSourceHealth()
    sourceHealth.value = data
  } catch {}
}

async function loadLanguages() {
  try {
    const { data } = await getAvailableLanguages()
    availableLanguages.value = data
  } catch {}
}

function switchLanguage(lang) {
  selectedLanguage.value = lang
  resultStore.setPage(1)
  doFetch()
}

const historyList = ref([])
const currentSessionId = ref('')

const historyApi = async () => {
  try {
    const res = await getCheckHistory()
    historyList.value = res.data || []
    if (historyList.value.length > 0 && !currentSessionId.value) {
      currentSessionId.value = historyList.value[0].session_id
    }
  } catch (e) {
    console.error('加载历史记录失败:', e)
  }
}

async function loadHistorySession(sessionId) {
  currentSessionId.value = sessionId
  toast.success('已切换', '加载历史检测结果')
  resultStore.fetchResults({
    session_id: sessionId,
    view_mode: viewMode.value,
    group_path: selectedGroup.value || '',
    sort: 'best',
    media_type: mediaType.value,
    language: selectedLanguage.value || '',
  })
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

watch(() => resultStore.resultsPerPage, () => { resultStore.setPage(1); doFetch() })

watch([selectedRegion, selectedGroup, viewMode], () => { doFetch() }, { deep: true })

onMounted(async () => {
  await Promise.all([doFetch(), loadCategoryTree(), loadSourceHealth(), loadLanguages(), historyApi()])
})
</script>
