<template>
  <div class="space-y-6" @pointerdown.capture="markInteracting" @wheel.passive="markInteracting" @touchmove.passive="markInteracting">
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
      :country-mode="countryMode"
      :hide-vod="hideVod"
      :selected-category="selectedCategory"
      :selected-quality="selectedQuality"
      :selected-protocol="selectedProtocol"
      :selected-region="selectedRegion"
      :selected-sources="selectedSources"
      :available-sources="availableSources"
      :selected-language="selectedLanguage"
      :available-languages="availableLanguages"
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
      @update:country-mode="setCountryMode"
      @update:hide-vod="onHideVodChange"
      @toggle-country="toggleCountry"
      @toggle-region="toggleRegion"
      @toggle-source="toggleSource"
      @toggle-language="toggleLanguage"
      @update:selected-category="selectedCategory = $event"
      @update:selected-quality="selectedQuality = $event"
      @update:selected-protocol="selectedProtocol = $event"
      @update:latency-min="latencyMin = $event"
      @update:latency-max="latencyMax = $event"
      @update:speed-min="speedMin = $event"
      @update:speed-max="speedMax = $event"
      @clear-all-filters="clearAllFilters"
      @apply-filters="applyAdvancedFilters"
      @close-filter-panel="showAdvancedFilter = false"
    />

    <!-- 标题 + 操作按钮 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">检测结果</h1>
        <p class="text-muted-foreground mt-1">
          <template v-if="sourceTabs[0].count != null">
            共 {{ filterTabs[0].count }} 个频道 / {{ sourceTabs[0].count }} 个源地址
            · 有效 {{ filterTabs[1].count }} 频道（{{ sourceTabs[1].count }} 源）
            · 无效 {{ filterTabs[2].count }} 频道（{{ sourceTabs[2].count }} 源）
          </template>
          <template v-else>
            共 {{ filterTabs[0].count }} 个频道 · 有效 {{ filterTabs[1].count }} · 无效 {{ filterTabs[2].count }}
          </template>
          <span v-if="sessionAgeText" class="ml-2 px-2 py-0.5 rounded text-xs" :class="sessionAgeUrgency.class">{{ sessionAgeText }}</span>
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" class="gap-2" @click="showOptimizeDialog = true" title="自动移除重复和无效频道（不可撤销）">
          <Wand2 class="h-4 w-4" /> 智能优选
        </Button>
        <Button variant="outline" class="gap-2" @click="openRecheckDialog" :disabled="isRefreshingLatency || isFullRefreshing" :title="selectedItems.size > 0 ? `当前选中 ${selectedItems.size} 个频道` : '选择复检方案与范围'">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': isRefreshingLatency || isFullRefreshing }" />
          {{ isRefreshingLatency || isFullRefreshing ? '复检中...' : '复检' }}
        </Button>
        <Button variant="outline" class="gap-2" @click="openDetailCheckDialog" :disabled="appStore.isChecking || !validChannelCount" :title="!validChannelCount ? '当前会话没有有效频道可细筛' : '基于当前会话的有效频道发起细筛检测（可选快速/标准/深度），生成独立的细筛结果'">
          <Zap class="h-4 w-4" /> 细筛
        </Button>
        <div v-if="appStore.isRefreshLatencyRunning" class="flex items-center gap-3 ml-1 min-w-[280px]">
          <Progress :model-value="fullRefreshPercent" class="flex-1 h-2" />
          <span class="text-xs text-muted-foreground whitespace-nowrap">
            {{ appStore.refreshLatencyProgress.checked }}/{{ appStore.refreshLatencyProgress.total }} 源地址
            <template v-if="appStore.refreshLatencyProgress.channel_count"> · {{ appStore.refreshLatencyProgress.channel_count }} 频道</template>
            ({{ fullRefreshPercent }}%)
          </span>
          <span class="text-xs text-muted-foreground whitespace-nowrap">{{ refreshElapsed }}s</span>
          <Button variant="outline" size="sm" class="h-6 text-xs text-destructive border-destructive/50 hover:bg-destructive/10" @click="handleStopRefresh">停止</Button>
        </div>
        <Button variant="outline" class="gap-2" @click="showExport = true">
          <Download class="h-4 w-4" /> 导出
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="gap-2"
          @click="liveRefreshEnabled = !liveRefreshEnabled"
          :title="liveRefreshEnabled ? '检测中结果列表每 4 秒自动刷新；关闭后可专心查看，检测完成后仍会加载最终结果' : '检测中结果列表每 4 秒自动刷新'"
        >
          <RefreshCw
            class="h-4 w-4"
            :class="{ 'animate-spin': appStore.isChecking && followingLive && liveRefreshEnabled }"
          />
          {{ liveRefreshEnabled ? '实时刷新: 开' : '实时刷新: 关' }}
        </Button>
      </div>

    </div>

    <!-- 二次复检结果摘要（醒目展示，替代一闪而过的 toast） -->
    <div v-if="recheckSummary && recheckSummary.count > 0" class="flex items-center gap-3 rounded-lg border border-primary/25 bg-primary/5 px-4 py-3">
      <CheckCircle2 class="h-5 w-5 text-primary shrink-0" />
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span class="font-semibold text-foreground">二次复检完成</span>
        <span class="text-muted-foreground">检测 <span class="font-semibold text-foreground">{{ appStore.refreshLatencyProgress.total || recheckSummary.count }}</span> 个</span>
        <span class="text-muted-foreground">可达 <span class="font-semibold text-success">{{ appStore.refreshLatencyProgress.updated || recheckSummary.count }}</span></span>
        <span class="text-muted-foreground">平均延迟 <span class="font-semibold text-primary">{{ recheckSummary.avg_latency }} ms</span></span>
      </div>
      <Button variant="ghost" size="sm" class="ml-auto h-7 px-2 text-xs text-muted-foreground" @click="recheckSummary = null">关闭</Button>
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
                {{ allFilteredSelected ? '取消全选' : '全选' }}
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
           <!-- 聚合视图：按频道聚合展示多源 -->
           <ResultGroupedView
             v-if="viewMode === 'grouped'"
             :items="resultStore.checkResults"
             :expanded-channels="expandedChannels"
             @toggle-expand="toggleExpanded"
             @open-epg="openEpg"
             @play-recommended="playRecommended"
             @open-player="(item, url) => openPlayer({ ...item, url })"
             @toggle-favorite="handleToggleFavoriteGrouped"
           />
           <!-- 平铺视图 -->
           <template v-else>
           <div class="hidden sm:block rounded-lg border overflow-auto">
            <table class="text-sm table-fixed w-full">
              <thead>
                <tr class="border-b bg-muted/50">
                  <th class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 40px">
                    <Checkbox
                      :model-value="allFilteredSelected"
                      @update:model-value="selectAllItems"
                    />
                  </th>
                  <th class="h-10 px-3 text-left font-medium text-muted-foreground whitespace-nowrap cursor-pointer select-none hover:bg-accent/50 transition-colors group" style="width: 40%;" @click="toggleTableSort('name_asc', 'name_desc')">
                    <span class="inline-flex items-center gap-1">
                      频道名
                      <span v-if="resultStore.sortOrder === 'name_asc'" class="text-primary text-xs">▲</span>
                      <span v-else-if="resultStore.sortOrder === 'name_desc'" class="text-primary text-xs">▼</span>
                      <span v-else class="text-xs text-muted-foreground/30 group-hover:text-muted-foreground/60 transition-colors">⇅</span>
                    </span>
                  </th>
                  <th v-if="isWideScreen" class="h-10 px-3 text-left font-medium text-muted-foreground whitespace-nowrap" style="width: 15%;">分组</th>
                  <th class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 60px">
                    状态
                  </th>
                  <th v-if="isMediumScreen" class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap cursor-pointer select-none hover:bg-accent/50 transition-colors group" style="width: 72px" @click="toggleTableSort('latency_asc', 'latency_desc')">
                    <span class="inline-flex items-center gap-1">
                      <span v-if="hasLiveLatency" class="text-[10px] text-green-500" title="实时数据">●</span>
                      延迟
                      <span v-if="resultStore.sortOrder === 'latency_asc'" class="text-primary text-xs">▲</span>
                      <span v-else-if="resultStore.sortOrder === 'latency_desc'" class="text-primary text-xs">▼</span>
                      <span v-else class="text-xs text-muted-foreground/30 group-hover:text-muted-foreground/60 transition-colors">⇅</span>
                    </span>
                  </th>
                  <th v-if="isMediumScreen" class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap cursor-pointer select-none hover:bg-accent/50 transition-colors group" style="width: 72px" @click="toggleTableSort('speed_asc', 'speed_desc')">
                    <span class="inline-flex items-center gap-1">
                      速度
                      <span v-if="resultStore.sortOrder === 'speed_asc'" class="text-primary text-xs">▲</span>
                      <span v-else-if="resultStore.sortOrder === 'speed_desc'" class="text-primary text-xs">▼</span>
                      <span v-else class="text-xs text-muted-foreground/30 group-hover:text-muted-foreground/60 transition-colors">⇅</span>
                    </span>
                  </th>
                  <th class="h-10 px-3 text-center font-medium text-muted-foreground whitespace-nowrap" style="width: 96px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in resultStore.checkResults" :key="item.url || item.name"
                  class="border-b transition-colors hover:bg-accent/50"
                >
                  <td class="px-3 py-2 text-center" style="width: 40px">
                    <Checkbox
                      :model-value="selectedItems.has(item.url)"
                      @update:model-value="toggleItemSelection(item.url)"
                    />
                  </td>
                  <td class="px-3 py-2.5">
                    <div class="min-w-0">
                      <div class="flex items-center gap-1.5">
                        <Badge
                          v-if="geoLabel(item)"
                          variant="secondary"
                          class="text-[10px] shrink-0 px-1.5 py-0 h-4"
                          :class="geoIsForeign(item) ? 'bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800' : 'bg-emerald-600 text-white border-emerald-600 dark:bg-emerald-500 dark:border-emerald-500'"
                        >{{ geoLabel(item) }}</Badge>
                        <MediaTypeBadge :is-radio="item.is_radio" />
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
                      <span class="text-xs text-muted-foreground truncate block cursor-pointer hover:text-foreground" :title="item.url" @click="handleCopyUrl(item.url)">{{ item.url }}</span>
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
                      :variant="getItemQualityTier(item) === 'valid' ? 'success' : 'destructive'"
                      class="text-[10px] whitespace-nowrap"
                    >
                      {{ getItemQualityTier(item) === 'valid' ? '有效' : '无效' }}
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
                      <Button variant="ghost" size="icon" class="h-7 w-7" @click="openPlayer(item)" title="播放" aria-label="播放">
                        <Play class="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" class="h-7 w-7" @click="openEpg(item)" title="节目单" aria-label="节目单">
                        <Calendar class="h-4 w-4" />
                      </Button>
                      <div class="relative inline-flex">
                        <Button variant="ghost" size="icon" class="h-7 w-7" @click="handleToggleFavorite(item)" :title="favoriteStore.isFavorite(item.url) ? '取消收藏' : '收藏'" :aria-label="favoriteStore.isFavorite(item.url) ? '取消收藏' : '收藏'">
                          <Star v-if="favoriteStore.isFavorite(item.url)" class="h-4 w-4 fill-primary text-primary" />
                          <Star v-else class="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" class="h-7 w-3 px-0 -ml-1" @click="openFavoriteDropdown(item, $event.target.closest('button'))" title="选择收藏夹" aria-label="选择收藏夹">
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
              v-for="(item, idx) in resultStore.checkResults" :key="item.url || ('m-'+item.name)"
              class="flex items-center gap-3 p-3 rounded-lg border bg-card"
            >
              <Checkbox
                :model-value="selectedItems.has(item.url)"
                @update:model-value="toggleItemSelection(item.url)"
                class="shrink-0"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <Badge
                    v-if="geoLabel(item)"
                    variant="secondary"
                    class="text-[10px] shrink-0 px-1.5 py-0 h-4"
                    :class="geoIsForeign(item) ? 'bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800' : 'bg-emerald-600 text-white border-emerald-600 dark:bg-emerald-500 dark:border-emerald-500'"
                  >{{ geoLabel(item) }}</Badge>
                  <MediaTypeBadge :is-radio="item.is_radio" />
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
                :variant="getItemQualityTier(item) === 'valid' ? 'success' : 'destructive'"
                class="text-[10px] shrink-0"
              >
                {{ getItemQualityTier(item) === 'valid' ? '有效' : '无效' }}
              </Badge>
              <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" @click="openPlayer(item)">
                <Play class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" @click="openEpg(item)" title="节目单">
                <Calendar class="h-4 w-4" />
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
          </template>
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

    <ExportDialog
      :open="showExport"
      :selected-urls="Array.from(selectedItems)"
      @update:open="showExport = $event"
    />

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

    <AlertDialog v-model:open="showRecheckAllConfirm">
      <AlertDialogHeader>
        {{ pendingRecheck?.mode === 'emptyFilter' ? '当前筛选为空' : '确认全量复检' }}
      </AlertDialogHeader>
      <AlertDialogDescription>
        <template v-if="pendingRecheck?.mode === 'emptyFilter'">
          当前页面没有有效筛选条件（tab=全部且无国家/分组等），复检将覆盖
          <span class="font-semibold text-foreground">全部 {{ sessionTotalChannels || '?' }} 个频道（{{ sessionTotal || '?' }} 个源地址）</span>，进行{{
            pendingRecheck?.method === 'thorough' ? '彻底（GET 下载验证）' : '快速（HEAD）'
          }}检测，耗时较长。请确认范围后再继续。
        </template>
        <template v-else>
          将对整个检测会话的 {{ sessionTotalChannels || '?' }} 个频道 / {{ sessionTotal || '?' }} 个源地址进行{{
            pendingRecheck?.method === 'thorough' ? '彻底（GET 下载验证）' : '快速（HEAD）'
          }}检测，耗时较长。确认继续？
        </template>
      </AlertDialogDescription>
      <AlertDialogFooter>
        <Button variant="outline" @click="showRecheckAllConfirm = false">取消</Button>
        <Button @click="confirmRecheckAll">确认复检</Button>
      </AlertDialogFooter>
    </AlertDialog>

    <Dialog v-model:open="showRecheckDialog">
      <DialogHeader><DialogTitle>复检频道</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-5">
        <div>
          <div class="text-sm font-medium mb-2">检测方案</div>
          <Tabs class="w-full">
            <TabButton class="flex-1" :active="recheckMethod === 'quick'" @click="recheckMethod = 'quick'">快速</TabButton>
            <TabButton class="flex-1" :active="recheckMethod === 'thorough'" @click="recheckMethod = 'thorough'">彻底</TabButton>
          </Tabs>
          <div class="text-xs text-muted-foreground mt-1.5">
            <template v-if="recheckMethod === 'quick'">HEAD 探测，只判可达性 + 延迟，速度快</template>
            <template v-else>GET 下载验证，判定更准确，较慢</template>
          </div>
        </div>
        <div>
          <div class="text-sm font-medium mb-2">检测范围</div>
          <Tabs class="w-full">
            <TabButton class="flex-1" :active="recheckScope === 'page'" @click="recheckScope = 'page'">当前页</TabButton>
            <TabButton class="flex-1" :active="recheckScope === 'filter'" @click="recheckScope = 'filter'">当前筛选</TabButton>
            <TabButton class="flex-1" :active="recheckScope === 'all'" @click="recheckScope = 'all'">全部</TabButton>
            <TabButton v-if="selectedItems.size > 0" class="flex-1" :active="recheckScope === 'selected'" @click="recheckScope = 'selected'">已选 {{ selectedItems.size }}</TabButton>
          </Tabs>
          <div class="text-xs text-muted-foreground mt-1.5">
            <template v-if="recheckScope === 'page'">仅当前页展示的 {{ resultStore.checkResults.length }} 个频道 / {{ resultStore.checkResults.length }} 个源地址</template>
            <template v-else-if="recheckScope === 'filter'">当前筛选条件下的 {{ recheckFilterChannels }} 个频道 / {{ recheckFilterSources }} 个源地址（一个频道可能有多个源）</template>
            <template v-else-if="recheckScope === 'selected'">仅已选中的 {{ selectedItems.size }} 个源地址</template>
            <template v-else>整个检测会话的 {{ sessionTotalChannels }} 个频道 / {{ sessionTotal }} 个源地址（全量检测，耗时较长）</template>
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="outline" @click="showRecheckDialog = false">取消</Button>
          <Button @click="runRecheck">开始复检</Button>
        </div>
      </div>
    </Dialog>

    <AlertDialog v-model:open="showDetailCheckDialog">
      <AlertDialogHeader>确认细筛</AlertDialogHeader>
      <AlertDialogDescription>
        将基于当前会话中有效的
        <span class="font-semibold text-foreground">{{ validChannelCount }} 个频道</span>
        发起{{ detailCheckMode === 'deep' ? '深度检测' : (detailCheckMode === 'standard' ? '标准检测' : '快速检测') }}，
        生成一条独立的细筛结果，可与粗筛结果并排对比。
      </AlertDialogDescription>
      <div>
        <div class="text-sm font-medium mb-2">检测方案</div>
        <Tabs class="w-full">
          <TabButton class="flex-1" :active="detailCheckMode === 'quick'" @click="detailCheckMode = 'quick'">快速</TabButton>
          <TabButton class="flex-1" :active="detailCheckMode === 'standard'" @click="detailCheckMode = 'standard'">标准</TabButton>
          <TabButton class="flex-1" :active="detailCheckMode === 'deep'" @click="detailCheckMode = 'deep'">深度</TabButton>
        </Tabs>
        <div class="text-xs text-muted-foreground mt-1.5">
          <template v-if="detailCheckMode === 'quick'">仅测可达性 + 延迟，速度最快</template>
          <template v-else-if="detailCheckMode === 'deep'">可达性 + 拉流验证 + 下载测速，最准但最慢</template>
          <template v-else>可达性 + 拉流验证（推荐）</template>
        </div>
      </div>
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-medium">并发线程</div>
        <div class="flex items-center gap-2">
          <Input v-model.number="detailThreads" type="number" min="10" max="300" step="10" class="h-8 w-24 text-xs text-right" />
          <span class="text-xs text-muted-foreground">太高可能打爆源站，建议 ≤120</span>
        </div>
      </div>
      <AlertDialogFooter>
        <Button variant="outline" @click="showDetailCheckDialog = false">取消</Button>
        <Button @click="confirmDetailCheck">开始细筛</Button>
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
              :model-value="allFilteredSelected"
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

    <EpgDialog v-model:open="showEpgDialog" :channel-name="epgChannelName" :is-radio="epgIsRadio" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Wand2, Download, BarChart3, Play, Star, ChevronDown, Folder, Inbox, Check, Plus, RefreshCw, Calendar, CheckCircle2, Zap } from 'lucide-vue-next'
