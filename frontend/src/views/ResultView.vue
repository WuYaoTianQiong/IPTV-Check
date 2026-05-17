<template>
  <div class="space-y-6">
    <div class="p-6 bg-card rounded-xl border flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <h3 class="font-bold text-base">📊 本次检测大盘总结报告</h3>
        <p class="text-sm text-muted-foreground mt-1">
          检测完成：其中<span class="text-success font-bold mx-1">可用 {{ checkStore.validCount }} 个</span>，无效 {{ checkStore.invalidCount }} 个。
        </p>
      </div>
      <Button @click="handleSmartOptimize" class="gap-2">
        <Wand2 class="w-4 h-4" />
        🪄 智能一键优选并去重
      </Button>
    </div>

    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">检测结果</h1>
        <p class="text-muted-foreground mt-1">
          共 {{ resultStore.resultsTotal }} 个频道 · 有效 {{ checkStore.validCount }} · 无效 {{ checkStore.invalidCount }}
        </p>
      </div>
      <div class="flex gap-2 flex-wrap items-center">
        <select
          v-if="resultStore.history.length > 0"
          v-model="selectedSessionId"
          class="rounded border bg-card px-3 py-1.5 text-sm max-w-[220px]"
          @change="onSessionChange"
        >
          <option value="" disabled>📋 选择历史记录</option>
          <option
            v-for="h in resultStore.history"
            :key="h.session_id"
            :value="h.session_id"
          >
            {{ formatHistoryLabel(h) }}
          </option>
        </select>
        <Tabs>
          <TabButton :active="resultStore.currentTab === 'all'" @click="switchTab('all')">全部</TabButton>
          <TabButton :active="resultStore.currentTab === 'valid'" @click="switchTab('valid')">有效</TabButton>
          <TabButton :active="resultStore.currentTab === 'likely_valid'" @click="switchTab('likely_valid')">疑似有效</TabButton>
          <TabButton :active="resultStore.currentTab === 'invalid'" @click="switchTab('invalid')">无效</TabButton>
        </Tabs>
        <Button variant="outline" class="gap-2" @click="router.push('/source')">
          <ArrowLeft class="h-4 w-4" /> 返回选源
        </Button>
        <Button variant="outline" class="gap-2" @click="showExport = true">
          <Download class="h-4 w-4" /> 导出
        </Button>
      </div>
    </div>

        <Card>
          <CardContent class="p-4 space-y-4">
            <!-- 基础筛选区域 -->
            <div class="flex items-center gap-3 mb-2">
              <div class="relative flex-1">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input v-model="resultStore.searchQuery" placeholder="搜索频道..." class="pl-9" @input="onSearch" />
              </div>
              <Select v-model="mediaType" @change="switchMediaType">
                <option value="all">全部</option>
                <option value="tv">电视</option>
                <option value="radio">广播</option>
              </Select>
              <Button variant="outline" size="sm" @click="showAdvancedFilter = !showAdvancedFilter">
                <Filter class="h-4 w-4 mr-1" /> 高级筛选
              </Button>
            </div>

            <!-- 高级筛选面板 -->
            <div v-if="showAdvancedFilter" class="bg-muted/20 rounded-lg p-4 border space-y-3">
              <!-- 数据覆盖提示 -->
              <div v-if="dataCoverageHint" class="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-sm text-amber-700 dark:text-amber-400">
                <span class="font-medium">💡 提示：</span>{{ dataCoverageHint }}
                <Button variant="link" size="sm" class="px-1 text-amber-600 dark:text-amber-300 underline" @click="router.push('/source')">去选源</Button>
              </div>
              <div class="space-y-4">
                <!-- 国家/地区筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">国家/地区</label>
                  <div class="flex flex-wrap gap-2">
                    <Badge
                      v-for="country in availableCountries"
                      :key="country.code"
                      :variant="selectedCountries.includes(country.code) ? 'default' : 'outline'"
                      class="cursor-pointer"
                      @click="toggleCountry(country.code)"
                    >
                      {{ country.emoji }} {{ country.name }}
                    </Badge>
                    <Input
                      v-model="countrySearch"
                      placeholder="搜索国家..."
                      class="text-xs h-8"
                      @input="onCountrySearch"
                    />
                  </div>
                  <!-- 中国二级：省级行政区联动 -->
                  <div v-if="showRegionPanel && dynamicRegions.length > 0" class="ml-4 mt-2 space-y-1">
                    <label class="text-xs font-medium text-muted-foreground">省级行政单位 / 直辖市</label>
                    <div class="flex flex-wrap gap-1.5">
                      <Badge
                        v-for="region in dynamicRegions"
                        :key="region.code"
                        :variant="selectedRegion === region.code ? 'default' : 'outline'"
                        class="cursor-pointer text-xs"
                        @click="toggleRegion(region.code)"
                      >
                        {{ region.name }}
                        <span class="ml-1 opacity-60">({{ region.valid }}/{{ region.count }})</span>
                      </Badge>
                      <Button variant="ghost" size="sm" class="text-xs h-6 px-2" @click="selectedRegion = ''">清空</Button>
                    </div>
                  </div>
                </div>

                <!-- 内容分类筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">内容分类</label>
                  <div class="flex flex-wrap gap-2">
                    <Badge
                      v-for="cat in categoryOptions"
                      :key="cat.value"
                      :variant="selectedCategory === cat.value ? 'default' : 'outline'"
                      class="cursor-pointer"
                      @click="selectCategory(cat.value)"
                    >
                      {{ cat.label }}
                    </Badge>
                    <Button variant="ghost" size="sm" @click="selectedCategory = ''">清空</Button>
                  </div>
                </div>

                <!-- 画质筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">画质</label>
                  <div class="flex flex-wrap gap-2">
                    <Badge
                      v-for="q in qualityOptions"
                      :key="q.value"
                      :variant="selectedQuality === q.value ? 'default' : 'outline'"
                      class="cursor-pointer"
                      @click="selectQuality(q.value)"
                    >
                      {{ q.label }}
                    </Badge>
                    <Button variant="ghost" size="sm" @click="selectedQuality = ''">清空</Button>
                  </div>
                </div>

                <!-- 协议筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">协议</label>
                  <div class="flex flex-wrap gap-2">
                    <Badge
                      v-for="p in protocolOptions"
                      :key="p.value"
                      :variant="selectedProtocol === p.value ? 'default' : 'outline'"
                      class="cursor-pointer"
                      @click="selectProtocol(p.value)"
                    >
                      {{ p.label }}
                    </Badge>
                    <Button variant="ghost" size="sm" @click="selectedProtocol = ''">清空</Button>
                  </div>
                </div>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 延迟范围筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">延迟范围 (ms)</label>
                  <div class="flex items-center gap-2">
                    <Input
                      v-model.number="latencyMin"
                      type="number"
                      placeholder="最小值"
                      class="h-8 text-xs"
                      min="0"
                      @input="onLatencyChange"
                    />
                    <span class="text-muted-foreground">~</span>
                    <Input
                      v-model.number="latencyMax"
                      type="number"
                      placeholder="最大值"
                      class="h-8 text-xs"
                      min="0"
                      @input="onLatencyChange"
                    />
                    <Button variant="ghost" size="sm" @click="clearLatency">清空</Button>
                  </div>
                </div>

                <!-- 速度范围筛选 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">速度范围 (Kbps)</label>
                  <div class="flex items-center gap-2">
                    <Input
                      v-model.number="speedMin"
                      type="number"
                      placeholder="最小值"
                      class="h-8 text-xs"
                      min="0"
                      @input="onSpeedChange"
                    />
                    <span class="text-muted-foreground">~</span>
                    <Input
                      v-model.number="speedMax"
                      type="number"
                      placeholder="最大值"
                      class="h-8 text-xs"
                      min="0"
                      @input="onSpeedChange"
                    />
                    <Button variant="ghost" size="sm" @click="clearSpeed">清空</Button>
                  </div>
                </div>
              </div>

              <!-- 筛选操作按钮 -->
              <div class="flex justify-between items-center pt-2 border-t">
                <div class="text-xs text-muted-foreground">
                  <template v-if="hasActiveFilters">
                    已激活 {{ activeFilterCount }} 个筛选条件
                  </template>
                  <template v-else>
                    无激活的筛选条件
                  </template>
                </div>
                <div class="flex gap-2">
                  <Button variant="outline" size="sm" @click="clearAllFilters">清除所有筛选</Button>
                  <Button variant="default" size="sm" @click="applyAdvancedFilters">应用筛选</Button>
                </div>
              </div>
            </div>

        <div v-if="resultStore.isLoading" class="space-y-3">
          <div v-for="i in 5" :key="i" class="h-12 rounded-lg bg-muted animate-pulse" />
        </div>

        <div v-else-if="resultStore.checkResults.length === 0" class="text-center py-12 text-muted-foreground">
          <BarChart3 class="h-12 w-12 mx-auto mb-3 opacity-50" />
          <p class="text-sm">暂无检测结果</p>
          <Button variant="outline" size="sm" class="mt-4" @click="router.push('/source')">去选源检测</Button>
        </div>

        <div v-else class="rounded-lg border overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b bg-muted/50">
                <th class="h-10 px-3 text-left font-medium text-muted-foreground">#</th>
                <th class="h-10 px-3 text-left font-medium text-muted-foreground">频道名</th>
                <th class="h-10 px-3 text-left font-medium text-muted-foreground hidden md:table-cell">分组</th>
                <th class="h-10 px-3 text-center font-medium text-muted-foreground">状态</th>
                <th class="h-10 px-3 text-center font-medium text-muted-foreground hidden sm:table-cell">延迟</th>
                <th class="h-10 px-3 text-center font-medium text-muted-foreground w-20">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, idx) in resultStore.checkResults" :key="item.name"
                class="border-b transition-colors hover:bg-accent/50"
              >
                <td class="px-3 py-2.5 text-muted-foreground">{{ idx + 1 }}</td>
                <td class="px-3 py-2.5">
                  <div class="flex items-center gap-1.5">
                    <span class="font-medium">{{ item.name }}</span>
                    <Badge
                      v-if="item.resolution"
                      variant="outline"
                      class="text-[10px] shrink-0 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                    >
                      {{ item.resolution }}
                    </Badge>
                  </div>
                </td>
                <td class="px-3 py-2.5 text-xs text-muted-foreground hidden md:table-cell">{{ item.group || '-' }}</td>
                <td class="px-3 py-2.5 text-center">
                  <Badge
                    :variant="getItemQualityTier(item) === 'valid' ? 'success' : getItemQualityTier(item) === 'likely_valid' ? 'warning' : 'destructive'"
                    class="text-[10px]"
                  >
                    {{ getItemQualityTier(item) === 'valid' ? '有效' : getItemQualityTier(item) === 'likely_valid' ? '疑似有效' : '无效' }}
                  </Badge>
                </td>
                <td class="px-3 py-2.5 text-center text-xs text-muted-foreground hidden sm:table-cell">
                  {{ (item.latency && item.latency !== '-') ? item.latency + 'ms' : '-' }}
                </td>
                <td class="px-3 py-2.5 text-center">
                  <Button variant="ghost" size="icon" class="h-7 w-7" @click="openPlayer(item)">
                    <Play class="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="flex items-center justify-between pt-2">
          <span class="text-xs text-muted-foreground">
            第 {{ resultStore.resultsPage }} 页 / 共 {{ totalPages }} 页
          </span>
          <div class="flex gap-1">
            <Button variant="outline" size="sm" :disabled="resultStore.resultsPage <= 1" @click="changePage(resultStore.resultsPage - 1)">上一页</Button>
            <Button variant="outline" size="sm" :disabled="resultStore.resultsPage >= totalPages" @click="changePage(resultStore.resultsPage + 1)">下一页</Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Dialog v-model:open="showExport">
      <DialogHeader><DialogTitle>导出检测结果</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <p class="text-sm text-muted-foreground">选择导出格式</p>
        <div class="flex gap-2">
          <Button class="flex-1 gap-2" @click="doExport('m3u')"><Download class="h-4 w-4" /> M3U</Button>
          <Button variant="outline" class="flex-1 gap-2" @click="doExport('txt')"><Download class="h-4 w-4" /> TXT</Button>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Wand2, ArrowLeft, Download, Search, BarChart3, Play, Filter } from 'lucide-vue-next'
