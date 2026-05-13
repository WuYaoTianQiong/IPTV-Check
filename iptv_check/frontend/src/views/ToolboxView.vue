<template>
  <div class="space-y-6 max-w-4xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">工具箱</h1>
      <p class="text-muted-foreground mt-1">格式转换、在线服务等实用工具</p>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <RefreshCw class="h-5 w-5 text-primary" />
            格式转换
          </CardTitle>
          <CardDescription>
            在 M3U 和 TXT 格式之间转换直播源文件
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div
            @click="convertInput?.click()"
            :class="cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors',
              'hover:border-primary/50 hover:bg-primary/5',
              convertFile ? 'border-primary bg-primary/5' : 'border-border'
            )"
          >
            <Upload class="h-6 w-6 mx-auto text-muted-foreground mb-2" />
            <p class="text-sm font-medium">点击选择要转换的文件</p>
            <p class="text-xs text-muted-foreground mt-1">支持 .m3u, .txt</p>
            <input
              ref="convertInput"
              type="file"
              accept=".m3u,.txt"
              class="hidden"
              @change="handleConvertFile"
            />
          </div>

          <div v-if="convertFile" class="flex items-center gap-2 rounded-lg bg-accent px-3 py-2">
            <FileText class="h-4 w-4 text-muted-foreground" />
            <span class="text-sm flex-1 truncate">{{ convertFile.name }}</span>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium">输出格式</label>
            <Select v-model="convertOutputFormat">
              <option value="m3u">M3U 播放列表</option>
              <option value="txt">TXT 频道列表</option>
            </Select>
          </div>

          <Button
            class="w-full gap-2"
            :disabled="!convertFile || converting"
            @click="doConvert"
          >
            <Loader2 v-if="converting" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            开始转换
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Globe class="h-5 w-5 text-primary" />
            M3U 在线服务
          </CardTitle>
          <CardDescription>
            将有效源以 M3U 格式提供在线访问
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center justify-between rounded-lg border p-4">
            <div class="flex items-center gap-3">
              <div
                :class="cn(
                  'w-3 h-3 rounded-full',
                  m3uRunning ? 'bg-success' : 'bg-muted-foreground'
                )"
              />
              <div>
                <div class="text-sm font-medium">服务状态</div>
                <div class="text-xs text-muted-foreground">
                  {{ m3uRunning ? '运行中' : '已停止' }}
                </div>
              </div>
            </div>
            <Button
              :variant="m3uRunning ? 'destructive' : 'default'"
              size="sm"
              @click="toggleM3uServer"
            >
              {{ m3uRunning ? '停止服务' : '启动服务' }}
            </Button>
          </div>

          <div v-if="m3uUrl" class="space-y-2">
            <label class="text-sm font-medium">服务地址</label>
            <div class="flex gap-2">
              <Input :value="m3uUrl" readonly class="flex-1" />
              <Button variant="outline" size="icon" class="shrink-0" @click="copyM3uUrl">
                <Copy class="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Sparkles class="h-5 w-5 text-primary" />
            智能源推荐
          </CardTitle>
          <CardDescription>
            基于 ISP 和延迟自动推荐最优频道组合
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center gap-2">
            <span class="text-sm text-muted-foreground">每组最多</span>
            <select v-model="recMaxPerGroup" class="rounded border bg-card px-2 py-1 text-sm w-16">
              <option :value="1">1</option>
              <option :value="2">2</option>
              <option :value="3">3</option>
              <option :value="5">5</option>
            </select>
            <span class="text-sm text-muted-foreground">个源</span>
          </div>

          <Button class="w-full gap-2" @click="loadRecommendations" :disabled="loadingRecs">
            <Loader2 v-if="loadingRecs" class="h-4 w-4 animate-spin" />
            <Sparkles v-else class="h-4 w-4" />
            生成推荐
          </Button>

          <div v-if="recTotal > 0" class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span>推荐频道: <strong>{{ recTotal }}</strong></span>
              <span>总源数: <strong>{{ recVariants }}</strong></span>
            </div>
            <Button variant="outline" class="w-full gap-2" @click="downloadRecM3u">
              <Download class="h-4 w-4" />
              下载推荐 M3U
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  RefreshCw,
  Upload,
  FileText,
  Globe,
  Copy,
  Loader2,
  Sparkles,
  Download,
} from 'lucide-vue-next'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { startM3uServer, stopM3uServer, getRecommendations, getRecommendM3u } from '../api'

const convertInput = ref(null)
const convertFile = ref(null)
const convertOutputFormat = ref('m3u')
const converting = ref(false)
const m3uRunning = ref(false)
const m3uUrl = ref('')
const m3uPort = ref(8080)

const recMaxPerGroup = ref(3)
const loadingRecs = ref(false)
const recTotal = ref(0)
const recVariants = ref(0)

onMounted(async () => {
  try {
    const res = await fetch('/api/m3u/state')
    const data = await res.json()
    if (data.running) {
      m3uRunning.value = true
      m3uUrl.value = data.url
    }
  } catch {}
})

async function toggleM3uServer() {
  try {
    if (m3uRunning.value) {
      await stopM3uServer()
      m3uRunning.value = false
      m3uUrl.value = ''
    } else {
      const { data } = await startM3uServer()
      if (data.url) {
        m3uRunning.value = true
        m3uUrl.value = data.url
      } else {
        alert('M3U 服务启动失败')
      }
    }
  } catch (e) {
    alert(`操作失败: ${e.response?.data?.message || e.message}`)
  }
}

async function copyM3uUrl() {
  try {
    await navigator.clipboard.writeText(m3uUrl.value)
    alert('已复制到剪贴板')
  } catch {
    alert('复制失败')
  }
}

async function loadRecommendations() {
  loadingRecs.value = true
  try {
    const { data } = await getRecommendations(recMaxPerGroup.value)
    if (data.error) {
      alert(data.error)
      return
    }
    recTotal.value = data.total_channels
    recVariants.value = data.total_variants
  } catch (e) {
    alert(`推荐失败: ${e.response?.data?.message || e.message}`)
  } finally {
    loadingRecs.value = false
  }
}

async function downloadRecM3u() {
  try {
    const res = await getRecommendM3u(recMaxPerGroup.value)
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'recommended.m3u'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('下载失败')
  }
}

function handleConvertFile(e) {
  const file = e.target.files?.[0]
  if (file) convertFile.value = file
}

async function doConvert() {
  if (!convertFile.value) return
  converting.value = true
  try {
    const content = await readFileAsText(convertFile.value)
    const fromFormat = convertFile.value.name.endsWith('.m3u') ? 'm3u' : 'txt'
    const toFormat = convertOutputFormat.value

    const res = await fetch('/api/convert-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, from_format: fromFormat, to_format: toFormat }),
    })

    if (!res.ok) {
      const err = await res.json()
      alert(`转换失败: ${err.detail || '未知错误'}`)
      return
    }

    const data = await res.json()
    const ext = toFormat === 'm3u' ? 'm3u' : 'txt'
    const outputName = convertFile.value.name.replace(/\.[^.]+$/, '') + '_converted.' + ext
    downloadText(data.content, outputName, `text/${toFormat === 'm3u' ? 'x-mpegurl' : 'plain'}`)
  } catch (e) {
    alert(`转换失败: ${e.message}`)
  } finally {
    converting.value = false
  }
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

function downloadText(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
</script>