import ResultPagination from '../components/result/ResultPagination.vue'
import EpgDialog from '../components/EpgDialog.vue'
import ResultGroupedView from '../components/result/ResultGroupedView.vue'
import MediaTypeBadge from '../components/result/MediaTypeBadge.vue'
import ExportDialog from '../components/ExportDialog.vue'
import LatencyBadge from '../components/LatencyBadge.vue'
import ResultFilterBar from '../components/result/ResultFilterBar.vue'
import { useCheckStore } from '../stores/check'
import { useResultStore } from '../stores/result'
import { useFavoriteStore } from '../stores/favorite'
import { useAppStore } from '../stores/app'
import { smartOptimize, getAvailableCountries, getAvailableRegions, getAvailableSources, getAvailableLanguages, getCategoryTree, quickCheckResults, refreshResultsLatency, thoroughCheck, getFilteredUrls, stopRefreshLatency, getRefreshLatencyStatus, getResults, getLatencySummary, startDetailCheck } from '../api'
import { useToast } from '../composables/useToast'
import { geoLabel, geoIsForeign } from '../lib/utils'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Checkbox } from '../components/ui/checkbox'
import { AlertDialog, AlertDialogHeader, AlertDialogDescription, AlertDialogFooter } from '../components/ui/alert-dialog'
import Progress from '../components/ui/progress/Progress.vue'
import { Tabs, TabButton } from '../components/ui/tabs'
import { Input } from '../components/ui/input'

