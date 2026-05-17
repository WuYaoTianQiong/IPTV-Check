<template>
  <div class="space-y-4">
    <!-- 搜索行 -->
    <div class="relative">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <Input
        :model-value="search"
        placeholder="搜索频道名..."
        class="pl-9"
        @update:model-value="$emit('update:search', $event); $emit('search')"
      />
    </div>

    <div class="flex flex-col lg:flex-row gap-4 lg:items-start lg:justify-between">
      <!-- 左侧：筛选条件区 -->
      <div class="flex flex-col sm:flex-row gap-3 sm:items-center flex-wrap">
        <!-- 语言选择 -->
        <div v-if="availableLanguages.length > 0" class="flex items-center gap-2">
          <Globe class="h-4 w-4 text-muted-foreground shrink-0" />
          <select
            :value="selectedLanguage"
            class="h-9 rounded-md border border-input bg-background px-3 text-sm"
            @change="$emit('switch-language', $event.target.value)"
          >
            <option value="">全部语言</option>
            <option v-for="lang in availableLanguages" :key="lang.language" :value="lang.language">
              {{ lang.language }} ({{ lang.count }})
            </option>
          </select>
        </div>

        <!-- 分隔线 -->
        <Separator orientation="vertical" class="h-6 hidden sm:block" />

        <!-- Tab 筛选 -->
        <div class="flex items-center gap-2">
          <Filter class="h-4 w-4 text-muted-foreground shrink-0" />
          <div class="flex gap-1.5">
            <Button
              v-for="tab in tabs"
              :key="tab.value"
              variant="outline"
              size="sm"
              :class="currentTab === tab.value ? 'bg-primary text-primary-foreground hover:bg-primary/90 border-primary' : ''"
              @click="$emit('switch-tab', tab.value)"
            >
              {{ tab.label }}
              <Badge variant="secondary" class="ml-1.5">{{ tab.count }}</Badge>
            </Button>
          </div>
        </div>

        <!-- 分隔线 -->
        <Separator orientation="vertical" class="h-6 hidden sm:block" />

        <!-- 媒体类型 -->
        <div class="flex items-center gap-2">
          <Tv class="h-4 w-4 text-muted-foreground shrink-0" />
          <div class="flex gap-1.5">
            <Button
              v-for="mt in mediaTypes"
              :key="mt.value"
              variant="outline"
              size="sm"
              :class="mediaType === mt.value ? 'bg-primary text-primary-foreground hover:bg-primary/90 border-primary' : ''"
              @click="$emit('switch-media-type', mt.value)"
            >
              {{ mt.label }}
            </Button>
          </div>
        </div>
      </div>

      <!-- 右侧：视图模式区 -->
      <div class="flex items-center gap-2 shrink-0">
        <span class="text-xs text-muted-foreground hidden lg:inline">视图</span>
        <div class="flex gap-1.5 border rounded-lg p-1 bg-muted/30">
          <Button
            variant="ghost"
            size="sm"
            class="h-8 gap-1.5"
            :class="viewMode === 'grouped' ? 'bg-background shadow-sm' : 'hover:bg-transparent'"
            @click="$emit('switch-view-mode', 'grouped')"
          >
            <LayoutGrid class="h-4 w-4" />
            <span class="hidden sm:inline">聚合</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            class="h-8 gap-1.5"
            :class="viewMode === 'flat' ? 'bg-background shadow-sm' : 'hover:bg-transparent'"
            @click="$emit('switch-view-mode', 'flat')"
          >
            <List class="h-4 w-4" />
            <span class="hidden sm:inline">平铺</span>
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Search, LayoutGrid, List, Filter, Tv, Globe } from 'lucide-vue-next'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Input } from '../ui/input'
import { Separator } from '../ui/separator'

defineProps({
  search: { type: String, default: '' },
  currentTab: { type: String, default: 'all' },
  tabs: { type: Array, default: () => [] },
  mediaType: { type: String, default: 'all' },
  mediaTypes: { type: Array, default: () => [] },
  viewMode: { type: String, default: 'grouped' },
  selectedLanguage: { type: String, default: '' },
  availableLanguages: { type: Array, default: () => [] },
})

defineEmits([
  'update:search',
  'search',
  'switch-tab',
  'switch-media-type',
  'switch-view-mode',
  'switch-language',
])
</script>
