<template>
  <div class="space-y-4">
    <!-- 历史检测 -->
    <Card>
      <CardHeader class="pb-2 flex flex-row items-center justify-between">
        <CardTitle class="text-sm font-medium flex items-center gap-2">
          <History class="h-4 w-4 text-muted-foreground" />
          历史检测
        </CardTitle>
        <Badge variant="outline" class="text-[10px]">{{ historyList.length }} 次</Badge>
      </CardHeader>
      <CardContent class="p-2 space-y-1.5 max-h-[40vh] overflow-y-auto">
        <div
          v-for="h in historyList"
          :key="h.session_id"
          class="flex items-center justify-between text-xs px-2 py-2 rounded cursor-pointer transition-colors"
          :class="h.session_id === currentSessionId ? 'bg-primary/10 border border-primary/30' : 'hover:bg-accent/50 border border-transparent'"
          @click="$emit('load-history', h.session_id)"
        >
          <div class="flex-1 min-w-0">
            <div class="font-medium truncate">{{ formatTime(h.created_at) }}</div>
            <div class="text-muted-foreground mt-0.5">{{ h.total }} 频道 · {{ h.valid }} 有效 · {{ h.invalid }} 无效</div>
          </div>
          <Badge v-if="h.session_id === currentSessionId" variant="default" class="text-[10px] ml-2 shrink-0">当前</Badge>
        </div>
        <div v-if="historyList.length === 0" class="text-xs text-muted-foreground text-center py-4">
          <Clock class="h-8 w-8 mx-auto mb-2 opacity-50" />
          暂无历史记录
        </div>
      </CardContent>
    </Card>

    <!-- 分类导航 -->
    <Card>
      <CardHeader class="pb-2">
        <CardTitle class="text-sm font-medium flex items-center gap-2">
          <FolderTree class="h-4 w-4 text-muted-foreground" />
          分类导航
        </CardTitle>
      </CardHeader>
      <CardContent class="p-2 max-h-[70vh] overflow-y-auto">
        <div v-if="categoryTree.length > 0">
          <div v-for="region in categoryTree" :key="region.name" class="mb-1">
            <button
              class="w-full flex items-center justify-between px-2 py-2 rounded text-sm font-medium hover:bg-accent/50 transition-colors"
              :class="selectedRegion === region.name && !selectedGroup ? 'bg-accent text-accent-foreground' : ''"
              @click="$emit('select-region', region.name)"
            >
              <span class="flex items-center gap-1.5">
                <ChevronRight
                  class="h-3.5 w-3.5 text-muted-foreground transition-transform"
                  :class="expandedRegion === region.name ? 'rotate-90' : ''"
                />
                {{ region.name }}
              </span>
              <span class="text-xs text-muted-foreground">{{ region.valid }}/{{ region.count }}</span>
            </button>
            <div v-if="expandedRegion === region.name" class="ml-6 space-y-0.5 mt-0.5">
              <button
                v-for="grp in region.children"
                :key="grp.name"
                class="w-full flex items-center justify-between px-2 py-1.5 rounded text-xs hover:bg-accent/50 transition-colors"
                :class="selectedGroup === grp.name ? 'bg-accent text-accent-foreground' : ''"
                @click="$emit('select-group', region.name, grp.name)"
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
        </div>
        <div v-else class="text-xs text-muted-foreground text-center py-4">
          <FolderOpen class="h-8 w-8 mx-auto mb-2 opacity-50" />
          暂无分类数据
        </div>
      </CardContent>
    </Card>

    <!-- 源健康度 -->
    <Card>
      <CardHeader class="pb-2 flex flex-row items-center justify-between">
        <CardTitle class="text-sm font-medium flex items-center gap-2">
          <HeartPulse class="h-4 w-4 text-muted-foreground" />
          源健康度
        </CardTitle>
        <Badge variant="outline" class="text-[10px]">{{ sourceHealth.length }} 个</Badge>
      </CardHeader>
      <CardContent class="p-2 space-y-1.5">
        <div
          v-for="src in sourceHealth"
          :key="src.source_name"
          class="flex items-center justify-between text-xs px-2 py-2 rounded hover:bg-accent/50 transition-colors"
          :title="src.source_name"
        >
          <span class="truncate max-w-[130px]">{{ src.source_name }}</span>
          <Badge :variant="src.success ? 'success' : 'destructive'" class="text-[10px] ml-1 shrink-0">
            {{ src.channel_count }} {{ src.success ? '成功' : '失败' }}
          </Badge>
        </div>
        <div v-if="sourceHealth.length === 0" class="text-xs text-muted-foreground text-center py-4">
          <Activity class="h-8 w-8 mx-auto mb-2 opacity-50" />
          暂无数据
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<script setup>
import { History, Clock, FolderTree, FolderOpen, HeartPulse, Activity, ChevronRight } from 'lucide-vue-next'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'

defineProps({
  historyList: { type: Array, default: () => [] },
  currentSessionId: { type: String, default: '' },
  categoryTree: { type: Array, default: () => [] },
  sourceHealth: { type: Array, default: () => [] },
  selectedRegion: { type: String, default: '' },
  selectedGroup: { type: String, default: '' },
  expandedRegion: { type: String, default: '' },
})

defineEmits(['load-history', 'select-region', 'select-group'])

function formatTime(timeStr) {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>