const checkStore = useCheckStore()
const resultStore = useResultStore()
const favoriteStore = useFavoriteStore()
const appStore = useAppStore()
const router = useRouter()
const route = useRoute()
const { toast } = useToast()

const showExport = ref(false)
const showOptimizeDialog = ref(false)
const showRecheckDialog = ref(false)
const recheckMethod = ref('quick')
const recheckScope = ref('filter')
const showDetailCheckDialog = ref(false)
const detailCheckMode = ref('deep') // 细筛检测方案：quick | standard | deep
const detailThreads = ref(80) // 细筛并发线程数
const showEpgDialog = ref(false)
// 复检"全部"范围：整个 session 的频道数 / 源地址数（用于提示），以及全量确认
const sessionTotal = ref(0)           // 全部源地址数（flat 口径）
const sessionTotalChannels = ref(0)   // 全部频道数（grouped 口径）
// "当前筛选"范围的频道数 / 源地址数（打开对话框时轻量获取）
const recheckFilterChannels = ref(0)
const recheckFilterSources = ref(0)
const showRecheckAllConfirm = ref(false)
const pendingRecheck = ref(null)
const epgChannelName = ref('')
const epgIsRadio = ref(false)
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

// ---------- 聚合视图（ResultGroupedView）交互 ----------
const expandedChannels = ref(new Set())