import { useCheckStore } from '../stores/check'
import { useResultStore } from '../stores/result'
import { smartOptimize, exportResults, getAvailableCountries, getAvailableRegions, getCategoryTree } from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { Tabs, TabButton } from '../components/ui/tabs'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'

const checkStore = useCheckStore()
const resultStore = useResultStore()
const router = useRouter()
const { toast } = useToast()

const showExport = ref(false)
const mediaType = ref('all')
const viewMode = ref('grouped')
const showAdvancedFilter = ref(false)
const countrySearch = ref('')
const selectedCountries = ref([])
const selectedCategory = ref('')
const selectedQuality = ref('')
const selectedProtocol = ref('')
const latencyMin = ref('')
const latencyMax = ref('')
const speedMin = ref('')
const speedMax = ref('')
const dynamicCountries = ref([])
const dynamicRegions = ref([])
const showRegionPanel = ref(false)
const selectedRegion = ref('')
const categoryTree = ref([])
const selectedSessionId = ref('')
let searchTimer = null

const staticCountries = [
  { code: 'CN', name: '中国', emoji: '🇨🇳' },
  { code: 'US', name: '美国', emoji: '🇺🇸' },
  { code: 'GB', name: '英国', emoji: '🇬🇧' },
  { code: 'JP', name: '日本', emoji: '🇯🇵' },
  { code: 'KR', name: '韩国', emoji: '🇰🇷' },
  { code: 'FR', name: '法国', emoji: '🇫🇷' },
  { code: 'DE', name: '德国', emoji: '🇩🇪' },
  { code: 'IT', name: '意大利', emoji: '🇮🇹' },
  { code: 'ES', name: '西班牙', emoji: '🇪🇸' },
  { code: 'AU', name: '澳大利亚', emoji: '🇦🇺' },
  { code: 'CA', name: '加拿大', emoji: '🇨🇦' },
  { code: 'IN', name: '印度', emoji: '🇮🇳' },
  { code: 'BR', name: '巴西', emoji: '🇧🇷' },
  { code: 'RU', name: '俄罗斯', emoji: '🇷🇺' },
  { code: 'SG', name: '新加坡', emoji: '🇸🇬' },
  { code: 'MY', name: '马来西亚', emoji: '🇲🇾' },
  { code: 'TH', name: '泰国', emoji: '🇹🇭' },
  { code: 'AE', name: '阿联酋', emoji: '🇦🇪' },
]

