<template>
  <div class="space-y-6">
    <div class="p-6 bg-card rounded-xl border flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <h3 class="font-bold text-base">📊 本次检测大盘总结报告</h3>
        <p class="text-sm text-muted-foreground mt-1">
          检测完成：其中<span class="text-success font-bold mx-1">可用 {{ checkStore.validCount }} 个</span>，无效 {{ checkStore.invalidCount }} 个。
        </p>
      </div>
      <Button @click="showOptimizeDialog = true" class="gap-2">
        <Wand2 class="w-4 h-4" />
        🪄 智能一键优选并去重
      </Button>
    </div>

    <!-- 统一粘性筛选栏 -->
    <ResultFilterBar
      :search="resultStore.searchQuery"
      :current-tab="resultStore.currentTab"
      :tabs="filterTabs"
      :media-type="mediaType"
      :media-types="mediaTypes"
      :view-mode="viewMode"
      :selected-session-id="selectedSessionId"
      :history="resultStore.history"
      :show-advanced="showAdvancedFilter"
      :batch-select-mode="batchSelectMode"
      :active-filter-count="activeFilterCount"
      :selected-countries="selectedCountries"
      :selected-category="selectedCategory"
      :selected-quality="selectedQuality"
      :selected-protocol="selectedProtocol"
      :selected-region="selectedRegion"
      :latency-min="latencyMin"
      :latency-max="latencyMax"
      :speed-min="speedMin"
      :speed-max="speedMax"
      :available-countries="availableCountries"
      :dynamic-regions="dynamicRegions"
      :show-region-panel="showRegionPanel"
      :category-options="categoryOptions"
      :quality-options="qualityOptions"
      :protocol-options="protocolOptions"
      :country-search="countrySearch"
      @update:search="resultStore.searchQuery = $event"
      @search="onSearch"
      @update:current-tab="switchTab"
      @update:media-type="selectMediaType"
      @update:view-mode="(v) => viewMode = v"
      @update:selected-session-id="onSessionChangeId"
      @toggle-advanced="showAdvancedFilter = !showAdvancedFilter"
      @toggle-batch-select="toggleBatchSelectMode"
      @toggle-country="toggleCountry"
      @toggle-region="toggleRegion"
      @update:selected-category="selectedCategory = $event"
      @update:selected-quality="selectedQuality = $event"
      @update:selected-protocol="selectedProtocol = $event"
      @update:latency-min="latencyMin = $event"
      @update:latency-max="latencyMax = $event"
      @update:speed-min="speedMin = $event"
      @update:speed-max="speedMax = $event"
      @clear-all-filters="clearAllFilters"
      @apply-filters="applyAdvancedFilters"
    />

    <!-- 标题 + 操作按钮 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">检测结果</h1>
        <p class="text-muted-foreground mt-1">
          共 {{ resultStore.resultsTotal }} 个频道 · 有效 {{ checkStore.validCount }} · 无效 {{ checkStore.invalidCount }}
          <span v-if="sessionAgeText" class="ml-2 px-2 py-0.5 rounded text-xs" :class="sessionAgeUrgency.class">{{ sessionAgeText }}</span>
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" class="gap-2" @click="handleRefreshLatency" :disabled="isRefreshingLatency">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': isRefreshingLatency }" />
          {{ isRefreshingLatency ? '检测中...' : '实时检测延迟' }}
        </Button>
        <Button variant="outline" class="gap-2" @click="showExport = true">
          <Download class="h-4 w-4" /> 导出
        </Button>
      </div>
    </div>

        <Card>
          <CardContent class="p-4 space-y-4">
            <!-- 数据覆盖提示 -->
            <div v-if="dataCoverageHint" class="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-sm text-amber-700 dark:text-amber-400">
              <span class="font-medium">💡 提示：</span>{{ dataCoverageHint }}
              <Button variant="link" size="sm" class="px-1 text-amber-600 dark:text-amber-300 underline" @click="router.push('/source')">去选源</Button>
            </div>

            <!-- 批量操作栏 -->
            <div v-if="batchSelectMode" class="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
              <Button variant="outline" size="sm" @click="selectAllItems">
                {{ resultStore.checkResults.length > 0 && resultStore.checkResults.every(item => selectedItems.has(item.url)) ? '取消全选' : '全选' }}
              </Button>
              <span class="text-sm text-muted-foreground">已选 {{ selectedItems.size }} 个</span>
              <div class="flex-1" />
              <Button size="sm" @click="openBatchFavoriteDialog" :disabled="selectedItems.size === 0">
                <Star class="h-4 w-4 mr-1" /> 收藏到文件夹
              </Button>
            </div>

            <!-- 筛选条件已移至上方统一粘性筛选栏 -->

        <div v-if="resultStore.isLoading" class="space-y-3">
          <div v-for="i in 5" :key="i" class="h-12 rounded-lg bg-muted animate-pulse" />
        </div>

        <div v-else-if="resultStore.checkResults.length === 0" class="text-center py-12 text-muted-foreground">
          <BarChart3 class="h-12 w-12 mx-auto mb-3 opacity-50" />
          <p class="text-sm">暂无检测结果</p>
          <Button variant="outline" size="sm" class="mt-4" @click="router.push('/source')">去选源检测</Button>
        </div>

         <div v-else>
           <div class="hidden sm:block rounded-lg border overflow-auto">
            <table class="text-sm table-fixed w-full">
              <thead>
                <tr class="border-b bg-muted/50">
                  <th v-if="batchSelectMode" class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 40px">
                    <Checkbox
                      :model-value="resultStore.checkResults.length > 0 && resultStore.checkResults.every(item => selectedItems.has(item.url))"
                      @update:model-value="selectAllItems"
                    />
                  </th>
                  <th class="h-10 px-3 text-left font-medium text-muted-foreground whitespace-nowrap" style="width: 40%;">频道名</th>
                  <th v-if="isWideScreen" class="h-10 px-3 text-left font-medium text-muted-foreground whitespace-nowrap" style="width: 15%;">分组</th>
                  <th class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 60px">状态</th>
                  <th v-if="isMediumScreen" class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 72px">延迟</th>
                  <th v-if="isMediumScreen" class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 72px">速度</th>
                  <th class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 96px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in resultStore.checkResults" :key="item.name"
                  class="border-b transition-colors hover:bg-accent/50"
                >
                  <td v-if="batchSelectMode" class="px-3 py-2 text-center" style="width: 40px">
                    <Checkbox
                      :model-value="selectedItems.has(item.url)"
                      @update:model-value="toggleItemSelection(item.url)"
                    />
                  </td>
                  <td class="px-3 py-2.5">
                    <div class="min-w-0">
                      <div class="flex items-center gap-1.5">
                        <Badge v-if="item.country && !['CN','HK','MO','TW'].includes(item.country)" variant="secondary" class="text-[10px] shrink-0 px-1.5 py-0 h-4 bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800">{{ countryCodeToName(item.country) }}</Badge>
                        <Badge
                          :variant="item.is_radio ? 'secondary' : 'outline'"
                          class="text-[10px] shrink-0 px-1.5 py-0 h-4"
                        >{{ item.is_radio ? '广播' : '电视' }}</Badge>
                        <Badge
                          v-if="item.region"
                          variant="default"
                          class="text-[10px] shrink-0 px-1.5 py-0 h-4 bg-emerald-600 text-white dark:bg-emerald-500"
                        >{{ item.region }}</Badge>
                        <span class="font-medium truncate">{{ item.name }}</span>
                        <Badge
                          v-if="item.resolution"
                          variant="outline"
                          class="text-[10px] shrink-0 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                        >
                          {{ item.resolution }}
                        </Badge>
                      </div>
                      <div v-if="(item.name_cn && item.name_cn !== item.name) || (item.clean_name && item.clean_name !== item.name)" class="text-xs text-muted-foreground truncate mt-0.5">{{ item.name_cn || item.clean_name }}</div>
                      <span class="text-xs text-muted-foreground truncate block" :title="item.url" @click="$emit('copy-url', item.url)">{{ item.url }}</span>
                    </div>
                  </td>
                  <td v-if="isWideScreen" class="px-3 py-2.5 text-xs text-muted-foreground">
                    <div class="flex items-center gap-1">
                      <span class="truncate">{{ item.group || '-' }}</span>
                      <span v-if="item.language" class="text-[10px] text-muted-foreground/70">· {{ item.language }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <Badge
                      :variant="getItemQualityTier(item) === 'valid' ? 'success' : getItemQualityTier(item) === 'likely_valid' ? 'warning' : 'destructive'"
                      class="text-[10px] whitespace-nowrap"
                    >
                      {{ getItemQualityTier(item) === 'valid' ? '有效' : getItemQualityTier(item) === 'likely_valid' ? '疑似有效' : '无效' }}
                    </Badge>
                  </td>
                  <td v-if="isMediumScreen" class="px-3 py-2.5 text-center whitespace-nowrap" style="width: 72px">
                    <LatencyBadge :latency="getLiveLatency(item)?.latency ?? item.latency" />
                    <span v-if="getLiveLatency(item)" class="text-[10px] text-green-600 dark:text-green-400 ml-0.5">●</span>
                  </td>
                  <td v-if="isMediumScreen" class="px-3 py-2.5 text-center text-xs text-muted-foreground whitespace-nowrap" style="width: 72px">
                    {{ formatSpeed(item.speed) }}
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <div class="flex items-center justify-center gap-1">
                      <Button variant="ghost" size="icon" class="h-7 w-7" @click="openPlayer(item)" title="播放">
                        <Play class="h-4 w-4" />
                      </Button>
                      <div class="relative inline-flex">
                        <Button variant="ghost" size="icon" class="h-7 w-7" @click="handleToggleFavorite(item)" :title="favoriteStore.isFavorite(item.url) ? '取消收藏' : '收藏'">
                          <Star v-if="favoriteStore.isFavorite(item.url)" class="h-4 w-4 fill-primary text-primary" />
                          <Star v-else class="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" class="h-7 w-3 px-0 -ml-1" @click="openFavoriteDropdown(item, $event.target.closest('button'))" title="选择收藏夹">
                          <ChevronDown class="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="sm:hidden space-y-2">
            <div
              v-for="(item, idx) in resultStore.checkResults" :key="'m-'+item.name"
              class="flex items-center gap-3 p-3 rounded-lg border bg-card"
            >
              <Checkbox
                v-if="batchSelectMode"
                :model-value="selectedItems.has(item.url)"
                @update:model-value="toggleItemSelection(item.url)"
                class="shrink-0"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <Badge v-if="item.country && !['CN','HK','MO','TW'].includes(item.country)" variant="secondary" class="text-[10px] shrink-0 px-1.5 py-0 h-4 bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800">{{ countryCodeToName(item.country) }}</Badge>
                  <Badge
                    :variant="item.is_radio ? 'secondary' : 'outline'"
                    class="text-[10px] shrink-0 px-1.5 py-0 h-4"
                  >{{ item.is_radio ? '广播' : '电视' }}</Badge>
                  <span class="font-medium text-sm truncate">{{ item.name }}</span>
                  <Badge
                    v-if="item.resolution"
                    variant="outline"
                    class="text-[10px] shrink-0 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                  >
                    {{ item.resolution }}
                  </Badge>
                </div>
                <div v-if="(item.name_cn && item.name_cn !== item.name) || (item.clean_name && item.clean_name !== item.name)" class="text-xs text-muted-foreground truncate mt-0.5">{{ item.name_cn || item.clean_name }}</div>
                <div class="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <span v-if="item.group">{{ item.group }}</span>
                  <LatencyBadge :latency="getLiveLatency(item)?.latency ?? item.latency" />
                  <span v-if="getLiveLatency(item)" class="text-[10px] text-green-600 dark:text-green-400">●</span>
                  <span v-if="item.speed && item.speed !== '-'">{{ formatSpeed(item.speed) }}</span>
                </div>
              </div>
              <Badge
                :variant="getItemQualityTier(item) === 'valid' ? 'success' : getItemQualityTier(item) === 'likely_valid' ? 'warning' : 'destructive'"
                class="text-[10px] shrink-0"
              >
                {{ getItemQualityTier(item) === 'valid' ? '有效' : getItemQualityTier(item) === 'likely_valid' ? '疑似有效' : '无效' }}
              </Badge>
              <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" @click="openPlayer(item)">
                <Play class="h-4 w-4" />
              </Button>
              <div class="relative inline-flex">
                <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" @click="handleToggleFavorite(item)" :title="favoriteStore.isFavorite(item.url) ? '取消收藏' : '收藏'">
                  <Star v-if="favoriteStore.isFavorite(item.url)" class="h-4 w-4 fill-primary text-primary" />
                  <Star v-else class="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" class="h-7 w-3 shrink-0 px-0 -ml-1" @click="openFavoriteDropdown(item, $event.target.closest('button'))" title="选择收藏夹">
                  <ChevronDown class="h-3 w-3" />
                </Button>
              </div>
            </div>
          </div>
        </div>

        <ResultPagination
          :current-page="resultStore.resultsPage"
          :total-pages="totalPages"
          :total="resultStore.resultsTotal"
          :per-page="resultStore.resultsPerPage"
          @update:current-page="changePage"
          @update:per-page="changePerPage"
        />
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

    <AlertDialog v-model:open="showOptimizeDialog">
      <AlertDialogHeader>智能优选并去重</AlertDialogHeader>
      <AlertDialogDescription>
        将自动移除重复和无效频道，此操作不可撤销。确认继续？
      </AlertDialogDescription>
      <AlertDialogFooter>
        <Button variant="outline" @click="showOptimizeDialog = false">取消</Button>
        <Button @click="showOptimizeDialog = false; handleSmartOptimize()">确认优选</Button>
      </AlertDialogFooter>
    </AlertDialog>

    <Dialog v-model:open="showBatchFavoriteDialog">
      <DialogHeader><DialogTitle>批量收藏到文件夹</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <p class="text-sm text-muted-foreground">已选择 {{ selectedItems.size }} 个频道，请选择目标收藏夹</p>
        <div class="max-h-60 overflow-y-auto space-y-2 pr-1">
          <Button
            variant="outline"
            size="sm"
            class="w-full justify-start gap-2"
            @click="doBatchFavorite(null)"
          >
            <Inbox class="h-3.5 w-3.5" />
            未分类
          </Button>
          <Button
            v-for="folder in favoriteStore.folders.filter(f => f.id !== null)" :key="folder.id"
            variant="outline"
            size="sm"
            class="w-full justify-start gap-2"
            @click="doBatchFavorite(folder.id)"
          >
            <Folder class="h-3.5 w-3.5" />
            {{ folder.name }}
            <span class="ml-auto text-xs text-muted-foreground">{{ folder.count }}</span>
          </Button>
        </div>
        <!-- 新建收藏夹 -->
        <div class="border-t pt-3 space-y-2">
          <template v-if="showBatchNewFolder">
            <div class="flex items-center gap-2">
              <Input v-model="batchNewFolderName" placeholder="收藏夹名称" class="h-8 text-xs flex-1" @keyup.enter="handleBatchAddFolder" @keyup.esc="showBatchNewFolder = false; batchNewFolderName = ''" />
              <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="handleBatchAddFolder" title="创建">
                <Check class="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="showBatchNewFolder = false; batchNewFolderName = ''" title="取消">
                <X class="h-3.5 w-3.5" />
              </Button>
            </div>
          </template>
          <template v-else>
            <Button variant="outline" size="sm" class="w-full gap-2" @click="showBatchNewFolder = true">
              <Plus class="h-3.5 w-3.5" />
              新建收藏夹
            </Button>
          </template>
        </div>
        <!-- 底部固定操作栏 -->
        <div class="border-t pt-3 flex items-center justify-between">
          <label class="flex items-center gap-2 cursor-pointer select-none">
            <Checkbox
              :model-value="resultStore.checkResults.length > 0 && resultStore.checkResults.every(item => selectedItems.has(item.url))"
              @update:model-value="selectAllItems"
            />
            <span class="text-sm">全选</span>
          </label>
          <span class="text-xs text-muted-foreground">{{ selectedItems.size }} 个选中</span>
        </div>
      </div>
    </Dialog>

    <Dialog v-model:open="showAddFolderDialog">
      <DialogHeader><DialogTitle>新建收藏夹</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <Input v-model="addFolderName" placeholder="收藏夹名称" @keyup.enter="handleAddFolderDialog" />
        <div class="flex justify-end gap-2">
          <Button variant="outline" @click="showAddFolderDialog = false">取消</Button>
          <Button @click="handleAddFolderDialog">创建</Button>
        </div>
      </div>
    </Dialog>

    <Teleport to="body">
      <div
        v-if="showFavoriteDropdown"
        ref="favoriteDropdownMenuRef"
        class="fixed z-50 min-w-[180px] rounded-lg border bg-popover p-1 shadow-md max-h-[60vh] overflow-y-auto"
        :style="{ top: favoriteDropdownPosition.top + 'px', left: favoriteDropdownPosition.left + 'px' }"
      >
        <div class="px-2 py-1.5 text-xs text-muted-foreground font-medium">
          收藏到
          <span v-if="favoriteStore.activeFolderId !== null" class="text-primary ml-1">(默认: {{ favoriteStore.folders.find(f => f.id === favoriteStore.activeFolderId)?.name || '未分类' }})</span>
        </div>
        <button
          class="flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-sm hover:bg-accent transition-colors"
          @click="handleAddToFolder(null)"
        >
          <Inbox class="h-3.5 w-3.5" />
          <span>未分类</span>
          <Check v-if="favoriteStore.activeFolderId === null" class="h-3 w-3 ml-auto text-primary" />
        </button>
        <button
          v-for="folder in favoriteStore.folders.filter(f => f.id !== null)" :key="folder.id"
          class="flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-sm hover:bg-accent transition-colors"
          @click="handleAddToFolder(folder.id)"
        >
          <Folder class="h-3.5 w-3.5" />
          <span>{{ folder.name }}</span>
          <Check v-if="favoriteStore.activeFolderId === folder.id" class="h-3 w-3 ml-auto text-primary" />
        </button>
        <div class="border-t mt-1 pt-1 px-2 py-1.5 space-y-1">
          <button
            class="flex items-center gap-2 w-full rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            @click="showFavoriteDropdown = false; showAddFolderDialog = true"
          >
            <Plus class="h-3 w-3" />
            <span>新建收藏夹</span>
          </button>
          <button
            class="flex items-center gap-2 w-full rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            @click="showFavoriteDropdown = false; router.push('/favorites')"
          >
            <Star class="h-3 w-3" />
            <span>管理收藏夹</span>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Wand2, Download, BarChart3, Play, Star, ChevronDown, Folder, Inbox, Check, Plus, RefreshCw } from 'lucide-vue-next'
