<template>
  <div class="space-y-8">
    <div class="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/30 rounded-xl flex items-center gap-3 text-sm text-amber-800 dark:text-amber-200 shadow-sm">
      <HelpCircle class="w-5 h-5 text-amber-600 flex-shrink-0" />
      <span>
        不知道从哪开始？点击
        <a href="#" @click.prevent="handleNoviceGuide" class="underline font-bold hover:text-amber-900 dark:hover:text-amber-100">新手引导向导 🎯</a>
        ，由智能管家带您玩转硬核自动化。
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

    <Dialog v-model:open="showSubscription">
      <DialogHeader><DialogTitle>在线订阅链接管理</DialogTitle></DialogHeader>
      <div class="p-6 pt-0 space-y-3">
        <Input v-model="subName" placeholder="订阅名称" />
        <Input v-model="subUrl" placeholder="订阅 URL (http://...)" />
        <Button class="w-full gap-2" :disabled="!subUrl" @click="addSubscription">
          <Plus class="h-4 w-4" /> 添加订阅
        </Button>
        <div v-if="subscriptions.length === 0" class="text-xs text-muted-foreground text-center py-4">暂无订阅</div>
        <div v-for="(sub, idx) in subscriptions" :key="idx" class="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
          <span class="font-medium truncate">{{ sub.name }}</span>
          <span class="text-xs text-muted-foreground truncate flex-1">{{ sub.url }}</span>
          <button class="text-muted-foreground hover:text-destructive" @click="subscriptions.splice(idx, 1)">
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import {
  RefreshCw, Rss, Zap, Clock, Server, Trash2 as TrashIcon,
  ArrowRight, ChevronRight, HelpCircle,
  Upload, FileText, Loader2, Plus, X,
} from 'lucide-vue-next'
import { convertText } from '../api'
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
const convertInput = ref(null)
const convertFile = ref(null)
const convertOutputFormat = ref('m3u')
const converting = ref(false)
const subName = ref('')
const subUrl = ref('')
const subscriptions = ref([])

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
    desc: '一键粘贴网络第三方直播订阅池。系统会在启动时全自动同步拉取最新变动，不需要一次次手动下载文件。',
    icon: Rss,
    iconBg: 'bg-indigo-50 dark:bg-indigo-950/30',
    iconColor: 'text-indigo-600',
    badge: '常驻',
    badgeVariant: 'secondary',
    actionLabel: '管理第三方订阅',
    action: () => { showSubscription.value = true },
  },
  {
    title: '老司机最优黄金组合源',
    desc: '利用历史多次体检大盘指标，AI 全自动帮您整合出一套综合延迟最低、4K成功率最高的"黄金极速收藏夹"。',
    icon: Zap,
    iconBg: 'bg-amber-50 dark:bg-amber-950/30',
    iconColor: 'text-amber-600',
    badge: '智能',
    actionLabel: '一键生成最优源',
    action: () => { toast.info('即将推出', 'AI 智能源推荐功能即将上线') },
  },
]

const advancedTools = [
  {
    title: '定时全自动静默检测',
    desc: '配置自动化 Cron 表达式，让服务器/系统在每日凌晨半夜自动帮您巡检所有源，睡醒即享最净化的列表。',
    icon: Clock,
    actionLabel: '配置自动化 Cron',
    action: () => { toast.info('即将推出', '定时检测配置功能即将上线') },
  },
  {
    title: 'M3U 本地在线局域网托管',
    desc: '将您清洗后的完美列表一键托管为局域网内的在线 URL，电视盒子、手机端可直接填入此链接实现云同步更新。',
    icon: Server,
    actionLabel: '获取托管订阅源',
    action: () => { toast.info('即将推出', '局域网托管功能即将上线') },
  },
  {
    title: '全站历史缓存一键释放',
    desc: '一键深度清理历史检测沉淀的各种临时视频分片残余及过期日志，迅速释放系统常驻内存与空间。',
    icon: TrashIcon,
    actionLabel: '一键释放空间',
    action: () => { toast.info('即将推出', '缓存清理功能即将上线') },
  },
]

function handleNoviceGuide() {
  toast.info('即将启动', '小白专属工具箱交互向导，3步轻松学会格式转换与定时自动更新！')
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

function addSubscription() {
  if (!subUrl.value) return
  subscriptions.value.push({ name: subName.value || '自定义订阅', url: subUrl.value })
  subName.value = ''
  subUrl.value = ''
  toast.success('已添加', '订阅已添加，系统将在启动时自动同步')
}
</script>
