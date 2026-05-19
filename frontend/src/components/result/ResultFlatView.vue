<template>
  <div class="rounded-lg border overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b bg-muted/50">
          <th class="h-10 px-3 text-left font-medium text-muted-foreground w-16">#</th>
          <th class="h-10 px-3 text-left font-medium text-muted-foreground w-48">频道名</th>
          <th class="h-10 px-3 text-left font-medium text-muted-foreground hidden md:table-cell">分组</th>
          <th class="h-10 px-3 text-left font-medium text-muted-foreground w-20">类型</th>
          <th class="h-10 px-3 text-center font-medium text-muted-foreground w-20">状态</th>
          <th class="h-10 px-3 text-center font-medium text-muted-foreground w-24">延迟</th>
          <th class="h-10 px-3 text-center font-medium text-muted-foreground w-24 hidden sm:table-cell">速度</th>
          <th class="h-10 px-3 text-center font-medium text-muted-foreground w-16">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in items"
          :key="item.index"
          class="border-b transition-colors hover:bg-accent/50"
          :class="item.is_valid ? 'border-l-4 border-l-success' : 'border-l-4 border-l-destructive'"
        >
          <td class="px-3 py-2.5 text-muted-foreground">{{ item.index }}</td>
          <td class="px-3 py-2.5 max-w-48">
            <div class="flex flex-col gap-0.5 overflow-x-auto whitespace-nowrap">
              <span class="font-medium text-sm">{{ item.name }}</span>
              <span v-if="item.clean_name" class="text-xs text-muted-foreground">{{ item.clean_name }}</span>
              <span class="text-xs text-muted-foreground truncate max-w-[200px] md:max-w-[300px] cursor-pointer hover:underline" :title="item.url" @click="$emit('copy-url', item.url)">{{ item.url }}</span>
            </div>
          </td>
          <td class="px-3 py-2.5 hidden md:table-cell">
            <Badge
              v-if="item.region"
              variant="default"
              class="text-xs bg-emerald-600 text-white dark:bg-emerald-500"
            >{{ item.region }}</Badge>
            <span v-else class="text-xs text-muted-foreground">-</span>
          </td>
          <td class="px-3 py-2.5">
            <Badge :variant="item.is_radio ? 'secondary' : 'default'" class="text-xs">
              {{ item.is_radio ? '电台' : '电视' }}
            </Badge>
            <Badge
              v-if="item.region"
              variant="default"
              class="text-[10px] ml-1 bg-emerald-600 text-white dark:bg-emerald-500"
            >{{ item.region }}</Badge>
          </td>
          <td class="px-3 py-2.5 text-center">
            <Badge :variant="(item.is_valid ?? item.has_valid) ? 'success' : 'destructive'" class="text-xs">
              {{ (item.is_valid ?? item.has_valid) ? '有效' : '无效' }}
            </Badge>
          </td>
          <td class="px-3 py-2.5 text-center">{{ (item.latency && item.latency !== '-') ? item.latency + 'ms' : '-' }}</td>
          <td class="px-3 py-2.5 text-center hidden sm:table-cell">{{ item.speed || '-' }}</td>
          <td class="px-3 py-2.5 text-center">
            <div class="flex items-center justify-center gap-1">
              <Button variant="ghost" size="icon" class="h-8 w-8" @click="$emit('toggle-favorite', item)">
                <Loader2 v-if="favoriteStore.isLoading" class="h-4 w-4 animate-spin text-muted-foreground" />
                <Star v-else-if="favoriteStore.isFavorite(item.url)" class="h-4 w-4 fill-primary text-primary" />
                <Star v-else class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" class="h-8 w-8" @click="$emit('open-epg', item)">
                <Calendar class="h-4 w-4" />
              </Button>
              <Button v-if="(item.is_valid ?? item.has_valid)" variant="ghost" size="icon" class="h-8 w-8" @click="$emit('open-player', item.name, item.url)">
                <PlayCircle class="h-4 w-4" />
              </Button>
            </div>
          </td>
        </tr>
        <tr v-if="items.length === 0">
          <td colspan="8" class="px-3 py-12 text-center text-muted-foreground">
            <SearchX class="h-12 w-12 mx-auto mb-3 opacity-50" />
            暂无数据
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { Calendar, PlayCircle, SearchX, Star, Loader2 } from 'lucide-vue-next'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { useFavoriteStore } from '../../stores/favorite'

const favoriteStore = useFavoriteStore()

defineProps({
  items: { type: Array, default: () => [] },
})

defineEmits(['open-epg', 'open-player', 'copy-url', 'toggle-favorite'])
</script>