import ResultPagination from '../components/result/ResultPagination.vue'
import LatencyBadge from '../components/LatencyBadge.vue'
import ResultFilterBar from '../components/result/ResultFilterBar.vue'
import { useCheckStore } from '../stores/check'
import { useResultStore } from '../stores/result'
import { useFavoriteStore } from '../stores/favorite'
import { smartOptimize, exportResults, getAvailableCountries, getAvailableRegions, getCategoryTree, quickCheckResults } from '../api'
import { useToast } from '../composables/useToast'
import { cn, countryCodeToName } from '../lib/utils'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Checkbox } from '../components/ui/checkbox'
import { AlertDialog, AlertDialogHeader, AlertDialogDescription, AlertDialogFooter } from '../components/ui/alert-dialog'

const checkStore = useCheckStore()
const resultStore = useResultStore()
const favoriteStore = useFavoriteStore()
const router = useRouter()
const route = useRoute()
const { toast } = useToast()

const showExport = ref(false)
const showOptimizeDialog = ref(false)
const mediaType = ref('all')
try {
  const saved = localStorage.getItem('iptv_result_media_type')
  if (saved) mediaType.value = saved
} catch {}
watch(mediaType, (val) => {
  try { localStorage.setItem('iptv_result_media_type', val) } catch {}
})

