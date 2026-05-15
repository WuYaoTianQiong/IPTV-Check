<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">源配置</h1>
        <p class="text-muted-foreground">选择要检测的直播源并配置检测参数</p>
      </div>
    </div>

    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <CloudDownload class="h-5 w-5 text-primary" />
          在线直播源
        </CardTitle>
        <CardDescription>
          从在线源库选择，已根据您的运营商自动匹配推荐
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="space-y-3 max-h-[480px] overflow-y-auto pr-1">
          <!-- 加载骨架屏 -->
          <div v-if="pageLoading" class="space-y-3">
            <div
              v-for="i in 6" :key="i"
              class="rounded-lg bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 dark:from-gray-700 dark:via-gray-600 dark:to-gray-700 animate-pulse"
              style="height:52px"
            />
            <p class="text-xs text-center text-muted-foreground mt-2">正在加载在线源列表...</p>
          </div>
          <!-- 加载失败 -->
          <div v-else-if="loadError" class="text-center py-8">
            <p class="text-sm text-destructive mb-3">{{ loadError }}</p>
            <Button variant="outline" size="sm" @click="pageLoading=true; loadError=null; store.fetchOnlineSources().then(()=>{pageLoading=false}).catch(e=>{loadError=e.message||'加载失败';pageLoading=false})">
              重新加载
            </Button>
          </div>
          <!-- 空数据（非加载状态） -->
          <div v-else-if="categorizedSources.length === 0" class="text-sm text-muted-foreground py-8 text-center">
            <p>暂无在线源数据</p>
            <Button variant="outline" size="sm" class="mt-3" @click="pageLoading=true; loadError=null; store.fetchOnlineSources().then(()=>{pageLoading=false}).catch(e=>{loadError=e.message||'加载失败';pageLoading=false})">
              重新加载
            </Button>
          </div>
          <div v-for="cat in categorizedSources" :key="cat.category" class="space-y-1">
            <h4 class="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2">
              {{ cat.category }}
            </h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-1">
              <div
                v-for="src in cat.sources"
                :key="src.id"
                @click="toggleOnline(src.id)"
                :class="cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer transition-colors',
                  selectedOnlineIds.includes(src.id)
                    ? 'bg-primary/10 border border-primary/20'
                    : 'hover:bg-accent border border-transparent',
                  !src.isp_compatible && 'opacity-50'
                )"
              >
                <div
                  :class="cn(
                    'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
                    selectedOnlineIds.includes(src.id)
                      ? 'bg-primary border-primary'
                      : 'border-muted-foreground/30'
                  )"
                >
                  <Check v-if="selectedOnlineIds.includes(src.id)" class="h-3 w-3 text-primary-foreground" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium truncate">{{ src.name }}</div>
                  <div class="flex items-center gap-1.5 mt-0.5">
                    <Badge variant="outline" class="text-[10px] px-1 py-0 h-4">{{ src.protocol }}</Badge>
                    <Badge v-if="src.quality_rating" :variant="src.quality_rating === 'S' ? 'default' : 'outline'" class="text-[10px] px-1 py-0 h-4">{{ src.quality_rating }}</Badge>
                    <span v-if="src.has_epg" class="text-[10px] text-primary">EPG</span>
                    <span v-if="src.has_logo_support" class="text-[10px] text-primary">台标</span>
                    <span class="text-xs text-muted-foreground">{{ src.isp.join(', ') }}</span>
                  </div>
                </div>
                <Badge
                  v-if="!src.isp_compatible"
                  variant="warning"
                  class="text-[10px] shrink-0"
                >
                  可能不兼容
                </Badge>
                <Badge
                  v-else-if="isIspMatch(src)"
                  variant="success"
                  class="text-[10px] shrink-0"
                >
                  推荐
                </Badge>
              </div>
            </div>
          </div>
        </div>

        <div class="flex gap-2 mt-4">
          <Button variant="outline" size="sm" @click="selectAllMatched">
            全选匹配
          </Button>
          <Button variant="outline" size="sm" @click="clearOnline">
            取消全选
          </Button>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <FileUp class="h-5 w-5 text-primary" />
            本地文件
          </CardTitle>
          <CardDescription>
            上传 M3U / M3U8 / TXT 格式的直播源文件
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            @click="fileInput?.click()"
            @dragover.prevent
            @drop.prevent="handleDrop"
            :class="cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors',
              'hover:border-primary/50 hover:bg-primary/5',
              uploadedFiles.length > 0 ? 'border-primary bg-primary/5' : 'border-border'
            )"
          >
            <Upload class="h-8 w-8 mx-auto text-muted-foreground mb-3" />
            <p class="text-sm font-medium">点击或拖拽文件到此处</p>
            <p class="text-xs text-muted-foreground mt-1">支持 .m3u, .m3u8, .txt</p>
            <input
              ref="fileInput"
              type="file"
              accept=".m3u,.m3u8,.txt"
              multiple
              class="hidden"
              @change="handleFileChange"
            />
          </div>

          <div v-if="uploadedFiles.length > 0" class="mt-4 space-y-2">
            <div
              v-for="(file, idx) in uploadedFiles"
              :key="idx"
              class="flex items-center gap-2 rounded-lg bg-accent px-3 py-2"
            >
              <FileText class="h-4 w-4 text-muted-foreground" />
              <span class="text-sm flex-1 truncate">{{ file.name }}</span>
              <button @click="removeFile(idx)" class="text-muted-foreground hover:text-destructive">
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Settings2 class="h-5 w-5 text-primary" />
            检测参数
          </CardTitle>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">连接超时</label>
              <span class="text-sm text-muted-foreground">{{ config.timeout_connect }} 秒</span>
            </div>
            <Slider v-model="config.timeout_connect" :min="1" :max="10" :step="1" />
          </div>

          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">读取超时</label>
              <span class="text-sm text-muted-foreground">{{ config.timeout_read }} 秒</span>
            </div>
            <Slider v-model="config.timeout_read" :min="3" :max="30" :step="1" />
          </div>

          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium">并发线程数</label>
              <span class="text-sm text-muted-foreground">{{ config.max_threads }}</span>
            </div>
            <Slider v-model="config.max_threads" :min="5" :max="100" :step="5" />
          </div>

          <Separator />

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium">测速</div>
              <div class="text-xs text-muted-foreground">检测下载速度（较慢但更准确）</div>
            </div>
            <Switch v-model="config.run_speed_test" />
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium">使用缓存</div>
              <div class="text-xs text-muted-foreground">加速重复检测</div>
            </div>
            <Switch v-model="config.use_cache" />
          </div>
        </CardContent>
      </Card>
    </div>

    <div class="flex justify-end">
      <button
        :disabled="!canStart || starting"
        @click="doStart"
        :class="cn(
          'inline-flex items-center gap-2 rounded-lg px-6 py-3 text-base font-semibold transition-all',
          canStart && !starting
            ? 'bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0'
            : 'bg-muted text-muted-foreground cursor-not-allowed opacity-60'
        )"
      >
        <Loader2 v-if="starting" class="h-5 w-5 animate-spin" />
        <Play v-else class="h-5 w-5" />
        {{ starting ? '启动中...' : '开始检测' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  CloudDownload,
  FileUp,
  Settings2,
  Play,
  Check,
  Upload,
  FileText,
  X,
  Loader2,
} from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import { useSourceStore } from '../stores/source'
import { useCheckStore } from '../stores/check'
import { useRouter } from 'vue-router'
import { startCheck, uploadFile } from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Slider } from '../components/ui/slider'
import { Switch } from '../components/ui/switch'
import { Separator } from '../components/ui/separator'

