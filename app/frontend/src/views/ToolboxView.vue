<template>
  <div class="space-y-8">
    <div class="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/30 rounded-xl flex items-center gap-3 text-sm text-amber-800 dark:text-amber-200 shadow-sm">
      <HelpCircle class="w-5 h-5 text-amber-600 flex-shrink-0" />
      <span>
        不知道从哪开始？先
        <a href="#" @click.prevent="$router.push('/source')" class="underline font-bold hover:text-amber-900 dark:hover:text-amber-100">去选源检测</a>
        ，再回来用下方工具维护你的直播源。
      </span>
    </div>

    <div class="space-y-4">
      <div class="flex items-center gap-2 border-b pb-2">
        <h3 class="font-extrabold text-base">🔥 小白必备 (初次使用/最常用功能)</h3>
        <Badge variant="destructive" class="text-[10px]">推荐</Badge>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div
          v-for="tool in beginnerTools" :key="tool.title"
          class="bg-card border rounded-xl p-6 shadow-sm hover:-translate-y-1 hover:shadow-md transition-all duration-300 group cursor-pointer flex flex-col justify-between"
          @click="tool.action"
        >
          <div class="space-y-3">
            <div class="flex justify-between items-start">
              <div :class="cn('p-3 rounded-xl', tool.iconBg, tool.iconColor)">
                <component :is="tool.icon" class="w-5 h-5" />
              </div>
              <Badge v-if="tool.badge" :class="cn('text-[10px] uppercase tracking-wide', tool.badgeClass)" :variant="tool.badgeVariant || 'secondary'">
                {{ tool.badge }}
              </Badge>
            </div>
            <div>
              <h4 class="font-bold text-base">{{ tool.title }}</h4>
              <p class="text-xs text-muted-foreground mt-1 leading-relaxed">{{ tool.desc }}</p>
            </div>
          </div>
          <div class="mt-6 pt-4 border-t flex items-center justify-between text-xs font-semibold text-primary">
            <span>{{ tool.actionLabel }}</span>
            <ArrowRight class="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-4">
      <div class="flex items-center gap-2 border-b pb-2">
        <h3 class="font-extrabold text-base">⚙️ 极客进阶 (自动化维护与系统深度管理)</h3>
        <Badge variant="secondary" class="text-[10px]">高阶</Badge>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div
          v-for="tool in advancedTools" :key="tool.title"
          class="bg-card border rounded-xl p-5 shadow-sm opacity-85 hover:opacity-100 transition-opacity group cursor-pointer flex flex-col justify-between"
          @click="tool.action"
        >
          <div class="space-y-2">
            <span class="text-muted-foreground block">
              <component :is="tool.icon" class="w-5 h-5" />
            </span>
            <h4 class="font-bold text-sm">{{ tool.title }}</h4>
            <p class="text-xs text-muted-foreground leading-relaxed">{{ tool.desc }}</p>
          </div>
          <div class="mt-4 text-xs font-medium text-muted-foreground group-hover:text-foreground flex items-center justify-between transition-colors">
            <span>{{ tool.actionLabel }}</span>
            <ChevronRight class="w-3.5 h-3.5" />
          </div>
        </div>
      </div>
    </div>

    <!-- 格式转换 -->
    <Dialog v-model:open="showFormatConvert">
      <DialogHeader><DialogTitle>直播源格式一键转换</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-4">
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
          <input ref="convertInput" type="file" accept=".m3u,.txt" class="hidden" @change="handleConvertFile" />
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
        <Button class="w-full gap-2" :disabled="!convertFile || converting" @click="doConvert">
          <Loader2 v-if="converting" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          开始转换
        </Button>
      </div>
    </Dialog>

    <!-- 订阅管理 -->
    <Dialog v-model:open="showSubscription">
      <DialogHeader><DialogTitle>在线订阅链接管理</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <div class="flex gap-2">
          <Input v-model="subName" placeholder="订阅名称" class="flex-1" />
          <Input v-model="subUrl" placeholder="订阅 URL (http://...)" class="flex-[2]" @keyup.enter="addSubscription" />
          <Button :disabled="!subUrl || loadingSubs" @click="addSubscription">
            <Plus class="h-4 w-4" /> 添加
          </Button>
        </div>
        <Button variant="outline" class="w-full gap-2" :disabled="subscriptions.length === 0 || syncingSubs" @click="syncSubscription">
          <Loader2 v-if="syncingSubs" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          {{ syncingSubs ? '同步中...' : '立即同步订阅' }}
        </Button>
        <div v-if="subscriptions.length === 0" class="text-xs text-muted-foreground text-center py-4">暂无订阅</div>
        <div v-else class="space-y-2">
          <div v-for="sub in subscriptions" :key="sub.id" class="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <span class="font-medium truncate max-w-[40%]">{{ sub.name }}</span>
            <span class="text-xs text-muted-foreground truncate flex-1">{{ sub.url }}</span>
            <button class="text-muted-foreground hover:text-destructive" @click="removeSubscription(sub.id)">
              <X class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div v-if="syncResults.length > 0" class="space-y-2 rounded-lg border bg-muted/30 p-3">
          <div v-for="r in syncResults" :key="r.name" class="text-xs">
            <span class="font-medium">{{ r.name }}</span>：
            <span :class="r.ok ? 'text-success' : 'text-destructive'">
              {{ r.ok ? `解析出 ${r.channels} 个频道` : `拉取失败 ${r.error || ''}` }}
            </span>
          </div>
          <div v-if="syncTotal > 0" class="text-xs font-semibold">合计 {{ syncTotal }} 个频道（仅预览，未写入检测库）</div>
        </div>
      </div>
    </Dialog>

    <!-- 定时检测 -->
    <Dialog v-model:open="showScheduler">
      <DialogHeader><DialogTitle>定时全自动静默检测</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-4">
        <div class="flex items-center gap-3">
          <label class="text-sm font-medium whitespace-nowrap">检测间隔</label>
          <Input v-model.number="schedulerHours" type="number" min="1" max="168" class="w-24" />
          <span class="text-sm text-muted-foreground">小时</span>
        </div>
        <div class="text-xs text-muted-foreground">
          定时任务会在后台自动对当前配置的源执行检测，不干扰其他操作。检测结果自动保存到历史。
        </div>
        <div class="rounded-lg border bg-muted/30 p-3 text-xs space-y-1">
          <div>状态：<span :class="schedulerState ? 'text-success font-medium' : 'text-muted-foreground'">{{ schedulerState ? '运行中' : '未运行' }}</span></div>
          <div v-if="schedulerConfig" class="text-muted-foreground">当前配置：间隔 {{ schedulerConfig.interval_hours ?? '-' }} 小时</div>
        </div>
        <div class="flex gap-2 justify-end">
          <Button variant="outline" :disabled="startingScheduler" @click="stopSchedulerTask">
            <Square class="h-4 w-4" /> 停止定时检测
          </Button>
          <Button :disabled="startingScheduler || schedulerHours < 1" @click="startSchedulerTask">
            <Loader2 v-if="startingScheduler" class="h-4 w-4 animate-spin" />
            <Clock v-else class="h-4 w-4" />
            启动定时检测
          </Button>
        </div>
      </div>
    </Dialog>

    <!-- M3U 局域网托管 -->
    <Dialog v-model:open="showM3u">
      <DialogHeader><DialogTitle>M3U 本地在线局域网托管</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-4">
        <div class="rounded-lg border bg-muted/30 p-3 text-xs space-y-1">
          <div>状态：<span :class="m3uState.running ? 'text-success font-medium' : 'text-muted-foreground'">{{ m3uState.running ? '托管中' : '未托管' }}</span></div>
          <div v-if="m3uState.valid_channels" class="text-muted-foreground">有效频道：{{ m3uState.valid_channels }} 个</div>
          <div v-if="m3uState.url" class="flex items-center gap-2">
            <span class="text-muted-foreground shrink-0">订阅地址：</span>
            <code class="text-primary break-all">{{ m3uState.url }}</code>
          </div>
        </div>
        <div class="text-xs text-muted-foreground">
          启动后在局域网内提供在线 M3U 地址，电视盒子、手机播放器可直接填入此链接订阅。
        </div>
        <div class="flex gap-2 justify-end">
          <Button variant="outline" :disabled="!m3uState.running || loadingM3u" @click="stopM3uTask">
            <Square class="h-4 w-4" /> 停止托管
          </Button>
          <Button :disabled="m3uState.running || loadingM3u" @click="startM3uTask">
            <Loader2 v-if="loadingM3u" class="h-4 w-4 animate-spin" />
            <Server v-else class="h-4 w-4" />
            启动托管
          </Button>
        </div>
      </div>
    </Dialog>

    <!-- 缓存清理 -->
    <Dialog v-model:open="showCache">
      <DialogHeader><DialogTitle>全站历史缓存管理</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-4">
        <div class="rounded-lg border bg-muted/30 p-3 text-xs space-y-1">
          <div v-if="cacheStats.detection" class="flex justify-between"><span class="text-muted-foreground">检测缓存</span><span>{{ cacheStats.detection.count ?? '-' }} 条</span></div>
          <div v-if="cacheStats.epg" class="flex justify-between"><span class="text-muted-foreground">EPG 缓存</span><span>{{ cacheStats.epg.count ?? '-' }} 条</span></div>
          <div v-if="cacheStats.logos" class="flex justify-between"><span class="text-muted-foreground">台标缓存</span><span>{{ cacheStats.logos.count ?? '-' }} 条</span></div>
          <div v-if="!cacheStats.detection && !cacheStats.epg && !cacheStats.logos" class="text-muted-foreground">暂无缓存数据</div>
        </div>
        <Button variant="destructive" class="w-full gap-2" :disabled="clearingCache" @click="clearAllCache">
          <Loader2 v-if="clearingCache" class="h-4 w-4 animate-spin" />
          <Trash2 v-else class="h-4 w-4" />
          一键清理全部缓存
        </Button>
      </div>
    </Dialog>

    <!-- 源健康报告 -->
    <Dialog v-model:open="showHealth" class="max-w-3xl">
      <DialogHeader><DialogTitle>源健康报告</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <div class="text-xs text-muted-foreground">基于最近一次检测结果，按有效率从低到高排列</div>
        <div v-if="healthLoading" class="text-xs text-muted-foreground py-4 text-center">加载中...</div>
        <div v-else-if="healthSources.length === 0" class="text-xs text-muted-foreground py-4 text-center">暂无健康数据，请先执行一次检测</div>
        <div v-else class="space-y-2 max-h-80 overflow-y-auto">
          <div
            v-for="h in healthSources" :key="h.source_name"
            class="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm"
            :class="h.is_healthy ? 'border-border' : 'border-destructive/40 bg-destructive/5'"
          >
            <span class="font-medium truncate flex-1 min-w-0">{{ h.source_name }}</span>
            <span class="text-xs text-muted-foreground shrink-0">{{ h.valid }}/{{ h.total }} 有效</span>
            <span class="text-xs shrink-0 w-14 text-right" :class="h.valid_rate < 60 ? 'text-destructive' : 'text-success'">{{ h.valid_rate }}%</span>
            <span v-if="h.avg_latency > 0" class="text-xs text-muted-foreground shrink-0">{{ h.avg_latency }}ms</span>
            <Badge v-if="!h.is_healthy" variant="destructive" class="text-[10px] shrink-0">异常</Badge>
          </div>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  RefreshCw, Rss, Zap, Clock, Server, Trash2,
  ArrowRight, ChevronRight, HelpCircle,
  Upload, FileText, Loader2, Plus, X, Square,
} from 'lucide-vue-next'
import {
  convertText, getSubscriptions, addSubscription as addSubApi, deleteSubscription as deleteSubApi,
  syncSubscriptions, startScheduler, stopScheduler, getSchedulerState,
  startM3uServer, stopM3uServer, getM3uState,
  getCacheStats, clearCache, getSourceHealth, getRecommendM3u,
} from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'