function toggleExpanded(name) {
  const next = new Set(expandedChannels.value)
  next.has(name) ? next.delete(name) : next.add(name)
  expandedChannels.value = next
}

function handleToggleFavoriteGrouped(item) {
  const url = item.url || (item.sources && item.sources[item.recommended_source_idx ?? 0]?.url) || ''
  if (!url) return
  return handleToggleFavorite({ ...item, url, group: item.channel_group || item.group || '' })
}

function playRecommended(item) {
  const src = item.sources && item.sources[item.recommended_source_idx ?? 0]
  if (src && src.url) openPlayer({ ...item, url: src.url })
}

function openEpg(item) {
  epgChannelName.value = item.tvg_name || item.name || ''
  epgIsRadio.value = !!item.is_radio
  showEpgDialog.value = true
}

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

// 国家反向筛选模式：include=包含所选（多选 OR）| exclude=排除所选（反向）
const countryMode = ref('include')
try {
  const saved = localStorage.getItem('iptv_result_country_mode')
  if (saved) countryMode.value = saved === 'exclude' ? 'exclude' : 'include'
} catch {}
watch(countryMode, (val) => {
  try { localStorage.setItem('iptv_result_country_mode', val) } catch {}
})

// 隐藏点播/轮播类假台（mp4 单文件循环、分集/合集点播等），默认开启
const hideVod = ref(true)
try {
  const saved = localStorage.getItem('iptv_result_hide_vod')
  if (saved !== null) hideVod.value = saved === '1'
} catch {}
watch(hideVod, (val) => {
  try { localStorage.setItem('iptv_result_hide_vod', val ? '1' : '0') } catch {}
})
function onHideVodChange(val) {
  hideVod.value = !!val
  // 二态内容偏好：切换即时生效，不必再点"应用筛选"
  applyAdvancedFilters()
}

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

const selectedSources = ref([])
try {
  const saved = localStorage.getItem('iptv_result_selected_sources')
  if (saved) selectedSources.value = JSON.parse(saved)
} catch {}
watch(selectedSources, (val) => {
  try { localStorage.setItem('iptv_result_selected_sources', JSON.stringify(val)) } catch {}
}, { deep: true })
const availableSources = ref([])
const selectedLanguage = ref('')
const availableLanguages = ref([])

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

const activeFilterCount = computed(() => {
  let count = 0
  if (selectedCountries.value.length > 0) count++
  if (selectedRegion.value !== '') count++
  if (selectedCategory.value !== '') count++
  if (selectedQuality.value !== '') count++
  if (selectedProtocol.value !== '') count++
  if (selectedSources.value.length > 0) count++
  if (selectedLanguage.value !== '') count++
  if (latencyMin.value !== '' || latencyMax.value !== '') count++
  if (speedMin.value !== '' || speedMax.value !== '') count++
  return count
})

// tab 计数优先取当前会话+当前筛选下由后端算出的 tab_counts（与列表同口径），
// 后端未返回时回退到旧的 resultsTotal / checkStore（避免旧版本后端兼容问题）。
// 2026-09-01: 移除"疑似有效"档位（引擎不再产生，两态：有效/无效）。
const filterTabs = computed(() => {
  const tc = resultStore.tabCounts
  return [
    { value: 'all', label: '全部', count: tc?.all ?? resultStore.resultsTotal },
    { value: 'valid', label: '有效', count: tc?.valid ?? checkStore.validCount },
    { value: 'invalid', label: '无效', count: tc?.invalid ?? checkStore.invalidCount },
  ]
})
// 当前会话的有效频道数（深度细筛的输入规模提示）
const validChannelCount = computed(() => filterTabs.value[1]?.count ?? 0)

function openDetailCheckDialog() {
  showDetailCheckDialog.value = true
}

async function confirmDetailCheck() {
  const sid = resultStore.selectedSessionId || checkStore.sessionId || ''
  if (!sid) {
    toast.error('无法细筛', '请先选择一个历史会话')
    return
  }
  if (validChannelCount.value <= 0) {
    toast.error('无法细筛', '当前会话没有有效频道可检测')
    return
  }
  showDetailCheckDialog.value = false
  try {
    router.push('/checking')
    checkStore.startCheckState(0)
    const threads = Math.max(10, Math.min(300, Number(detailThreads.value) || 80))
    const { data } = await startDetailCheck({ source_session_id: sid, check_mode: detailCheckMode.value, max_threads: threads })
    if (data?.session_id) checkStore.sessionId.value = data.session_id
  } catch (e) {
    let msg = '启动细筛检测失败'
    if (e?.response?.data?.detail) msg = e.response.data.detail
    else if (e?.message) msg = e.message
    toast.error('细筛启动失败', msg)
    checkStore.resetCheckState()
    router.push('/result')
  }
}
// 源地址统计（tab_counts.source，flat 口径）：与"频道数"并列展示"几个频道 / 几个源地址"
const sourceTabs = computed(() => {
  const sc = resultStore.tabCounts?.source
  if (!sc) return [{ count: null }, { count: null }, { count: null }]
  return [{ count: sc.all ?? 0 }, { count: sc.valid ?? 0 }, { count: sc.invalid ?? 0 }]
})

// 当前初筛全集是否已被全部选中（用于全选/取消全选文案）
const allFilteredSelected = computed(() =>
  resultStore.resultsTotal > 0 &&
  selectedItems.value.size > 0 &&
  selectedItems.value.size >= resultStore.resultsTotal
)