const viewMode = ref('grouped')
try {
  const saved = localStorage.getItem('iptv_result_view_mode')
  if (saved) viewMode.value = saved
} catch {}
watch(viewMode, (val) => {
  try { localStorage.setItem('iptv_result_view_mode', val) } catch {}
})

const showAdvancedFilter = ref(false)
try {
  const saved = localStorage.getItem('iptv_result_show_advanced_filter')
  if (saved) showAdvancedFilter.value = JSON.parse(saved)
} catch {}
watch(showAdvancedFilter, (val) => {
  try { localStorage.setItem('iptv_result_show_advanced_filter', JSON.stringify(val)) } catch {}
})

const countrySearch = ref('')
const selectedCountries = ref([])
try {
  const saved = localStorage.getItem('iptv_result_selected_countries')
  if (saved) selectedCountries.value = JSON.parse(saved)
} catch {}
watch(selectedCountries, (val) => {
  try { localStorage.setItem('iptv_result_selected_countries', JSON.stringify(val)) } catch {}
}, { deep: true })

const selectedCategory = ref('')
try {
  const saved = localStorage.getItem('iptv_result_selected_category')
  if (saved) selectedCategory.value = saved
} catch {}
watch(selectedCategory, (val) => {
  try { localStorage.setItem('iptv_result_selected_category', val) } catch {}
})