const { toast } = useToast()

const showFormatConvert = ref(false)
const showSubscription = ref(false)
const showScheduler = ref(false)
const showM3u = ref(false)
const showCache = ref(false)
const showHealth = ref(false)
const convertInput = ref(null)
const convertFile = ref(null)
const convertOutputFormat = ref('m3u')
const converting = ref(false)
const subName = ref('')
const subUrl = ref('')
const subscriptions = ref([])
const loadingSubs = ref(false)
const syncingSubs = ref(false)
const syncResults = ref([])
const syncTotal = ref(0)
const schedulerHours = ref(24)
const startingScheduler = ref(false)
const schedulerState = ref(false)
const schedulerConfig = ref(null)
const m3uState = ref({ running: false, url: '', file_exists: false, valid_channels: 0 })
const loadingM3u = ref(false)
const cacheStats = ref({})
const clearingCache = ref(false)
const healthSources = ref([])
const healthLoading = ref(false)

const beginnerTools = [
  {
    title: '直播源格式一键转换',
    desc: '傻瓜化互转。将网络上下载的 TXT 纯文本源自动生成通用的标准化 M3U 播放文件，或进行反向无损提取。',
    icon: RefreshCw,
    iconBg: 'bg-blue-50 dark:bg-blue-950/30',
    iconColor: 'text-blue-600',
    badge: '零门槛',
    badgeClass: 'animate-pulse',
    actionLabel: '立即转换格式',
    action: () => { showFormatConvert.value = true },
  },
  {
    title: '在线订阅链接管理',
    desc: '一键粘贴网络第三方直播订阅池。订阅保存后可在任意时刻手动同步，拉取解析并预览其中的频道内容。',
    icon: Rss,
    iconBg: 'bg-indigo-50 dark:bg-indigo-950/30',
    iconColor: 'text-indigo-600',
    badge: '常驻',
    badgeVariant: 'secondary',
    actionLabel: '管理第三方订阅',
    action: () => { showSubscription.value = true; loadSubscriptions() },
  },
  {
    title: '老司机最优黄金组合源',
    desc: '基于历史多次检测数据，智能挑选出综合延迟最低、成功率最高的黄金组合源，一键下载推荐列表。',
    icon: Zap,
    iconBg: 'bg-amber-50 dark:bg-amber-950/30',
    iconColor: 'text-amber-600',
    badge: '智能',
    actionLabel: '一键下载最优源',
    action: downloadRecommendM3u,
  },
]