// 内容分类选项
const categoryOptions = [
  { value: '', label: '全部' },
  { value: '央视', label: '央视' },
  { value: '卫视', label: '卫视' },
  { value: '地方', label: '地方' },
  { value: '国际电视', label: '国际电视' },
  { value: '专题', label: '专题频道' },
  { value: '未分类', label: '未分类' },
]

// 画质选项
const qualityOptions = [
  { value: '', label: '全部' },
  { value: '4K', label: '4K超清' },
  { value: 'HD', label: '高清' },
  { value: 'SD', label: '标清' },
]

// 协议选项
const protocolOptions = [
  { value: '', label: '全部' },
  { value: 'IPv6', label: 'IPv6' },
  { value: 'IPv4', label: 'IPv4' },
]

const totalPages = computed(() => Math.ceil(resultStore.resultsTotal / resultStore.resultsPerPage) || 1)

// 计算属性
const availableCountries = computed(() => {
  const cnSubCodes = ['HK', 'MO', 'TW']
  let source = dynamicCountries.value.length > 0 ? dynamicCountries.value : staticCountries
  source = source.filter(c => !cnSubCodes.includes(c.code))
  if (!countrySearch.value) return source
  const search = countrySearch.value.toLowerCase()
  return source.filter(country => 
    country.name.toLowerCase().includes(search) || 
    country.code.toLowerCase().includes(search)
  )
})

