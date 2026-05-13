<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">检测结果</h1>
        <p class="text-muted-foreground mt-1">
          共 {{ store.resultsTotal }} 条记录 · 有效 {{ store.validCount }} · 无效 {{ store.invalidCount }}
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" class="gap-2" @click="store.activeView = 'source'">
          <ArrowLeft class="h-4 w-4" />
          返回选源
        </Button>
        <Button variant="outline" class="gap-2" @click="doOptimize">
          <Wand2 class="h-4 w-4" />
          智能优选
        </Button>
        <Button class="gap-2" @click="showExport = true">
          <Download class="h-4 w-4" />
          导出
        </Button>
      </div>
    </div>

    <Card>
      <CardContent class="p-4 space-y-4">
        <div class="flex flex-col sm:flex-row gap-3">
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              v-model="store.searchQuery"
              placeholder="搜索频道名或 URL..."
              class="pl-9"
              @input="onSearch"
            />
          </div>
          <div class="flex gap-2">
            <Button
              v-for="tab in tabs"
              :key="tab.value"
              variant="outline"
              size="sm"
              :class="store.currentTab === tab.value ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
              @click="switchTab(tab.value)"
            >
              {{ tab.label }}
              <Badge variant="secondary" class="ml-1.5">{{ tab.count }}</Badge>
            </Button>
          </div>
        </div>

        <div class="rounded-lg border overflow-x-auto">
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
              <tr
                v-for="item in store.checkResults"
                :key="item.index"
                class="border-b transition-colors hover:bg-accent/50"
                :class="item.is_valid ? 'border-l-2 border-l-success' : 'border-l-2 border-l-destructive'"
              >
                <td class="px-3 py-2.5 text-muted-foreground">{{ item.index }}</td>
                <td class="px-3 py-2.5">
                  <div class="font-medium">{{ item.name }}</div>
                  <div class="text-xs text-muted-foreground truncate max-w-[200px] md:max-w-[300px]">{{ item.url }}</div>
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
                  <Button
                    v-if="item.is_valid"
                    variant="ghost"
                    size="icon"
                    class="h-8 w-8"
                    @click="openPlayer(item)"
                  >
                    <PlayCircle class="h-4 w-4" />
                  </Button>
                </td>
              </tr>
              <tr v-if="store.checkResults.length === 0">
                <td colspan="7" class="px-3 py-12 text-center text-muted-foreground">
                  暂无数据
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="flex items-center justify-between">
          <div class="text-sm text-muted-foreground">
            第 {{ store.resultsPage }} 页 · 共 {{ totalPages }} 页
          </div>
          <div class="flex gap-1">
            <Button
              variant="outline"
              size="icon"
              class="h-8 w-8"
              :disabled="store.resultsPage <= 1"
              @click="changePage(store.resultsPage - 1)"
            >
              <ChevronLeft class="h-4 w-4" />
            </Button>
            <Button
              v-for="p in visiblePages"
              :key="p"
              variant="outline"
              size="sm"
              class="h-8 min-w-[2rem]"
              :class="p === store.resultsPage ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
              @click="changePage(p)"
            >
              {{ p }}
            </Button>
            <Button
              variant="outline"
              size="icon"
              class="h-8 w-8"
              :disabled="store.resultsPage >= totalPages"
              @click="changePage(store.resultsPage + 1)"
            >
              <ChevronRight class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <ExportDialog v-model:open="showExport" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  Search,
  ArrowLeft,
  Wand2,
  Download,
  PlayCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { smartOptimize } from '../api'
import { Card, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import ExportDialog from '../components/ExportDialog.vue'

const store = useAppStore()
const showExport = ref(false)
let searchTimer = null

const tabs = computed(() => [
  { value: 'all', label: '全部', count: store.checkTotal },
  { value: 'valid', label: '有效', count: store.validCount },
  { value: 'invalid', label: '无效', count: store.invalidCount },
])

const totalPages = computed(() => Math.ceil(store.resultsTotal / store.resultsPerPage) || 1)

const visiblePages = computed(() => {
  const pages = []
  const maxVisible = 7
  let start = Math.max(1, store.resultsPage - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages.value, start + maxVisible - 1)
  if (end - start + 1 < maxVisible) {
    start = Math.max(1, end - maxVisible + 1)
  }
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    store.resultsPage = 1
    store.fetchResults()
  }, 400)
}

function switchTab(tab) {
  store.currentTab = tab
  store.resultsPage = 1
  store.fetchResults()
}

function changePage(page) {
  store.resultsPage = page
  store.fetchResults()
}

function openPlayer(item) {
  const encoded = btoa(encodeURIComponent(item.url))
  window.open(`/player?url=${encoded}&name=${encodeURIComponent(item.name)}`, '_blank')
}

async function doOptimize() {
  try {
    const { data } = await smartOptimize()
    alert(`优选完成：移除 ${data.removed} 个重复/无效频道`)
    store.fetchResults()
  } catch (e) {
    console.error(e)
  }
}

watch(() => store.resultsPerPage, () => {
  store.resultsPage = 1
  store.fetchResults()
})

onMounted(() => {
  store.fetchResults()
})
</script>
