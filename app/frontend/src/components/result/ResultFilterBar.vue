<template>
  <div class="sticky top-0 z-30 bg-background/95 backdrop-blur-sm border-b border-border/40 -mx-4 sm:-mx-6 px-4 sm:px-6 pb-3 pt-3 space-y-3">
    <!-- 第一行：搜索 + 历史 -->
    <div class="flex items-center gap-3">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          :model-value="search"
          placeholder="搜索频道名..."
          class="pl-9 h-9"
          @update:model-value="$emit('update:search', $event); $emit('search')"
        />
      </div>
      <select
        v-if="history.length > 0"
        :value="selectedSessionId"
        class="h-9 rounded-md border border-input bg-background px-3 text-sm max-w-[200px]"
        @change="$emit('update:selectedSessionId', $event.target.value)"
      >
        <option value="" disabled>📋 选择历史记录</option>
        <option
          v-for="h in history"
          :key="h.session_id"
          :value="h.session_id"
        >
          {{ formatHistoryLabel(h) }}
        </option>
      </select>
    </div>

    <!-- 第二行：筛选标签行 -->
    <div class="flex flex-wrap items-center gap-2">
      <!-- 媒体类型 -->
      <Tabs class="shrink-0">
        <TabButton
          v-for="mt in mediaTypes" :key="mt.value"
          :active="mediaType === mt.value"
          @click="$emit('update:mediaType', mt.value)"
        >{{ mt.label }}</TabButton>
      </Tabs>

      <Separator orientation="vertical" class="h-5 hidden sm:block" />

      <!-- 状态标签 -->
      <Tabs class="shrink-0">
        <TabButton
          v-for="tab in tabs" :key="tab.value"
          :active="currentTab === tab.value"
          @click="$emit('update:currentTab', tab.value)"
        >
          {{ tab.label }}
          <Badge variant="secondary" class="ml-1 text-[10px]">{{ tab.count }}</Badge>
        </TabButton>
      </Tabs>

      <div class="flex-1" />

      <!-- 视图切换 -->
      <div class="flex items-center gap-1.5 border rounded-lg p-0.5 bg-muted/30 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          class="h-7 gap-1 text-xs"
          :class="viewMode === 'grouped' ? 'bg-background shadow-sm' : 'hover:bg-transparent'"
          @click="$emit('update:viewMode', 'grouped')"
        >
          <LayoutGrid class="h-3.5 w-3.5" />
          <span class="hidden sm:inline">聚合</span>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          class="h-7 gap-1 text-xs"
          :class="viewMode === 'flat' ? 'bg-background shadow-sm' : 'hover:bg-transparent'"
          @click="$emit('update:viewMode', 'flat')"
        >
          <List class="h-3.5 w-3.5" />
          <span class="hidden sm:inline">平铺</span>
        </Button>
      </div>

      <!-- 高级筛选 -->
      <Button variant="outline" size="sm" class="h-8 gap-1 shrink-0" @click="$emit('toggle-advanced')">
        <Filter class="h-3.5 w-3.5" />
        筛选
        <Badge v-if="activeFilterCount > 0" variant="default" class="text-[10px] h-4 px-1">{{ activeFilterCount }}</Badge>
      </Button>

      <Button variant="outline" size="sm" class="h-8 gap-1 shrink-0" @click="$emit('toggle-batch-select')">
        <Star class="h-3.5 w-3.5" />
        {{ batchSelectMode ? '退出多选' : '批量收藏' }}
      </Button>
    </div>

    <!-- 高级筛选展开面板 -->
    <div v-if="showAdvanced" class="bg-muted/20 rounded-lg border p-4 space-y-3">
      <!-- 国家/地区 -->
      <div class="space-y-2">
        <label class="text-xs font-medium text-muted-foreground">国家/地区</label>
        <div class="flex flex-wrap gap-1.5">
          <Badge
            v-for="country in availableCountries"
            :key="country.code"
            :variant="selectedCountries.includes(country.code) ? 'default' : 'outline'"
            class="cursor-pointer text-xs"
            @click="$emit('toggle-country', country.code)"
          >
            {{ country.name }}
          </Badge>
          <Input
            :model-value="countrySearch"
            placeholder="搜索国家..."
            class="text-xs h-7 w-28"
            @update:model-value="$emit('update:countrySearch', $event)"
          />
        </div>
        <!-- 中国二级区域 -->
        <div v-if="showRegionPanel && dynamicRegions.length > 0" class="ml-2 space-y-1">
          <label class="text-xs font-medium text-muted-foreground">省级行政单位 / 直辖市</label>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="region in dynamicRegions"
              :key="region.code"
              :variant="selectedRegion === region.code ? 'default' : 'outline'"
              class="cursor-pointer text-xs"
              @click="$emit('toggle-region', region.code)"
            >
              {{ region.name }}
              <span class="ml-1 opacity-60">({{ region.valid }}/{{ region.count }})</span>
            </Badge>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <!-- 分类 -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground">内容分类</label>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="cat in categoryOptions"
              :key="cat.value"
              :variant="selectedCategory === cat.value ? 'default' : 'outline'"
              class="cursor-pointer text-xs"
              @click="$emit('update:selectedCategory', cat.value)"
            >{{ cat.label }}</Badge>
          </div>
        </div>

        <!-- 画质 -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground">画质</label>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="q in qualityOptions"
              :key="q.value"
              :variant="selectedQuality === q.value ? 'default' : 'outline'"
              class="cursor-pointer text-xs"
              @click="$emit('update:selectedQuality', q.value)"
            >{{ q.label }}</Badge>
          </div>
        </div>

        <!-- 协议 -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground">协议</label>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="p in protocolOptions"
              :key="p.value"
              :variant="selectedProtocol === p.value ? 'default' : 'outline'"
              class="cursor-pointer text-xs"
              @click="$emit('update:selectedProtocol', p.value)"
            >{{ p.label }}</Badge>
          </div>
        </div>
      </div>

      <!-- 语言 -->
      <div class="space-y-2">
        <label class="text-xs font-medium text-muted-foreground">语言</label>
        <div v-if="availableLanguages.length > 0" class="flex flex-wrap gap-1.5">
          <Badge
            v-for="lang in availableLanguages"
            :key="lang.language"
            :variant="selectedLanguage === lang.language ? 'default' : 'outline'"
            class="cursor-pointer text-xs"
            @click="$emit('toggle-language', lang.language)"
          >{{ lang.language }}<span v-if="lang.count" class="ml-1 opacity-60">({{ lang.count }})</span></Badge>
        </div>
        <div v-else class="text-xs text-muted-foreground">暂无语言数据</div>
      </div>

      <!-- 来源源 -->
      <div class="space-y-2">
        <label class="text-xs font-medium text-muted-foreground">来源源</label>
        <div v-if="availableSources.length > 0" class="flex flex-wrap gap-1.5">
          <Badge
            v-for="src in availableSources"
            :key="src"
            :variant="selectedSources.includes(src) ? 'default' : 'outline'"
            class="cursor-pointer text-xs"
            @click="$emit('toggle-source', src)"
          >{{ src }}</Badge>
        </div>
        <div v-else class="text-xs text-muted-foreground">暂无来源数据</div>
      </div>

      <!-- 延迟 + 速度 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground">延迟范围 (ms)</label>
          <div class="flex items-center gap-2">
            <Input :model-value="latencyMin" type="number" placeholder="最小值" class="h-8 text-xs" min="0" @update:model-value="$emit('update:latencyMin', $event)" />
            <span class="text-muted-foreground text-xs">~</span>
            <Input :model-value="latencyMax" type="number" placeholder="最大值" class="h-8 text-xs" min="0" @update:model-value="$emit('update:latencyMax', $event)" />
          </div>
        </div>
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground">速度范围 (Kbps)</label>
          <div class="flex items-center gap-2">
            <Input :model-value="speedMin" type="number" placeholder="最小值" class="h-8 text-xs" min="0" @update:model-value="$emit('update:speedMin', $event)" />
            <span class="text-muted-foreground text-xs">~</span>
            <Input :model-value="speedMax" type="number" placeholder="最大值" class="h-8 text-xs" min="0" @update:model-value="$emit('update:speedMax', $event)" />
          </div>
        </div>
      </div>

      <div class="flex justify-between items-center pt-1 border-t">
        <span class="text-xs text-muted-foreground" v-if="activeFilterCount > 0">
          已激活 {{ activeFilterCount }} 个筛选条件
        </span>
        <span v-else class="text-xs text-muted-foreground">无激活的筛选条件</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" @click="$emit('clear-all-filters')">清除所有筛选</Button>
          <Button variant="default" size="sm" @click="$emit('apply-filters')">应用筛选</Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Search, LayoutGrid, List, Filter, Star } from 'lucide-vue-next'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Input } from '../ui/input'
