<template>
  <div class="space-y-3">
    <div
      v-for="item in items"
      :key="item.index"
      class="rounded-lg border p-4 transition-all hover:border-primary/40 hover:shadow-sm"
      :class="item.has_valid ? 'border-l-4 border-l-success' : 'border-l-4 border-l-destructive'"
    >
      <div class="flex items-center gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-medium text-base">{{ item.name }}</span>
            <Badge
              v-if="item.region"
              variant="default"
              class="text-[10px] shrink-0 bg-emerald-600 text-white dark:bg-emerald-500"
            >{{ item.region }}</Badge>
            <Badge :variant="item.is_radio ? 'secondary' : 'default'" class="text-[10px] shrink-0">
              {{ item.is_radio ? '电台' : '电视' }}
            </Badge>
            <Badge
              v-if="item.is_radio && item.frequency"
              variant="default"
              class="text-[10px] shrink-0 bg-emerald-600 text-white dark:bg-emerald-500"
            >{{ item.frequency }}</Badge>
            <Badge v-if="item.source_count > 1" variant="secondary" class="text-[10px] shrink-0">
              {{ item.source_count }}源
            </Badge>
            <Badge v-if="item.valid_count > 0 && item.source_count > 1" variant="success" class="text-[10px] shrink-0">
              推荐
            </Badge>
          </div>
          <div v-if="item.sources && item.sources.length > 0" class="flex items-center gap-2 mt-1">
            <span class="text-xs text-muted-foreground truncate max-w-[300px]">{{ item.sources[0].url }}</span>
            <span v-if="item.sources[0].clean_name" class="text-xs text-muted-foreground">{{ item.sources[0].clean_name }}</span>
          </div>
          <div class="text-xs text-muted-foreground mt-1">
            有效 {{ item.valid_count }}/{{ item.source_count }}
            <span v-if="item.best_latency && item.best_latency !== '-'"> · 最优 {{ item.best_latency }}ms</span>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          <Button variant="ghost" size="icon" class="h-8 w-8" @click="$emit('toggle-favorite', item)">
            <Loader2 v-if="favoriteStore.isLoading" class="h-4 w-4 animate-spin text-muted-foreground" />
            <Star v-else-if="favoriteStore.isFavorite(getBestUrl(item))" class="h-4 w-4 fill-primary text-primary" />
            <Star v-else class="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" class="h-8 w-8" @click="$emit('open-epg', item)">
            <Calendar class="h-4 w-4" />
          </Button>
          <Button v-if="item.has_valid" variant="ghost" size="icon" class="h-8 w-8" @click="$emit('play-recommended', item)">
            <PlayCircle class="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" class="h-8 w-8" @click="$emit('toggle-expand', item.name)">
            <ChevronDown v-if="expandedChannels.has(item.name)" class="h-4 w-4" />
            <ChevronRight v-else class="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div v-if="expandedChannels.has(item.name) && item.sources" class="mt-3 space-y-1.5 border-t pt-3">
        <div
          v-for="(src, si) in item.sources"
          :key="si"
          class="flex items-center gap-2 px-3 py-2 rounded text-xs hover:bg-accent/50 transition-colors"
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
          <Button v-if="src.is_valid" variant="ghost" size="icon" class="h-6 w-6 shrink-0" @click="$emit('open-player', item.name, src.url)">
            <PlayCircle class="h-3 w-3" />
          </Button>
        </div>
      </div>
    </div>
    <div v-if="items.length === 0" class="text-center text-muted-foreground py-12">
      <SearchX class="h-12 w-12 mx-auto mb-3 opacity-50" />
      暂无数据
    </div>
  </div>
</template>

<script setup>
import { Calendar, PlayCircle, ChevronDown, ChevronRight, SearchX, Star, Loader2 } from 'lucide-vue-next'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { useFavoriteStore } from '../../stores/favorite'

const favoriteStore = useFavoriteStore()

defineProps({
  items: { type: Array, default: () => [] },
  expandedChannels: { type: Set, default: () => new Set() },
})

defineEmits(['toggle-expand', 'open-epg', 'play-recommended', 'open-player', 'toggle-favorite'])

function getBestUrl(item) {
  if (item.sources && item.sources.length > 0) {
    const best = item.sources[item.recommended_source_idx ?? 0]
    if (best) return best.url
  }
  return ''
}
</script>