const advancedTools = [
  {
    title: '定时全自动静默检测',
    desc: '配置定时任务，让服务器在指定间隔自动巡检所有源，检测结果自动保存，睡醒即享最净化的列表。',
    icon: Clock,
    actionLabel: '配置定时检测',
    action: () => { showScheduler.value = true; loadSchedulerState() },
  },
  {
    title: 'M3U 本地在线局域网托管',
    desc: '将清洗后的完美列表一键托管为局域网内的在线 URL，电视盒子、手机端可直接填入此链接实现云同步更新。',
    icon: Server,
    actionLabel: '获取托管订阅源',
    action: () => { showM3u.value = true; loadM3uState() },
  },
  {
    title: '全站历史缓存一键释放',
    desc: '一键深度清理历史检测沉淀的各种临时数据缓存，迅速释放系统常驻内存与空间。',
    icon: Trash2,
    actionLabel: '一键释放空间',
    action: () => { showCache.value = true; loadCacheStats() },
  },
  {
    title: '源健康报告',
    desc: '查看各源在最近一次检测中的有效率、平均延迟与异常告警，及时发现需要替换的劣质源。',
    icon: HelpCircle,
    actionLabel: '查看健康报告',
    action: () => { showHealth.value = true; loadHealth() },
  },
]

onMounted(() => {
  getM3uState().then(({ data }) => { m3uState.value = data }).catch(() => {})
})