import { Tabs, TabButton } from '../ui/tabs'
import { Separator } from '../ui/separator'


defineProps({
  search: { type: String, default: '' },
  currentTab: { type: String, default: 'all' },
  tabs: { type: Array, default: () => [] },
  mediaType: { type: String, default: 'all' },
  mediaTypes: { type: Array, default: () => [] },
  viewMode: { type: String, default: 'grouped' },
  selectedSessionId: { type: String, default: '' },
  history: { type: Array, default: () => [] },
  showAdvanced: { type: Boolean, default: false },
  batchSelectMode: { type: Boolean, default: false },
  activeFilterCount: { type: Number, default: 0 },

  // 高级筛选字段
  selectedCountries: { type: Array, default: () => [] },
  selectedCategory: { type: String, default: '' },
  selectedQuality: { type: String, default: '' },
  selectedProtocol: { type: String, default: '' },
  selectedRegion: { type: String, default: '' },
  selectedSources: { type: Array, default: () => [] },
  availableSources: { type: Array, default: () => [] },
  selectedLanguage: { type: String, default: '' },
  availableLanguages: { type: Array, default: () => [] },
  latencyMin: { type: [String, Number], default: '' },
  latencyMax: { type: [String, Number], default: '' },
  speedMin: { type: [String, Number], default: '' },
  speedMax: { type: [String, Number], default: '' },
  availableCountries: { type: Array, default: () => [] },
  dynamicRegions: { type: Array, default: () => [] },
  showRegionPanel: { type: Boolean, default: false },
  categoryOptions: { type: Array, default: () => [] },
  qualityOptions: { type: Array, default: () => [] },
  protocolOptions: { type: Array, default: () => [] },
  countrySearch: { type: String, default: '' },
})

defineEmits([
  'update:search', 'search',
  'update:currentTab',
  'update:mediaType',
  'update:viewMode',
  'update:selectedSessionId',
  'toggle-advanced',
  'toggle-batch-select',
  'toggle-country',
  'toggle-region',
  'toggle-source',
  'toggle-language',
  'update:selectedCategory',
  'update:selectedQuality',
  'update:selectedProtocol',
  'update:countrySearch',
  'update:latencyMin', 'update:latencyMax',
  'update:speedMin', 'update:speedMax',
  'clear-all-filters',
  'apply-filters',
])

function formatHistoryLabel(h) {
  if (!h) return ''
  const date = h.created_at ? new Date(h.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未知时间'
  const validRate = h.total > 0 ? Math.round((h.valid / h.total) * 100) : 0
  return `${date} | ${h.total}频道 | 有效${validRate}%`
}
</script>