const selectedQuality = ref('')
try {
  const saved = localStorage.getItem('iptv_result_selected_quality')
  if (saved) selectedQuality.value = saved
} catch {}
watch(selectedQuality, (val) => {
  try { localStorage.setItem('iptv_result_selected_quality', val) } catch {}
})

const selectedProtocol = ref('')
try {
  const saved = localStorage.getItem('iptv_result_selected_protocol')
  if (saved) selectedProtocol.value = saved
} catch {}
watch(selectedProtocol, (val) => {
  try { localStorage.setItem('iptv_result_selected_protocol', val) } catch {}
})

const latencyMin = ref('')
try {
  const saved = localStorage.getItem('iptv_result_latency_min')
  if (saved) latencyMin.value = saved
} catch {}
watch(latencyMin, (val) => {
  try { localStorage.setItem('iptv_result_latency_min', val) } catch {}
})

const latencyMax = ref('')
try {
  const saved = localStorage.getItem('iptv_result_latency_max')
  if (saved) latencyMax.value = saved
} catch {}
watch(latencyMax, (val) => {
  try { localStorage.setItem('iptv_result_latency_max', val) } catch {}
})

const speedMin = ref('')
try {
  const saved = localStorage.getItem('iptv_result_speed_min')
  if (saved) speedMin.value = saved
} catch {}
watch(speedMin, (val) => {
  try { localStorage.setItem('iptv_result_speed_min', val) } catch {}
})

