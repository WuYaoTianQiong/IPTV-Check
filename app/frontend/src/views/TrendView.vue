<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold">频道质量趋势</h2>
        <p class="text-muted-foreground mt-1">基于历史检测数据分析频道稳定性</p>
      </div>
      <div class="flex items-center gap-2">
        <select v-model="daysRange" @change="loadData" class="rounded border bg-card px-3 py-1.5 text-sm">
          <option :value="3">最近 3 天</option>
          <option :value="7">最近 7 天</option>
          <option :value="14">最近 14 天</option>
          <option :value="30">最近 30 天</option>
        </select>
      </div>
    </div>

    <!-- 稳定频道排行 -->
    <Card>
      <CardHeader>
        <CardTitle class="text-lg">最稳定频道 TOP {{ topChannels.length > 0 ? Math.min(20, topChannels.length) : 0 }}</CardTitle>
        <CardDescription>基于在线率和平均延迟综合排名</CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="loading" class="py-8 text-center text-muted-foreground">加载中...</div>
        <div v-else-if="topChannels.length === 0" class="py-8 text-center text-muted-foreground">
          暂无数据，请先保存检测结果到数据库
        </div>
        <div v-else class="space-y-2">
           <div
             v-for="(ch, i) in topChannels.slice(0, 20)"
             :key="ch.id"
             class="flex items-center gap-3 rounded-lg border p-3 hover:bg-accent/50 transition-colors cursor-pointer"
             @click="selectChannel(ch)"
           >
            <div class="flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold"
                 :class="i < 3 ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'">
              {{ i + 1 }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium truncate">{{ ch.name }}</div>
              <div class="text-xs text-muted-foreground">{{ ch.group || '未分组' }}</div>
            </div>
            <div class="flex items-center gap-4 text-sm">
              <div class="text-right">
                <div class="font-medium" :class="stabilityColor(ch.online_rate)">
                  {{ ch.online_rate }}%
                </div>
                <div class="text-xs text-muted-foreground">在线率</div>
              </div>
              <div class="text-right">
                <div class="font-medium">{{ ch.avg_latency }}ms</div>
                <div class="text-xs text-muted-foreground">平均延迟</div>
              </div>
              <div class="text-right">
                <div class="font-medium">{{ ch.valid_count }}/{{ ch.total_checks }}</div>
                <div class="text-xs text-muted-foreground">在线/检测</div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- 单频道趋势详情 -->
    <Card>
      <CardHeader>
        <CardTitle class="text-lg">单频道趋势查询</CardTitle>
        <CardDescription>搜索频道名或点击上方排行榜频道查看趋势</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex gap-2 mb-4">
          <div class="relative flex-1">
            <input
              v-model="channelSearch"
              type="text"
              placeholder="输入频道名称搜索..."
              class="w-full rounded border bg-card px-3 py-2 text-sm"
              @input="onChannelSearch"
            />
            <div
              v-if="searchSuggestions.length > 0 && showSuggestions"
              class="absolute top-full left-0 right-0 mt-1 rounded border bg-popover shadow-lg z-10 max-h-48 overflow-y-auto"
            >
              <div
                v-for="ch in searchSuggestions"
                :key="ch.id"
                class="flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent cursor-pointer"
                @click="selectChannel(ch)"
              >
                <span class="font-medium">{{ ch.name }}</span>
                <span class="text-xs text-muted-foreground">{{ ch.group || '未分组' }}</span>
              </div>
            </div>
          </div>
          <Button @click="loadChannelTrend" :disabled="!selectedChannelId" class="gap-2">
            查询
          </Button>
        </div>

        <div v-if="channelLoading" class="py-8 text-center text-muted-foreground">查询中...</div>
        <div v-else-if="channelTrend" class="space-y-4">
          <!-- 稳定性统计 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="rounded-lg border p-3 text-center">
              <div class="text-2xl font-bold" :class="stabilityColor(channelStability.online_rate)">
                {{ channelStability.online_rate }}%
              </div>
              <div class="text-xs text-muted-foreground">在线率</div>
            </div>
            <div class="rounded-lg border p-3 text-center">
              <div class="text-2xl font-bold">{{ channelStability.avg_latency }}ms</div>
              <div class="text-xs text-muted-foreground">平均延迟</div>
            </div>
            <div class="rounded-lg border p-3 text-center">
              <div class="text-2xl font-bold">{{ channelStability.total_checks }}</div>
              <div class="text-xs text-muted-foreground">检测次数</div>
            </div>
            <div class="rounded-lg border p-3 text-center">
              <div class="text-2xl font-bold capitalize">{{ stabilityLabel(channelStability.stability) }}</div>
              <div class="text-xs text-muted-foreground">稳定性评级</div>
            </div>
          </div>

          <!-- 趋势图 -->
          <div class="rounded-lg border p-4">
            <h4 class="text-sm font-medium mb-3">延迟趋势</h4>
            <div class="h-48 flex items-end gap-1">
              <div
                v-for="(item, i) in channelTrend"
                :key="i"
                class="flex-1 rounded-t transition-colors hover:opacity-80"
                :class="item.is_valid ? 'bg-primary/60' : 'bg-destructive/40'"
                :style="{ height: item.is_valid ? `${Math.min(100, (item.latency / maxLatency) * 100)}%` : '10%' }"
                :title="`${item.is_valid ? item.latency + 'ms' : '离线'}\n${item.checked_at}`"
              />
            </div>
            <div class="flex justify-between text-xs text-muted-foreground mt-2">
              <span>{{ channelTrend[0]?.checked_at?.slice(0, 10) }}</span>
              <span>{{ channelTrend[channelTrend.length - 1]?.checked_at?.slice(0, 10) }}</span>
            </div>
          </div>

          <!-- 详细记录 -->
          <div class="rounded-lg border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-muted">
                <tr>
                  <th class="px-3 py-2 text-left">时间</th>
                  <th class="px-3 py-2 text-left">状态</th>
                  <th class="px-3 py-2 text-right">延迟</th>
                  <th class="px-3 py-2 text-right">速度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, i) in channelTrend.slice().reverse().slice(0, 50)" :key="i" class="border-t">
                  <td class="px-3 py-2 text-muted-foreground">{{ item.checked_at.slice(0, 16).replace('T', ' ') }}</td>
                  <td class="px-3 py-2">
                    <span class="rounded px-1.5 py-0.5 text-xs" :class="item.is_valid ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'">
                      {{ item.is_valid ? '在线' : '离线' }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-right">{{ item.is_valid ? item.latency + 'ms' : '-' }}</td>
                  <td class="px-3 py-2 text-right">{{ item.speed || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { getTopStableChannels, getChannelTrend } from '../api'
import Card from '../components/ui/card/Card.vue'
import CardHeader from '../components/ui/card/CardHeader.vue'
import CardTitle from '../components/ui/card/CardTitle.vue'
import CardContent from '../components/ui/card/CardContent.vue'
import CardDescription from '../components/ui/card/CardDescription.vue'
import { Button } from '../components/ui/button'

const daysRange = ref(7)
const topChannels = ref([])
const loading = ref(false)

const channelSearch = ref('')
const selectedChannelId = ref(null)
const searchSuggestions = ref([])
const showSuggestions = ref(true)
const channelTrend = ref(null)
const channelStability = ref({})
const channelLoading = ref(false)

const maxLatency = computed(() => {
  if (!channelTrend.value || channelTrend.value.length === 0) return 100
  const max = Math.max(...channelTrend.value.map(r => r.latency || 0))
  return max > 0 ? max : 100
})

onMounted(() => {
  loadData()
})

async function loadData() {
  loading.value = true
  try {
    const res = await getTopStableChannels(daysRange.value, 50)
    topChannels.value = res.data.channels || []
  } catch (e) {
    console.warn('加载稳定频道失败:', e)
    topChannels.value = []
  } finally {
    loading.value = false
  }
}

function onChannelSearch() {
  const q = channelSearch.value.toLowerCase().trim()
  if (!q) {
    searchSuggestions.value = []
    return
  }
  searchSuggestions.value = topChannels.value.filter(ch =>
    ch.name.toLowerCase().includes(q) || (ch.group || '').toLowerCase().includes(q)
  ).slice(0, 10)
  showSuggestions.value = true
}

function selectChannel(ch) {
  selectedChannelId.value = ch.id
  channelSearch.value = ch.name
  showSuggestions.value = false
  searchSuggestions.value = []
  loadChannelTrend()
}

async function loadChannelTrend() {
  if (!selectedChannelId.value) return
  channelLoading.value = true
  channelTrend.value = null
  channelStability.value = {}
  try {
    const res = await getChannelTrend(selectedChannelId.value, daysRange.value)
    channelTrend.value = res.data.trend || []
    channelStability.value = res.data.stability || {}
  } catch (e) {
    console.warn('加载频道趋势失败:', e)
  } finally {
    channelLoading.value = false
  }
}

function stabilityColor(rate) {
  if (rate >= 90) return 'text-success'
  if (rate >= 70) return 'text-warning'
  if (rate >= 50) return 'text-warning'
  return 'text-destructive'
}

function stabilityLabel(s) {
  const map = {
    excellent: '优秀',
    good: '良好',
    fair: '一般',
    poor: '较差',
    unknown: '未知',
  }
  return map[s] || s || '未知'
}
</script>