const dataCoverageHint = computed(() => {
  if (categoryTree.value.length === 0 && dynamicCountries.value.length === 0) return ''
  
  const hasInternationalChannels = 
    categoryTree.value.some(c => c.name === '国际电视') ||
    dynamicCountries.value.some(c => c.code && !['CN', 'HK', 'MO', 'TW'].includes(c.code))
  
  const hasRadioChannels = 
    categoryTree.value.some(c => c.name === '广播')
  
  const hints = []
  if (!hasInternationalChannels) {
    hints.push('当前数据不含国际频道，如需查看国外电视请勾选"国际电视"分类的在线源后重新检测')
  }
  if (!hasRadioChannels && !hasInternationalChannels) {
    hints.push('当前数据不含广播频道，如需听广播请勾选"广播电台"分类的在线源后重新检测')
  }
  return hints.join('；')
})

const hasActiveFilters = computed(() => {
  return selectedCountries.value.length > 0 || 
         selectedRegion.value !== '' ||
         selectedCategory.value !== '' || 
         selectedQuality.value !== '' || 
         selectedProtocol.value !== '' || 
         latencyMin.value !== '' || 
         latencyMax.value !== '' || 
         speedMin.value !== '' || 
         speedMax.value !== ''
})

const activeFilterCount = computed(() => {
  let count = 0
  if (selectedCountries.value.length > 0) count++
  if (selectedRegion.value !== '') count++
  if (selectedCategory.value !== '') count++
  if (selectedQuality.value !== '') count++
  if (selectedProtocol.value !== '') count++
  if (latencyMin.value !== '' || latencyMax.value !== '') count++
  if (speedMin.value !== '' || speedMax.value !== '') count++
  return count
})