// ---------- 格式转换 ----------
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
    const res = await convertText({ content, from_format: fromFormat, to_format: toFormat })
    const ext = toFormat === 'm3u' ? 'm3u' : 'txt'
    const outputName = convertFile.value.name.replace(/\.[^.]+$/, '') + '_converted.' + ext
    downloadText(res.data.content, outputName, `text/${toFormat === 'm3u' ? 'x-mpegurl' : 'plain'}`)
    toast.success('转换成功')
    showFormatConvert.value = false
  } catch (e) {
    toast.error('转换失败', e.message)
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
  a.click()
  URL.revokeObjectURL(url)
}

// ---------- 订阅管理 ----------
async function loadSubscriptions() {
  loadingSubs.value = true
  try {
    const { data } = await getSubscriptions()
    subscriptions.value = data.subscriptions || []
  } catch (e) {
    toast.error('加载订阅失败', e.response?.data?.detail || e.message)
  } finally {
    loadingSubs.value = false
  }
}

async function addSubscription() {
  if (!subUrl.value) return
  try {
    const { data } = await addSubApi({ name: subName.value, url: subUrl.value })
    subscriptions.value = data.subscriptions || []
    subName.value = ''
    subUrl.value = ''
    toast.success('已添加订阅')
  } catch (e) {
    toast.error('添加订阅失败', e.response?.data?.detail || e.message)
  }
}