// 收集当前初筛条件，传给后端（彻底版检测作用域 / 跨页全选）
function currentFilterParams() {
  const p = {
    tab: resultStore.currentTab,
    media_type: mediaType.value,
    search: resultStore.searchQuery,
    hide_vod: hideVod.value ? '1' : '0',
  }
  if (selectedCountries.value.length > 0) {
    // 反向筛选（排除所选国家）时改用 country_exclude 参数，不传 country
    if (countryMode.value === 'exclude') p.country_exclude = selectedCountries.value.join(',')
    else p.country = selectedCountries.value.join(',')
  }
  if (countryMode.value === 'include' && selectedRegion.value) p.region = selectedRegion.value
  if (selectedCategory.value) p.category = selectedCategory.value
  if (selectedQuality.value) p.quality = selectedQuality.value
  if (selectedProtocol.value) p.protocol = selectedProtocol.value
  if (selectedSources.value.length > 0) p.source = selectedSources.value.join(',')
  if (selectedLanguage.value) p.language = selectedLanguage.value
  if (latencyMin.value !== '' && !isNaN(latencyMin.value)) p.latency_min = parseFloat(latencyMin.value)
  if (latencyMax.value !== '' && !isNaN(latencyMax.value)) p.latency_max = parseFloat(latencyMax.value)
  if (speedMin.value !== '' && !isNaN(speedMin.value)) p.speed_min = parseFloat(speedMin.value)
  if (speedMax.value !== '' && !isNaN(speedMax.value)) p.speed_max = parseFloat(speedMax.value)
  return p
}

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
  if (q.country_exclude) {
    selectedCountries.value = q.country_exclude.split(',')
    countryMode.value = 'exclude'
  } else if (q.country) {
    selectedCountries.value = q.country.split(',')
    countryMode.value = 'include'
  }
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
  if (selectedCountries.value.length > 0) {
    query[countryMode.value === 'exclude' ? 'country_exclude' : 'country'] = selectedCountries.value.join(',')
  }
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
  () => countryMode.value,
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
  if (appStore.isRefreshLatencyRunning) {
    isFullRefreshing.value = true
    startRefreshTimer()
  }

  // 并行加载互不依赖的数据：历史会话、筛选项（国家/地区/分类）、收藏，避免串行等待
  await Promise.all([
    resultStore.fetchHistory().catch(() => {}),
    getAvailableCountries({ session_id: resultStore.selectedSessionId || '' }).then(d => {
      if (d.data && d.data.length > 0) {
        dynamicCountries.value = d.data.map(c => ({
          code: c.code,
          name: c.name,
          // emoji removed — using FlagIcon component instead
          // emoji: c.flag || '',
          count: c.count,
          valid: c.valid,
        }))
      }
    }).catch(() => {}),
    getAvailableRegions({ session_id: resultStore.selectedSessionId || '' }).then(d => {
      if (d.data && d.data.length > 0) dynamicRegions.value = d.data
    }).catch(() => {}),
    getCategoryTree({ session_id: resultStore.selectedSessionId || '' }).then(d => {
      if (d.data) categoryTree.value = d.data
    }).catch(() => {}),
    favoriteStore.fetchFavorites().catch(() => {}),
    favoriteStore.fetchFolders().catch(() => {}),
  ])

  // 会话相关：确定 session 后再加载源/语言并拉取列表（依赖 fetchHistory 的会话解析）
  if (resultStore.selectedSessionId) {
    selectedSessionId.value = resultStore.selectedSessionId
  }
  // URL 未指定会话时，跟随当前/最近检测会话，避免停留 localStorage 中的旧会话
  // （从 /checking 检测完成后跳转 /result 时 URL 无 session_id，localStorage 可能残留上一次的旧值）
  if (!route.query.session_id && checkStore.sessionId) {
    if ((selectedSessionId.value || resultStore.selectedSessionId) !== checkStore.sessionId) {
      selectedSessionId.value = checkStore.sessionId
      resultStore.selectSession(checkStore.sessionId)
    }
  }
  const activeSid = selectedSessionId.value || resultStore.selectedSessionId || ''
  loadAvailableSources(activeSid)
  loadAvailableLanguages(activeSid)
  // 首次加载必须带上 URL 同步后的完整筛选（tab/country/region/category 等），
  // 否则 URL 里的 country=CN 等参数在首屏不生效，列表与 tab 计数都会失真。
  resultStore.fetchResults({ ...currentFilterParams(), view_mode: viewMode.value })
  // 检测进行中：跟随当前检测会话并启动定时刷新，让"实时查看结果"生效
  if (checkStore.isChecking) {
    startFollowingLive()
  }
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('resize', onResize)
  clearTimeout(resizeTimer)
  clearTimeout(interactionTimer)
  stopLiveResultRefresh()
  stopRecheckRefresh()
})

// ---------- 检测中实时跟随（"实时查看结果"） ----------
const LIVE_RESULT_REFRESH_MS = 4000
let liveResultTimer = null
// 是否正在跟随当前检测会话：进入结果页/新一轮检测时自动开启；用户手动切换会话后关闭
let followingLive = false

// 实时刷新开关：用户可手动关闭，避免检测中列表被频繁刷新打扰
const liveRefreshEnabled = ref(true)
try {
  const saved = localStorage.getItem('iptv_result_live_refresh')
  if (saved !== null) liveRefreshEnabled.value = saved === '1'
} catch {}
watch(liveRefreshEnabled, (val) => {
  try { localStorage.setItem('iptv_result_live_refresh', val ? '1' : '0') } catch {}
})

// 用户正在交互（点击/滚动）时暂停自动刷新，停歇 1.5s 后恢复，
// 保证查看/滚动/勾选期间列表不被中途换页打断
const userInteracting = ref(false)
let interactionTimer = null
function markInteracting() {
  userInteracting.value = true
  clearTimeout(interactionTimer)
  interactionTimer = setTimeout(() => { userInteracting.value = false }, 1500)
}
function isLiveRefreshPaused() {
  return !liveRefreshEnabled.value || userInteracting.value
}

// 开始跟随当前检测会话（进入结果页 / 新一轮检测开始时调用）
function startFollowingLive() {
  followingLive = true
  const sid = checkStore.sessionId
  if (sid && (selectedSessionId.value || resultStore.selectedSessionId) !== sid) {
    selectedSessionId.value = sid
    resultStore.selectSession(sid)
  }
  startLiveResultRefresh()
  // 立即刷新一次，不必等定时器首跳
  refreshLiveResults()
}

function refreshLiveResults() {
  if (!followingLive) return
  const sid = checkStore.sessionId
  if (!sid || !checkStore.isChecking) return
  if (isLiveRefreshPaused()) return
  // silent：后台静默刷新，不置 isLoading（不闪骨架屏），旧数据原位更新
  resultStore.fetchResults({ ...currentFilterParams(), session_id: sid }, { silent: true }).catch(() => {})
}

function startLiveResultRefresh() {
  if (liveResultTimer) return
  liveResultTimer = setInterval(refreshLiveResults, LIVE_RESULT_REFRESH_MS)
}

function stopLiveResultRefresh() {
  followingLive = false
  if (liveResultTimer) {
    clearInterval(liveResultTimer)
    liveResultTimer = null
  }
}

watch(() => checkStore.phase, (phase) => {
  if (phase === 'checking') {
    startFollowingLive()
  } else if (phase === 'completed') {
    // 跟随中完成检测 → 切到本次会话并刷新最终结果；已手动切走的用户不打扰
    const sid = checkStore.sessionId
    if (sid && followingLive) {
      if ((selectedSessionId.value || resultStore.selectedSessionId) !== sid) {
        selectedSessionId.value = sid
        resultStore.selectSession(sid)
      }
      resultStore.fetchResults({ ...currentFilterParams(), session_id: sid }).catch(() => {})
    }
    stopLiveResultRefresh()
  }
})

watch(() => checkStore.isChecking, (running) => {
  if (!running) stopLiveResultRefresh()
})

// 进入结果页时 sessionId 可能尚未同步，拿到后立即跟随当前检测会话
watch(() => checkStore.sessionId, (sid) => {
  if (sid && checkStore.isChecking && followingLive) {
    if ((selectedSessionId.value || resultStore.selectedSessionId) !== sid) {
      selectedSessionId.value = sid
      resultStore.selectSession(sid)
    }
    refreshLiveResults()
  }
})

function handleOutsideClick(e) {
  if (showFavoriteDropdown.value && favoriteDropdownMenuRef.value && !favoriteDropdownMenuRef.value.contains(e.target) && favoriteDropdownButtonRef.value && !favoriteDropdownButtonRef.value.contains(e.target)) {
    showFavoriteDropdown.value = false
  }
}