onMounted(async () => {
  await resultStore.fetchHistory()
  if (resultStore.selectedSessionId) {
    selectedSessionId.value = resultStore.selectedSessionId
  }
  const initialFilters = {
    media_type: mediaType.value,
    view_mode: viewMode.value,
  }
  resultStore.fetchResults(initialFilters)
  try {
    const { data } = await getAvailableCountries()
    if (data && data.length > 0) {
      dynamicCountries.value = data.map(c => ({
        code: c.code,
        name: c.name,
        emoji: c.flag || '',
        count: c.count,
        valid: c.valid,
      }))
    }
  } catch (e) {
    // 使用静态列表作为后备
  }
  try {
    const { data } = await getAvailableRegions()
    if (data && data.length > 0) {
      dynamicRegions.value = data
    }
  } catch (e) {
    // ignore
  }
  try {
    const { data } = await getCategoryTree()
    if (data) categoryTree.value = data
  } catch (e) {
    // ignore
  }
})

function formatHistoryLabel(h) {
  const date = h.created_at ? new Date(h.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未知时间'
  const validRate = h.total > 0 ? Math.round((h.valid / h.total) * 100) : 0
  return `${date} | ${h.total}频道 | 有效${validRate}%`
}

function onSessionChange() {
  resultStore.selectSession(selectedSessionId.value)
  resultStore.setPage(1)
  applyAdvancedFilters()
}

watch(() => resultStore.selectedSessionId, (newVal) => {
  if (newVal && newVal !== selectedSessionId.value) {
    selectedSessionId.value = newVal
  }
})

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    resultStore.setPage(1)
    applyAdvancedFilters()
  }, 400)
}

function toggleCountry(countryCode) {
  const index = selectedCountries.value.indexOf(countryCode)
  if (index > -1) {
    selectedCountries.value.splice(index, 1)
    if (countryCode === 'CN') {
      showRegionPanel.value = false
      selectedRegion.value = ''
    }
  } else {
    selectedCountries.value.push(countryCode)
    if (countryCode === 'CN') {
      showRegionPanel.value = true
    }
  }
}

function toggleRegion(regionCode) {
  if (selectedRegion.value === regionCode) {
    selectedRegion.value = ''
  } else {
    selectedRegion.value = regionCode
  }
}

function onCountrySearch() {
  // 搜索国家时无需立即触发筛选
}

function selectCategory(cat) {
  selectedCategory.value = cat
}

function selectQuality(q) {
  selectedQuality.value = q
}