const speedMax = ref('')
try {
  const saved = localStorage.getItem('iptv_result_speed_max')
  if (saved) speedMax.value = saved
} catch {}
watch(speedMax, (val) => {
  try { localStorage.setItem('iptv_result_speed_max', val) } catch {}
})

const selectedRegion = ref('')
try {
  const saved = localStorage.getItem('iptv_result_selected_region')
  if (saved) selectedRegion.value = saved
} catch {}
watch(selectedRegion, (val) => {
  try { localStorage.setItem('iptv_result_selected_region', val) } catch {}
})

const showRegionPanel = ref(false)
try {
  const saved = localStorage.getItem('iptv_result_show_region_panel')
  if (saved) showRegionPanel.value = JSON.parse(saved)
} catch {}
watch(showRegionPanel, (val) => {
  try { localStorage.setItem('iptv_result_show_region_panel', JSON.stringify(val)) } catch {}
})

const dynamicCountries = ref([])
const dynamicRegions = ref([])
const categoryTree = ref([])
const selectedSessionId = ref('')
const colWidth = ref({ name: 192 })
let searchTimer = null

const showFavoriteDropdown = ref(false)
const favoriteDropdownTarget = ref(null)
const favoriteDropdownPosition = ref({ top: 0, left: 0 })
const favoriteDropdownItem = ref(null)
const favoriteDropdownButtonRef = ref(null)
const favoriteDropdownMenuRef = ref(null)

const showAddFolderDialog = ref(false)
const addFolderName = ref('')

const showBatchNewFolder = ref(false)
const batchNewFolderName = ref('')