const store = useAppStore()
const sourceStore = useSourceStore()
const checkStore = useCheckStore()
const router = useRouter()
const { toast } = useToast()
const selectedOnlineIds = ref([])
const uploadedFiles = ref([])
const fileInput = ref(null)
const starting = ref(false)

onMounted(() => {
  sourceStore.fetchOnlineSources().catch(() => {})
})

const config = reactive({
  timeout_connect: 3,
  timeout_read: 8,
  max_threads: 80,
  run_speed_test: true,
  use_cache: true,
})

const categorizedSources = computed(() => sourceStore.categorizedSources)
const pageLoading = computed(() => sourceStore.isLoading)
const loadError = computed(() => sourceStore.error)

const canStart = computed(() => selectedOnlineIds.value.length > 0 || uploadedFiles.value.length > 0)

function isIspMatch(src) {
  return src.isp_compatible && src.isp?.includes(store.localIsp)
}

function toggleOnline(id) {
  const idx = selectedOnlineIds.value.indexOf(id)
  if (idx >= 0) selectedOnlineIds.value.splice(idx, 1)
  else selectedOnlineIds.value.push(id)
}

function selectAllMatched() {
  const matched = sourceStore.onlineSources
    .filter(s => !s.disabled && s.isp_compatible)
    .map(s => s.id)
  selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...matched])]
}

function clearOnline() {
  selectedOnlineIds.value = []
}

function handleFileChange(e) {
  const files = Array.from(e.target.files || [])
  for (const file of files) {
    if (!uploadedFiles.value.find(f => f.name === file.name)) {
      uploadedFiles.value.push(file)
    }
  }
}

function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files || [])
  for (const file of files) {
    if (!uploadedFiles.value.find(f => f.name === file.name)) {
      uploadedFiles.value.push(file)
    }
  }
}

function removeFile(idx) {
  uploadedFiles.value.splice(idx, 1)
}

async function doStart() {
  starting.value = true
  try {
    const filePaths = []
    for (const file of uploadedFiles.value) {
      const reader = new FileReader()
      const content = await new Promise((resolve, reject) => {
        reader.onload = () => resolve(reader.result)
        reader.onerror = reject
        reader.readAsDataURL(file)
      })
      const base64 = content.split(',')[1]
      const { data } = await uploadFile({ filename: file.name, content_base64: base64 })
      filePaths.push(data.path)
    }

    const payload = {
      online_source_ids: selectedOnlineIds.value,
      file_paths: filePaths,
      ...config,
    }

    router.push('/checking')
    checkStore.startCheckState(0)
    checkStore.addLog('正在启动检测...', 'info')

    await startCheck(payload)
  } catch (e) {
    console.error('启动检测失败:', e)
    checkStore.resetCheckState()
    router.push('/source')
    let msg = '启动检测失败'
    if (e.code === 'ECONNABORTED') {
      msg = '启动检测超时，请减少在线源数量或稍后重试'
    } else if (e.response?.data?.detail) {
      msg = e.response.data.detail
    } else if (e.message) {
      msg = e.message
    }
    toast.error('启动失败', msg)
  } finally {
    starting.value = false
  }
}
</script>
