<template>
  <div class="max-w-7xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">检测报告</h1>
        <p class="text-muted-foreground mt-1">检测质量分析与源对比</p>
      </div>
      <Button @click="fetchReport" variant="outline" size="sm" :disabled="loading">
        <RefreshCw :class="cn('h-4 w-4 mr-1', loading && 'animate-spin')" />
        刷新
      </Button>
    </div>

    <div v-if="!report || report.error" class="text-center py-16">
      <BarChart3 class="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
      <p class="text-muted-foreground">{{ report?.error || '暂无检测结果，请先执行检测' }}</p>
    </div>

    <template v-else>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium text-muted-foreground">总频道数</CardTitle>
          </CardHeader>
          <CardContent>
            <div class="text-3xl font-bold">{{ report.total }}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium text-muted-foreground">有效率</CardTitle>
          </CardHeader>
          <CardContent>
            <div class="text-3xl font-bold" :class="report.valid_rate >= 70 ? 'text-success' : report.valid_rate >= 40 ? 'text-warning' : 'text-destructive'">
              {{ report.valid_rate }}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium text-muted-foreground">平均延迟</CardTitle>
          </CardHeader>
          <CardContent>
            <div class="text-3xl font-bold">{{ report.avg_latency }}<span class="text-lg text-muted-foreground">ms</span></div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-sm font-medium text-muted-foreground">延迟范围</CardTitle>
          </CardHeader>
          <CardContent>
            <div class="text-3xl font-bold">{{ report.min_latency }}<span class="text-lg text-muted-foreground">ms</span></div>
            <p class="text-xs text-muted-foreground">~ {{ report.max_latency }}ms</p>
          </CardContent>
        </Card>
      </div>

      <div class="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>延迟分布</CardTitle>
            <CardDescription>有效频道延迟区间统计</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="space-y-3">
              <div v-for="(count, range) in report.latency_distribution" :key="range" class="flex items-center gap-3">
                <span class="text-sm text-muted-foreground w-20 shrink-0">{{ range }}</span>
                <div class="flex-1 h-6 bg-secondary rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500"
                    :style="{ width: barWidth(count) + '%', background: barColor(range) }"
                  />
                </div>
                <span class="text-sm font-medium w-8 text-right">{{ count }}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>分组统计</CardTitle>
            <CardDescription>各频道分组有效数排行</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="space-y-2 max-h-64 overflow-y-auto">
              <div v-for="g in report.group_stats.slice(0, 15)" :key="g.name" class="flex items-center justify-between py-1.5 border-b last:border-0">
                <span class="text-sm truncate flex-1">{{ g.name }}</span>
                <span class="text-sm font-medium ml-2">{{ g.valid }}/{{ g.total }}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>在线源质量排行</CardTitle>
          <CardDescription>按有效率降序排列</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b">
                  <th class="text-left py-2 px-3 font-medium text-muted-foreground">排名</th>
                  <th class="text-left py-2 px-3 font-medium text-muted-foreground">源名称</th>
                  <th class="text-right py-2 px-3 font-medium text-muted-foreground">总数</th>
                  <th class="text-right py-2 px-3 font-medium text-muted-foreground">有效</th>
                  <th class="text-right py-2 px-3 font-medium text-muted-foreground">无效</th>
                  <th class="text-right py-2 px-3 font-medium text-muted-foreground">有效率</th>
                  <th class="text-right py-2 px-3 font-medium text-muted-foreground">平均延迟</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in report.source_ranking" :key="s.name" class="border-b last:border-0 hover:bg-accent/50">
                  <td class="py-2 px-3">
                    <span class="inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold" :class="i < 3 ? 'bg-primary text-primary-foreground' : 'bg-secondary'">{{ i + 1 }}</span>
                  </td>
                  <td class="py-2 px-3 font-medium">{{ s.name }}</td>
                  <td class="py-2 px-3 text-right">{{ s.total }}</td>
                  <td class="py-2 px-3 text-right text-success">{{ s.valid }}</td>
                  <td class="py-2 px-3 text-right text-destructive">{{ s.invalid }}</td>
                  <td class="py-2 px-3 text-right font-bold" :class="s.rate >= 70 ? 'text-success' : s.rate >= 40 ? 'text-warning' : 'text-destructive'">{{ s.rate }}%</td>
                  <td class="py-2 px-3 text-right">{{ s.avg_latency }}ms</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RefreshCw, BarChart3 } from 'lucide-vue-next'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { getQualityReport } from '../api'

const report = ref(null)
const loading = ref(false)

const barColors = {
  '<50ms': 'var(--color-success)',
  '50-100ms': 'var(--color-success)',
  '100-200ms': 'var(--color-warning)',
  '200-500ms': 'var(--color-warning)',
  '500ms+': 'var(--color-destructive)',
}

function barColor(range) {
  return barColors[range] || 'var(--color-muted-foreground)'
}

function barWidth(count) {
  if (!report.value?.latency_distribution) return 0
  const max = Math.max(...Object.values(report.value.latency_distribution), 1)
  return (count / max) * 100
}

async function fetchReport() {
  loading.value = true
  try {
    const res = await getQualityReport()
    report.value = res.data
  } catch {
    report.value = { error: '获取报告失败' }
  } finally {
    loading.value = false
  }
}

onMounted(fetchReport)
</script>