// ---------- 检测时效提示 ----------
const sessionAgeText = computed(() => {
  const h = resultStore.history.find(h => h.session_id === (selectedSessionId.value || resultStore.selectedSessionId))
  if (!h || !h.created_at) return ''
  // 优先"最后更新"（二次复检完成后更新），无则回退到会话创建时间
  const base = h.last_updated || h.created_at
  const elapsed = Date.now() - new Date(base).getTime()
  const mins = Math.floor(elapsed / 60000)
  if (mins < 1) return '刚刚更新'
  if (mins < 60) return `最后更新 ${mins} 分钟`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `最后更新 ${hours} 小时`
  const days = Math.floor(hours / 24)
  return `最后更新 ${days} 天`
})

const sessionAgeUrgency = computed(() => {
  if (!sessionAgeText.value) return { class: '' }
  const h = resultStore.history.find(h => h.session_id === (selectedSessionId.value || resultStore.selectedSessionId))
  if (!h || !h.created_at) return { class: '' }
  const base = h.last_updated || h.created_at
  const elapsed = Date.now() - new Date(base).getTime()
  const hours = elapsed / 3600000
  if (hours < 1) return { class: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' }
  if (hours < 6) return { class: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' }
  return { class: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' }
})

// ---------- 实时刷新延迟 ----------
const isRefreshingLatency = ref(false)
const liveLatencyMap = ref({})
const hasLiveLatency = computed(() => Object.keys(liveLatencyMap.value).length > 0)

// 打开复检对话框时获取：全部范围=频道数(grouped)+源地址数(flat)；当前筛选范围=频道数+源地址数
async function fetchSessionTotal() {
  const sid = resultStore.selectedSessionId || ''
  try {
    const [flatRes, groupedRes] = await Promise.all([
      getResults({ session_id: sid, tab: 'all', page: 1, per_page: 1, search: '', sort: 'best', view_mode: 'flat' }),
      getResults({ session_id: sid, tab: 'all', page: 1, per_page: 1, search: '', sort: 'best', view_mode: 'grouped' }),
    ])
    sessionTotal.value = flatRes.data.total || 0
    sessionTotalChannels.value = groupedRes.data.total || 0
  } catch (e) {
    sessionTotal.value = 0
    sessionTotalChannels.value = 0
  }
}

async function fetchRecheckFilterCounts() {
  try {
    const sid = resultStore.selectedSessionId || ''
    const { data } = await getFilteredUrls({ ...currentFilterParams(), session_id: sid, count_only: 1 })
    recheckFilterChannels.value = data.channel_count || 0
    recheckFilterSources.value = data.total || 0
  } catch (e) {
    recheckFilterChannels.value = 0
    recheckFilterSources.value = 0
  }
}

function openRecheckDialog() {
  // 默认范围对齐当前筛选（避免误选"全部"导致全量复检）；有选中项时优先按选中项
  recheckScope.value = selectedItems.value.size > 0 ? 'selected' : 'filter'
  fetchSessionTotal()
  fetchRecheckFilterCounts()
  showRecheckDialog.value = true
}

// 判断前端筛选参数是否"空"（空 = 后端将回退为全量检测）
function hasActiveFilter(filters) {
  if (!filters) return false
  const { tab, media_type, search } = filters
  if (tab !== 'all' || media_type !== 'all' || search) return true
  return Object.entries(filters).some(([k, v]) => {
    // hide_vod 是内容质量偏好，不算真正的"筛选"，避免把空筛选误判为有筛选触发全量确认
    if (['tab', 'media_type', 'search', 'hide_vod'].includes(k)) return false
    return v !== '' && v !== undefined && v !== null
  })
}

function confirmRecheckAll() {
  showRecheckAllConfirm.value = false
  const p = pendingRecheck.value
  pendingRecheck.value = null
  if (p) doRunRecheck(p.scope, p.method, true)
}

async function doRunRecheck(scope, method, force = false) {
  // 快速 + 当前页 / 已选：同步 HEAD 探测（不写库，实时更新表格延迟）
  if (method === 'quick' && (scope === 'page' || scope === 'selected')) {
    const items = scope === 'selected'
      ? Array.from(selectedItems.value).map(url => ({ url, name: '' }))
      : resultStore.checkResults
    await handleRefreshLatency(items)
    return
  }

  // 快速 + 当前筛选 / 全部：异步全量 HEAD（写库 + SSE 进度）
  if (method === 'quick') {
    const filters = scope === 'filter' ? currentFilterParams() : {}
    if (scope === 'filter' && !force && !hasActiveFilter(filters)) {
      // 当前筛选实际为空 → 等价于全量，先确认，避免误触
      pendingRecheck.value = { scope, method, mode: 'emptyFilter' }
      showRecheckAllConfirm.value = true
      return
    }
    await handleFullRefreshLatency(filters)
    return
  }

  // 彻底：GET 下载验证
  let urls = []
  let filters = {}
  if (scope === 'page') urls = resultStore.checkResults.map(i => i.url)
  else if (scope === 'filter') filters = currentFilterParams()
  else if (scope === 'selected') urls = Array.from(selectedItems.value)
  if (scope === 'filter' && !force && !hasActiveFilter(filters)) {
    pendingRecheck.value = { scope, method, mode: 'emptyFilter' }
    showRecheckAllConfirm.value = true
    return
  }
  await runThoroughCheck(urls, filters)
}

async function runRecheck() {
  showRecheckDialog.value = false
  const scope = recheckScope.value
  const method = recheckMethod.value

  // "全部"范围：先弹确认，避免误触全量检测
  if (scope === 'all') {
    pendingRecheck.value = { scope, method, mode: 'all' }
    showRecheckAllConfirm.value = true
    return
  }
  await doRunRecheck(scope, method)
}

async function handleRefreshLatency(items = null) {
  const target = items || resultStore.checkResults
  if (!target || target.length === 0) {
    toast.info('提示', '当前范围内没有可检测的频道')
    return
  }
  isRefreshingLatency.value = true
  liveLatencyMap.value = {}
  try {
    const payload = target.map(item => ({ url: item.url, name: item.name || '' }))
    const { data } = await quickCheckResults(payload)
    const map = {}
    for (const r of data.results) {
      map[r.url] = r
    }
    liveLatencyMap.value = map
    const okCount = data.results.filter(r => r.ok).length
    const failCount = data.results.filter(r => !r.ok).length
    toast.success('复检完成', `${okCount} 个可达，${failCount} 个不可达`)
  } catch (e) {
    const msg = e.response?.data?.error?.message || e.response?.data?.detail || e?.message || '复检失败'
    toast.error('复检失败', msg)
  } finally {
    isRefreshingLatency.value = false
  }
}

function getLiveLatency(item) {
  if (!liveLatencyMap.value[item.url]) return null
  return liveLatencyMap.value[item.url]
}

// ---------- 全量刷新延迟 ----------
const isFullRefreshing = ref(appStore.isRefreshLatencyRunning)
watch(() => appStore.isRefreshLatencyRunning, (val) => { isFullRefreshing.value = val })
// 二次复检完成后的延迟摘要（平均延迟等），用于展示醒目的复检结果横幅
const recheckSummary = ref(null)
async function loadRecheckSummary() {
  try {
    const sid = resultStore.selectedSessionId || ''
    const { data } = await getLatencySummary(sid)
    recheckSummary.value = data || null
  } catch {
    recheckSummary.value = null
  }
}

// 复检进行中定时刷新结果列表（边核验边更新），避免必须等全部复核完才看到结果
const RECHECK_REFRESH_MS = 5000
let recheckRefreshTimer = null
function startRecheckRefresh() {
  if (recheckRefreshTimer) return
  recheckRefreshTimer = setInterval(async () => {
    if (!appStore.isRefreshLatencyRunning) {
      stopRecheckRefresh()
      return
    }
    if (isLiveRefreshPaused()) return
    try {
      // silent：复检中的列表刷新同样不闪骨架屏、不打断用户查看
      await resultStore.fetchResults({ ...currentFilterParams(), view_mode: viewMode.value }, { silent: true })
    } catch {}
  }, RECHECK_REFRESH_MS)
}
function stopRecheckRefresh() {
  if (recheckRefreshTimer) {
    clearInterval(recheckRefreshTimer)
    recheckRefreshTimer = null
  }
}
const fullRefreshProgress = ref({ total: 0, checked: 0, updated: 0, percent: 0 })
const refreshElapsed = ref(0)
let refreshTimer = null

const fullRefreshPercent = computed(() => {
  const p = appStore.refreshLatencyProgress
  if (!p.total || p.total === 0) return 0
  return Math.floor((p.checked / p.total) * 100)
})

function startRefreshTimer() {
  refreshElapsed.value = 0
  refreshTimer = setInterval(() => { refreshElapsed.value++ }, 1000)
}
function stopRefreshTimer() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

// 触发类请求超时（拿不到 response）时，后端可能已经成功启动任务——其返回 202 前的
// 筛选取数与延迟重置耗时可能超过前端超时。此时不能判定失败，否则用户看不到正在跑的进度。
async function confirmTaskStarted() {
  try {
    const { data } = await getRefreshLatencyStatus({ timeout: 8000 })
    if (data && data.is_running) {
      appStore.isRefreshLatencyRunning = true
      if (data.progress) appStore.refreshLatencyProgress = data.progress
      toast.info('提示', '检测任务已启动，正在后台运行')
      return true
    }
    // 未运行：返回状态便于调用方展示后端记录的真实失败原因
    return data || null
  } catch {
    // 查询失败按未启动处理
  }
  return null
}

async function handleFullRefreshLatency(filters = {}) {
  if (isFullRefreshing.value) return
  isFullRefreshing.value = true
  appStore.isRefreshLatencyRunning = true
  startRefreshTimer()
  try {
    const sid = resultStore.selectedSessionId || ''
    const { data } = await refreshResultsLatency(sid, filters)
    if (data && data.total) {
      appStore.refreshLatencyProgress = { checked: 0, total: data.total, updated: 0 }
      toast.info('复检已启动', `本次复检范围：${data.channel_count ?? data.total} 个频道 / ${data.total} 个源地址`)
    }
  } catch (e) {
    if (e.response?.status === 409) {
      toast.info('提示', '刷新任务正在运行中')
      return
    }
    const st = await confirmTaskStarted()
    if (st === true) return
    stopRefreshTimer()
    isFullRefreshing.value = false
    appStore.isRefreshLatencyRunning = false
    const msg = e.response?.data?.detail || st?.error || e?.message || '全量刷新失败'
    toast.error('全量刷新失败', msg)
  }
}

async function runThoroughCheck(urls = [], filters = {}) {
  isFullRefreshing.value = true
  appStore.isRefreshLatencyRunning = true
  startRefreshTimer()
  try {
    const sid = resultStore.selectedSessionId || ''
    const selectedUrls = urls.map(url => btoa(encodeURIComponent(url)))
    const { data } = await thoroughCheck(sid, selectedUrls, filters)
    if (data && data.total) {
      appStore.refreshLatencyProgress = { checked: 0, total: data.total, updated: 0 }
      toast.info('复检已启动', `本次复检范围：${data.channel_count ?? data.total} 个频道 / ${data.total} 个源地址`)
    }
  } catch (e) {
    if (e.response?.status === 409) {
      toast.info('提示', '检测任务正在运行中')
      return
    }
    const st = await confirmTaskStarted()
    if (st === true) return
    stopRefreshTimer()
    isFullRefreshing.value = false
    appStore.isRefreshLatencyRunning = false
    const msg = e.response?.data?.detail || st?.error || e?.message || '彻底版检测失败'
    toast.error('彻底版检测失败', msg)
  }
}

async function handleStopRefresh() {
  try {
    await stopRefreshLatency()
    stopRefreshTimer()
    isFullRefreshing.value = false
    appStore.isRefreshLatencyRunning = false
  } catch (e) {
    toast.error('停止失败', e.response?.data?.detail || e.message)
  }
}

watch(() => appStore.isRefreshLatencyRunning, (running, wasRunning) => {
  if (!wasRunning && running) {
    startRefreshTimer()
    startRecheckRefresh()
  }
  if (wasRunning && !running) {
    stopRefreshTimer()
    stopRecheckRefresh()
    isFullRefreshing.value = false
    const p = appStore.refreshLatencyProgress
    if (p.checked > 0 && p.checked === p.total) {
      toast.success('全量延迟刷新完成', `检测 ${p.checked} 个，${p.updated} 个可达`)
      resultStore.fetchResults()
      loadRecheckSummary()
    }
  }
})

function onSessionChangeId(id) {
  // 用户手动切换会话：退出"实时查看"跟随模式
  followingLive = false
  selectedSessionId.value = id
  resultStore.selectSession(id)
  resultStore.setPage(1)
  // 切换会话后旧选中项失效，清空以免全选误判/复检范围错乱
  selectedItems.value = new Set()
  recheckSummary.value = null
  applyAdvancedFilters()
  // 来源/语言筛选项随会话切换刷新
  loadAvailableSources(id)
  loadAvailableLanguages(id)
}

watch(() => resultStore.selectedSessionId, (newVal) => {
  if (newVal && newVal !== selectedSessionId.value) {
    selectedSessionId.value = newVal
    selectedItems.value = new Set()
    recheckSummary.value = null
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
    // 仅「包含中国」时才展开省级联动；反向排除中国时无需二级区域
    if (countryCode === 'CN' && countryMode.value === 'include') {
      showRegionPanel.value = true
    }
  }
}

function setCountryMode(mode) {
  if (!['include', 'exclude'].includes(mode)) return
  countryMode.value = mode
  if (mode === 'exclude') {
    // 排除模式下省级区域联动无意义（region 是中国的细分），收起并清空
    showRegionPanel.value = false
    selectedRegion.value = ''
  } else if (mode === 'include' && selectedCountries.value.includes('CN')) {
    showRegionPanel.value = true
  }
}

function toggleRegion(regionCode) {
  if (selectedRegion.value === regionCode) {
    selectedRegion.value = ''
  } else {
    selectedRegion.value = regionCode
  }
}

function selectMediaType(type) {
  mediaType.value = type
  resultStore.setPage(1)
  applyAdvancedFilters()
}

function toggleTableSort(ascVal, descVal) {
  const newSort = resultStore.sortOrder === ascVal ? descVal : ascVal
  resultStore.setSort(newSort)
  resultStore.setPage(1)

  // 延迟排序 & 有实时数据 → 客户端排序（不做 API 请求）
  if (viewMode.value === 'flat' && Object.keys(liveLatencyMap.value).length > 0 && (ascVal === 'latency_asc' || descVal === 'latency_desc')) {
    doLocalLatencySort(newSort)
    return
  }

  applyAdvancedFilters()
}

function doLocalLatencySort(sortDir) {
  const sorted = [...resultStore.checkResults].sort((a, b) => {
    const la = getLiveLatency(a)?.latency ?? (a.latency !== '-' ? parseInt(a.latency) : 999999)
    const lb = getLiveLatency(b)?.latency ?? (b.latency !== '-' ? parseInt(b.latency) : 999999)
    const va = la > 0 ? la : 999999
    const vb = lb > 0 ? lb : 999999
    return sortDir === 'latency_asc' ? va - vb : vb - va
  })
  resultStore.checkResults = sorted
}

function toggleSource(src) {
  const index = selectedSources.value.indexOf(src)
  if (index > -1) selectedSources.value.splice(index, 1)
  else selectedSources.value.push(src)
}

function toggleLanguage(lang) {
  selectedLanguage.value = selectedLanguage.value === lang ? '' : lang
}

async function loadAvailableLanguages(sessionId = '') {
  try {
    const { data } = await getAvailableLanguages({ session_id: sessionId })
    availableLanguages.value = data || []
  } catch {}
}

async function loadAvailableSources(sessionId = '') {
  try {
    const { data } = await getAvailableSources({ session_id: sessionId })
    availableSources.value = data || []
  } catch {}
}

function clearAllFilters() {
  selectedCountries.value = []
  selectedRegion.value = ''
  showRegionPanel.value = false
  countryMode.value = 'include'
  selectedCategory.value = ''
  selectedQuality.value = ''
  selectedProtocol.value = ''
  selectedSources.value = []
  selectedLanguage.value = ''
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
  // 隐藏点播/轮播类假台（默认开启，个人偏好不写入 URL）
  filters.hide_vod = hideVod.value ? '1' : '0'
  
  // 国家筛选（排除模式走 country_exclude 反向参数）
  if (selectedCountries.value.length > 0) {
    if (countryMode.value === 'exclude') {
      filters.country_exclude = selectedCountries.value.join(',')
    } else {
      filters.country = selectedCountries.value.join(',')
    }
  }
  
  // 地区筛选（仅中国二级，包含模式且选中国时）
  if (countryMode.value === 'include' && selectedRegion.value !== '') {
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
  
  // 来源源筛选
  if (selectedSources.value.length > 0) {
    filters.source = selectedSources.value.join(',')
  }
  
  // 语言筛选
  if (selectedLanguage.value !== '') {
    filters.language = selectedLanguage.value
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
  const tvgId = item.tvg_id ? `&tvg_id=${encodeURIComponent(item.tvg_id)}` : ''
  const tvgName = item.tvg_name && item.tvg_name !== item.name ? `&tvg_name=${encodeURIComponent(item.tvg_name)}` : ''
  let sourcesParam = ''
  if (item.sources && item.sources.length >= 1) {
    const sourcesList = item.sources.map((s, idx) => {
      // 后端 latency 可能是字符串（如 "5" 或 "-"），转为数字
      let lat = -1
      if (typeof s.latency === 'number') lat = s.latency
      else if (typeof s.latency === 'string') {
        const parsed = parseFloat(s.latency)
        if (!isNaN(parsed) && parsed >= 0) lat = parsed
      }
      return {
        url: s.url,
        source_name: s.source_name || `源${idx + 1}`,
        latency: lat,
        is_valid: s.is_valid,
        recommended: idx === (item.recommended_source_idx ?? 0),
      }
    })
    sourcesParam = `&sources=${encodeURIComponent(btoa(encodeURIComponent(JSON.stringify(sourcesList))))}`
  }
  window.open(`/player?url=${encoded}&name=${encodeURIComponent(item.name)}${radio}${region}${freq}${tvgId}${tvgName}${sourcesParam}`, '_blank')
}

async function handleCopyUrl(url) {
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = url
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  toast.success('已复制 URL', url.length > 48 ? url.slice(0, 48) + '…' : url)
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

async function selectAllItems() {
  // 已全选（含跨页全集）→ 取消全选；否则拉取初筛全集 URL 并选中
  if (allFilteredSelected.value) {
    selectedItems.value = new Set()
    return
  }
  try {
    const { data } = await getFilteredUrls(currentFilterParams())
    if (data && data.urls && data.urls.length > 0) {
      selectedItems.value = new Set(data.urls)
    } else {
      // 兜底：仅选当前页
      selectedItems.value = new Set(resultStore.checkResults.map(item => item.url))
    }
  } catch (e) {
    selectedItems.value = new Set(resultStore.checkResults.map(item => item.url))
    toast.warning('跨页全选失败', '已选中当前页')
  }
}

function openBatchFavoriteDialog() {
  if (selectedItems.value.size === 0) return
  showBatchFavoriteDialog.value = true
}

// 构建 选中URL -> 频道信息 的映射；当前页缺失时拉取当前筛选条件下的全量结果兜底（跨页全选场景）
function indexResultItem(map, item) {
  const group = item.group || item.channel_group || ''
  if (item.url && !map.has(item.url)) map.set(item.url, { name: item.name, url: item.url, group })
  if (Array.isArray(item.sources)) {
    for (const s of item.sources) {
      if (s.url && !map.has(s.url)) map.set(s.url, { name: item.name, url: s.url, group })
    }
  }
}

async function buildSelectedUrlItemMap() {
  const map = new Map()
  for (const item of resultStore.checkResults) indexResultItem(map, item)
  const hasMissing = [...selectedItems.value].some(url => !map.has(url))
  if (hasMissing) {
    try {
      const { data } = await getResults({
        ...currentFilterParams(),
        sort: resultStore.sortOrder,
        page: 1,
        per_page: 100000,
        session_id: resultStore.selectedSessionId || '',
      })
      for (const item of data.items || []) indexResultItem(map, item)
    } catch (e) {
      console.warn('跨页获取结果失败:', e)
    }
  }
  return map
}

async function doBatchFavorite(folderId) {
  showBatchFavoriteDialog.value = false
  const folderName = favoriteStore.folders.find(f => f.id === folderId)?.name || '未分类'
  const itemMap = await buildSelectedUrlItemMap()
  let added = 0
  let skipped = 0
  let failed = 0
  for (const url of selectedItems.value) {
    const item = itemMap.get(url)
    if (!item) {
      failed++
      continue
    }
    if (favoriteStore.isFavorite(url)) {
      skipped++
      continue
    }
    try {
      await favoriteStore.addFavoriteTo(item, folderId)
      added++
    } catch {
      failed++
    }
  }
  favoriteStore.setDefaultFolder(folderId)
  await favoriteStore.fetchFavorites()
  batchSelectMode.value = false
  selectedItems.value = new Set()
  const parts = [`成功 ${added} 个`]
  if (skipped > 0) parts.push(`跳过已收藏 ${skipped} 个`)
  if (failed > 0) parts.push(`失败 ${failed} 个`)
  toast.success(`批量收藏完成${failed > 0 ? '（部分失败）' : ''}`, parts.join('，'))
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
</script>