const batchSelectMode = ref(false)
try {
  const saved = localStorage.getItem('iptv_result_batch_select_mode')
  if (saved) batchSelectMode.value = JSON.parse(saved)
} catch {}
watch(batchSelectMode, (val) => {
  try { localStorage.setItem('iptv_result_batch_select_mode', JSON.stringify(val)) } catch {}
})

const selectedItems = ref(new Set())
try {
  const saved = localStorage.getItem('iptv_result_selected_items')
  if (saved) selectedItems.value = new Set(JSON.parse(saved))
} catch {}
watch(selectedItems, (val) => {
  try { localStorage.setItem('iptv_result_selected_items', JSON.stringify([...val])) } catch {}
}, { deep: true })

const showBatchFavoriteDialog = ref(false)

const staticCountries = [
  { code: 'CN', name: '中国' },
  { code: 'US', name: '美国' },
  { code: 'GB', name: '英国' },
  { code: 'JP', name: '日本' },
  { code: 'KR', name: '韩国' },
  { code: 'FR', name: '法国' },
  { code: 'DE', name: '德国' },
  { code: 'IT', name: '意大利' },
  { code: 'ES', name: '西班牙' },
  { code: 'AU', name: '澳大利亚' },
  { code: 'CA', name: '加拿大' },
  { code: 'IN', name: '印度' },
  { code: 'BR', name: '巴西' },
  { code: 'RU', name: '俄罗斯' },
  { code: 'SG', name: '新加坡' },
  { code: 'MY', name: '马来西亚' },
  { code: 'TH', name: '泰国' },
  { code: 'AE', name: '阿联酋' },
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

const windowWidth = ref(window.innerWidth)
const isWideScreen = computed(() => windowWidth.value >= 768)
const isMediumScreen = computed(() => windowWidth.value >= 640)

let resizeTimer = null
function onResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => { windowWidth.value = window.innerWidth }, 100)
}

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

const filterTabs = computed(() => [
  { value: 'all', label: '全部', count: resultStore.resultsTotal },
  { value: 'valid', label: '有效', count: checkStore.validCount },
  { value: 'likely_valid', label: '疑似有效', count: checkStore.likelyValidCount },
  { value: 'invalid', label: '无效', count: checkStore.invalidCount },
])

const mediaTypes = [
  { value: 'all', label: '全部' },
  { value: 'tv', label: '电视' },
  { value: 'radio', label: '广播' },
]

// ---------- URL query 同步（必须在所有 ref 声明之后） ----------
function syncStateFromURL() {
  const q = route.query
  if (q.tab) resultStore.currentTab = q.tab
  if (q.media_type) mediaType.value = q.media_type
  if (q.search) resultStore.searchQuery = q.search
  if (q.country) selectedCountries.value = q.country.split(',')
  if (q.category) selectedCategory.value = q.category
  if (q.quality) selectedQuality.value = q.quality
  if (q.protocol) selectedProtocol.value = q.protocol
  if (q.session_id) {
    selectedSessionId.value = q.session_id
    resultStore.selectSession(q.session_id)
  }
  if (q.view_mode) viewMode.value = q.view_mode
}

function pushStateToURL() {
  const query = {}
  if (resultStore.currentTab !== 'all') query.tab = resultStore.currentTab
  if (mediaType.value !== 'all') query.media_type = mediaType.value
  if (resultStore.searchQuery) query.search = resultStore.searchQuery
  if (selectedCountries.value.length > 0) query.country = selectedCountries.value.join(',')
  if (selectedCategory.value) query.category = selectedCategory.value
  if (selectedQuality.value) query.quality = selectedQuality.value
  if (selectedProtocol.value) query.protocol = selectedProtocol.value
  if (selectedSessionId.value) query.session_id = selectedSessionId.value
  if (viewMode.value !== 'grouped') query.view_mode = viewMode.value
  router.replace({ query })
}

watch([
  () => resultStore.currentTab,
  () => mediaType.value,
  () => selectedCountries.value,
  () => selectedCategory.value,
  () => selectedQuality.value,
  () => selectedProtocol.value,
  () => selectedSessionId.value,
  () => viewMode.value,
], () => {
  pushStateToURL()
})

onMounted(async () => {
  syncStateFromURL()
  await resultStore.fetchHistory()
  try {
    await favoriteStore.fetchFavorites()
    await favoriteStore.fetchFolders()
  } catch (e) {
    toast.error('加载收藏失败', e.response?.data?.detail || e.message)
  }
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
        // emoji removed — using FlagIcon component instead
        // emoji: c.flag || '',
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
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('resize', onResize)
  clearTimeout(resizeTimer)
})

function handleOutsideClick(e) {
  if (showFavoriteDropdown.value && favoriteDropdownMenuRef.value && !favoriteDropdownMenuRef.value.contains(e.target) && favoriteDropdownButtonRef.value && !favoriteDropdownButtonRef.value.contains(e.target)) {
    showFavoriteDropdown.value = false
  }
}