async function removeSubscription(id) {
  try {
    const { data } = await deleteSubApi(id)
    subscriptions.value = data.subscriptions || []
    toast.success('已删除订阅')
  } catch (e) {
    toast.error('删除订阅失败', e.response?.data?.detail || e.message)
  }
}

async function syncSubscription() {
  syncingSubs.value = true
  syncResults.value = []
  syncTotal.value = 0
  try {
    const { data } = await syncSubscriptions()
    syncResults.value = data.results || []
    syncTotal.value = data.total_channels || 0
    toast.success('订阅同步完成', `共解析 ${data.total_channels || 0} 个频道`)
  } catch (e) {
    toast.error('同步失败', e.response?.data?.detail || e.message)
  } finally {
    syncingSubs.value = false
  }
}

// ---------- 黄金组合源 ----------
async function downloadRecommendM3u() {
  try {
    const { data } = await getRecommendM3u(3)
    const url = window.URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = '黄金组合源.m3u'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    toast.success('已生成推荐列表', '已下载黄金组合源.m3u')
  } catch (e) {
    toast.error('生成推荐失败', e.response?.data?.detail || e.message)
  }
}

// ---------- 定时检测 ----------
async function loadSchedulerState() {
  try {
    const { data } = await getSchedulerState()
    schedulerState.value = (data.tasks || []).some(t => t.id === 'auto_check')
    schedulerConfig.value = data.config || null
  } catch {}
}

async function startSchedulerTask() {
  startingScheduler.value = true
  try {
    await startScheduler({ interval_hours: schedulerHours.value })
    await loadSchedulerState()
    toast.success('定时检测已启动', `每 ${schedulerHours.value} 小时自动检测一次`)
  } catch (e) {
    toast.error('启动失败', e.response?.data?.detail || e.message)
  } finally {
    startingScheduler.value = false
  }
}

async function stopSchedulerTask() {
  startingScheduler.value = true
  try {
    await stopScheduler()
    await loadSchedulerState()
    toast.success('定时检测已停止')
  } catch (e) {
    toast.error('停止失败', e.response?.data?.detail || e.message)
  } finally {
    startingScheduler.value = false
  }
}

// ---------- M3U 托管 ----------
async function loadM3uState() {
  loadingM3u.value = true
  try {
    const { data } = await getM3uState()
    m3uState.value = data
  } catch {} finally {
    loadingM3u.value = false
  }
}

async function startM3uTask() {
  loadingM3u.value = true
  try {
    await startM3uServer()
    await loadM3uState()
    toast.success('托管已启动', '局域网订阅地址已生成，可复制到电视盒子/手机')
  } catch (e) {
    toast.error('启动失败', e.response?.data?.detail || e.message)
  } finally {
    loadingM3u.value = false
  }
}

async function stopM3uTask() {
  loadingM3u.value = true
  try {
    await stopM3uServer()
    await loadM3uState()
    toast.success('托管已停止')
  } catch (e) {
    toast.error('停止失败', e.response?.data?.detail || e.message)
  } finally {
    loadingM3u.value = false
  }
}

// ---------- 缓存清理 ----------
async function loadCacheStats() {
  try {
    const { data } = await getCacheStats()
    cacheStats.value = data
  } catch {}
}

async function clearAllCache() {
  clearingCache.value = true
  try {
    const { data } = await clearCache()
    await loadCacheStats()
    toast.success('缓存已清理', `已清理：${(data.cleared || []).join(' / ') || '无'}`)
  } catch (e) {
    toast.error('清理失败', e.response?.data?.detail || e.message)
  } finally {
    clearingCache.value = false
  }
}

// ---------- 源健康报告 ----------
async function loadHealth() {
  healthLoading.value = true
  try {
    const { data } = await getSourceHealth()
    const sources = data.sources || {}
    healthSources.value = Object.values(sources).sort((a, b) => a.valid_rate - b.valid_rate)
  } catch (e) {
    toast.error('加载健康报告失败', e.response?.data?.detail || e.message)
  } finally {
    healthLoading.value = false
  }
}
</script>