function selectProtocol(p) {
  selectedProtocol.value = p
}

function onLatencyChange() {
  // 延迟变化时无需立即触发筛选
}

function onSpeedChange() {
  // 速度变化时无需立即触发筛选
}

function clearLatency() {
  latencyMin.value = ''
  latencyMax.value = ''
}

function clearSpeed() {
  speedMin.value = ''
  speedMax.value = ''
}

function clearAllFilters() {
  selectedCountries.value = []
  selectedRegion.value = ''
  showRegionPanel.value = false
  selectedCategory.value = ''
  selectedQuality.value = ''
  selectedProtocol.value = ''
  latencyMin.value = ''
  latencyMax.value = ''
  speedMin.value = ''
  speedMax.value = ''
  countrySearch.value = ''
  mediaType.value = 'all'
  viewMode.value = 'grouped'
  applyAdvancedFilters()
}

function applyAdvancedFilters() {
  const filters = {}
  
  // 基础筛选
  filters.media_type = mediaType.value
  filters.view_mode = viewMode.value
  
  // 国家筛选
  if (selectedCountries.value.length > 0) {
    filters.country = selectedCountries.value.join(',')
  }
  
  // 地区筛选（仅中国二级）
  if (selectedRegion.value !== '') {
    filters.region = selectedRegion.value
  }
  
  // 内容分类筛选
  if (selectedCategory.value !== '') {
    filters.category = selectedCategory.value
  }
  
  // 画质筛选
  if (selectedQuality.value !== '') {
    filters.quality = selectedQuality.value
  }
  
  // 协议筛选
  if (selectedProtocol.value !== '') {
    filters.protocol = selectedProtocol.value
  }
  
  // 延迟范围筛选
  if (latencyMin.value !== '' && latencyMin.value !== null && !isNaN(latencyMin.value)) {
    filters.latency_min = parseFloat(latencyMin.value)
  }
  if (latencyMax.value !== '' && latencyMax.value !== null && !isNaN(latencyMax.value)) {
    filters.latency_max = parseFloat(latencyMax.value)
  }
  
  // 速度范围筛选
  if (speedMin.value !== '' && speedMin.value !== null && !isNaN(speedMin.value)) {
    filters.speed_min = parseFloat(speedMin.value)
  }
  if (speedMax.value !== '' && speedMax.value !== null && !isNaN(speedMax.value)) {
    filters.speed_max = parseFloat(speedMax.value)
  }
  
  resultStore.setPage(1)
  resultStore.fetchResults(filters)
}

function switchTab(tab) {
  resultStore.setTab(tab)
  resultStore.setPage(1)
  applyAdvancedFilters()
}

function switchMediaType() {
  resultStore.setPage(1)
  applyAdvancedFilters()
}

function changePage(page) {
  resultStore.setPage(page)
  applyAdvancedFilters()
}

async function handleSmartOptimize() {
  try {
    const { data } = await smartOptimize()
    toast.success('智能优选完成', `已帮您去重，移除 ${data.removed} 个重复/无效频道`)
    resultStore.fetchResults()
  } catch (e) {
    toast.error('优选失败', e.response?.data?.detail || e.message)
  }
}

function openPlayer(item) {
  const url = item.url || (item.sources && item.sources[item.recommended_source_idx ?? 0]?.url) || ''
  if (!url) return
  const encoded = btoa(encodeURIComponent(url))
  window.open(`/player?url=${encoded}&name=${encodeURIComponent(item.name)}`, '_blank')
}

async function doExport(format) {
  showExport.value = false
  try {
    const { data } = await exportResults({ format })
    const filename = format === 'm3u' ? 'results.m3u' : 'results.txt'
    downloadBlob(data, filename, format === 'm3u' ? 'audio/x-mpegurl' : 'text/plain')
    toast.success('导出成功')
  } catch (e) {
    toast.error('导出失败')
  }
}

function downloadBlob(data, filename, mimeType) {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function getItemQualityTier(item) {
  if (item.quality_tier) return item.quality_tier
  if (item.is_valid || item.has_valid) return 'valid'
  return 'invalid'
}
</script>