function formatHistoryLabel(h) {
  const date = h.created_at ? new Date(h.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未知时间'
  const validRate = h.total > 0 ? Math.round((h.valid / h.total) * 100) : 0
  return `${date} | ${h.total}频道 | 有效${validRate}%`
}

// ---------- 检测时效提示 ----------
const sessionAgeText = computed(() => {
  const h = resultStore.history.find(h => h.session_id === (selectedSessionId.value || resultStore.selectedSessionId))
  if (!h || !h.created_at) return ''
  const elapsed = Date.now() - new Date(h.created_at).getTime()
  const mins = Math.floor(elapsed / 60000)
  if (mins < 1) return '刚刚检测'
  if (mins < 60) return `距检测 ${mins} 分钟`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `距检测 ${hours} 小时`
  const days = Math.floor(hours / 24)
  return `距检测 ${days} 天`
})

const sessionAgeUrgency = computed(() => {
  if (!sessionAgeText.value) return { class: '' }
  const h = resultStore.history.find(h => h.session_id === (selectedSessionId.value || resultStore.selectedSessionId))
  if (!h || !h.created_at) return { class: '' }
  const elapsed = Date.now() - new Date(h.created_at).getTime()
  const hours = elapsed / 3600000
  if (hours < 1) return { class: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' }
  if (hours < 6) return { class: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' }
  return { class: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' }
})

// ---------- 实时刷新延迟 ----------
const isRefreshingLatency = ref(false)
const liveLatencyMap = ref({})

async function handleRefreshLatency() {
  const items = resultStore.checkResults
  if (!items || items.length === 0) {
    toast.info('提示', '当前页面没有可检测的频道')
    return
  }
  isRefreshingLatency.value = true
  liveLatencyMap.value = {}
  try {
    const payload = items.map(item => ({ url: item.url, name: item.name }))
    const { data } = await quickCheckResults(payload)
    const map = {}
    for (const r of data.results) {
      map[r.url] = r
    }
    liveLatencyMap.value = map
    const okCount = data.results.filter(r => r.ok).length
    const failCount = data.results.filter(r => !r.ok).length
    toast.success(`实时检测完成`, `${okCount} 个可达，${failCount} 个不可达`)
  } catch (e) {
    const msg = e.response?.data?.error?.message || e.response?.data?.detail || e?.message || '实时检测失败'
    toast.error('实时检测失败', msg)
  } finally {
    isRefreshingLatency.value = false
  }
}

function getLiveLatency(item) {
  if (!liveLatencyMap.value[item.url]) return null
  return liveLatencyMap.value[item.url]
}

function onSessionChange() {
  resultStore.selectSession(selectedSessionId.value)
  resultStore.setPage(1)
  applyAdvancedFilters()
}

function onSessionChangeId(id) {
  selectedSessionId.value = id
  resultStore.selectSession(id)
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

function selectMediaType(type) {
  mediaType.value = type
  resultStore.setPage(1)
  applyAdvancedFilters()
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

function applyAdvancedFilters(resetPage = true) {
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
  
  if (resetPage) resultStore.setPage(1)
  resultStore.fetchResults(filters)
}

function switchTab(tab) {
  resultStore.setTab(tab)
  resultStore.setPage(1)
  applyAdvancedFilters()
}

function changePage(page) {
  resultStore.setPage(page)
  applyAdvancedFilters(false)
}

function changePerPage(n) {
  resultStore.resultsPerPage = n
  resultStore.setPage(1)
  try { localStorage.setItem('iptv_result_per_page', n) } catch {}
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
  const radio = item.is_radio ? '&radio=1' : ''
  const region = item.region ? `&region=${encodeURIComponent(item.region)}` : ''
  const freq = item.frequency ? `&freq=${encodeURIComponent(item.frequency)}` : ''
  window.open(`/player?url=${encoded}&name=${encodeURIComponent(item.name)}${radio}${region}${freq}`, '_blank')
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

function formatSpeed(speed) {
  if (!speed || speed === '-' || speed === 0) return '-'
  const val = typeof speed === 'string' ? parseFloat(speed) : speed
  if (isNaN(val) || val <= 0) return '-'
  if (val >= 1000) return (val / 1000).toFixed(1) + 'Mbps'
  return Math.round(val) + 'Kbps'
}

async function handleToggleFavorite(item) {
  try {
    await favoriteStore.toggleFavorite({ name: item.name, url: item.url, group: item.group || item.channel_group || '' })
    const isFav = favoriteStore.isFavorite(item.url)
    if (isFav) {
      const folderName = favoriteStore.folders.find(f => f.id === favoriteStore.activeFolderId)?.name || '未分类'
      toast.success(`已收藏到${folderName}`, item.name)
    } else {
      toast.success('已取消收藏', item.name)
    }
  } catch (e) {
    toast.error('操作失败', e.response?.data?.detail || e.message)
  }
}

function openFavoriteDropdown(item, buttonEl) {
  favoriteDropdownItem.value = item
  showFavoriteDropdown.value = true
  favoriteDropdownButtonRef.value = buttonEl
  nextTick(() => {
    repositionFavoriteDropdown()
  })
}

function repositionFavoriteDropdown() {
  const buttonEl = favoriteDropdownButtonRef.value
  if (!buttonEl) return
  const rect = buttonEl.getBoundingClientRect()
  const dropdownWidth = 180
  const dropdownHeight = favoriteDropdownMenuRef.value
    ? favoriteDropdownMenuRef.value.offsetHeight
    : 200
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  let left = rect.right - dropdownWidth
  if (left < 8) left = rect.left

  let top = rect.bottom + 4
  if (top + dropdownHeight > viewportHeight) {
    top = rect.top - dropdownHeight - 4
  }

  favoriteDropdownPosition.value = { top, left }
}

async function handleAddToFolder(folderId) {
  if (!favoriteDropdownItem.value) return
  showFavoriteDropdown.value = false
  try {
    const result = await favoriteStore.addFavoriteTo(
      { name: favoriteDropdownItem.value.name, url: favoriteDropdownItem.value.url, group: favoriteDropdownItem.value.group || favoriteDropdownItem.value.channel_group || '' },
      folderId
    )
    favoriteStore.setDefaultFolder(folderId)
    const folderName = favoriteStore.folders.find(f => f.id === folderId)?.name || '未分类'
    toast.success(result.action === 'removed' ? '已取消收藏' : `已收藏到${folderName}`, favoriteDropdownItem.value.name)
  } catch (e) {
    toast.error('操作失败', e.response?.data?.detail || e.message)
  }
}

async function handleAddFolderDialog() {
  const name = addFolderName.value.trim()
  if (!name) return
  try {
    const data = await favoriteStore.addFolder(name)
    if (data) {
      if (favoriteDropdownItem.value) {
        await favoriteStore.addFavoriteTo(
          { name: favoriteDropdownItem.value.name, url: favoriteDropdownItem.value.url, group: favoriteDropdownItem.value.group || favoriteDropdownItem.value.channel_group || '' },
          data.id
        )
        favoriteStore.setDefaultFolder(data.id)
        toast.success(`已收藏到${data.name}`, favoriteDropdownItem.value.name)
      } else {
        toast.success(`收藏夹「${data.name}」已创建`)
      }
    }
    showAddFolderDialog.value = false
    addFolderName.value = ''
  } catch (e) {
    toast.error('创建收藏夹失败', e.response?.data?.detail || e.message)
  }
}

function toggleBatchSelectMode() {
  batchSelectMode.value = !batchSelectMode.value
  if (!batchSelectMode.value) {
    selectedItems.value = new Set()
  }
}

function toggleItemSelection(itemUrl) {
  const s = new Set(selectedItems.value)
  if (s.has(itemUrl)) s.delete(itemUrl)
  else s.add(itemUrl)
  selectedItems.value = s
}

function selectAllItems() {
  const urls = resultStore.checkResults.map(item => item.url)
  const allSelected = urls.every(url => selectedItems.value.has(url))
  if (allSelected) {
    selectedItems.value = new Set()
  } else {
    selectedItems.value = new Set(urls)
  }
}

function openBatchFavoriteDialog() {
  if (selectedItems.value.size === 0) return
  showBatchFavoriteDialog.value = true
}

async function doBatchFavorite(folderId) {
  showBatchFavoriteDialog.value = false
  const folderName = favoriteStore.folders.find(f => f.id === folderId)?.name || '未分类'
  let added = 0
  let skipped = 0
  for (const url of selectedItems.value) {
    const item = resultStore.checkResults.find(i => i.url === url)
    if (!item) continue
    if (favoriteStore.isFavorite(url)) {
      skipped++
      continue
    }
    try {
      await favoriteStore.addFavoriteTo(
        { name: item.name, url: item.url, group: item.group || item.channel_group || '' },
        folderId
      )
      added++
    } catch {}
  }
  favoriteStore.setDefaultFolder(folderId)
  await favoriteStore.fetchFavorites()
  batchSelectMode.value = false
  selectedItems.value = new Set()
  toast.success('批量收藏完成', `成功 ${added} 个${skipped > 0 ? `，跳过已收藏 ${skipped} 个` : ''}`)
}

async function handleBatchAddFolder() {
  const name = batchNewFolderName.value.trim()
  if (!name) return
  try {
    const data = await favoriteStore.addFolder(name)
    if (data) {
      await doBatchFavorite(data.id)
    }
    showBatchNewFolder.value = false
    batchNewFolderName.value = ''
  } catch (e) {
    toast.error('创建收藏夹失败', e.response?.data?.detail || e.message)
  }
}

function startResize(col, e) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = colWidth.value[col]
  const onMove = (ev) => {
    const delta = ev.clientX - startX
    colWidth.value[col] = Math.max(80, startWidth + delta)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
</script>
