<template>
  <Dialog :open="open" class="max-w-2xl!" @update:open="$emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle class="flex items-center gap-2">
        <Download class="h-5 w-5" />
        导出检测结果
      </DialogTitle>
    </DialogHeader>

    <div class="max-h-[60vh] space-y-4 overflow-y-auto overscroll-contain p-6 pt-0">
      <div class="space-y-2">
        <label class="text-sm font-medium">导出格式</label>
        <div class="grid grid-cols-2 gap-2">
          <label
            v-for="fmt in formats"
            :key="fmt.value"
            class="flex items-center gap-2 rounded-lg border p-3 cursor-pointer transition-colors hover:bg-accent"
            :class="selectedFormats.includes(fmt.value) ? 'border-primary bg-primary/5' : 'border-border'"
          >
            <input
              type="checkbox"
              :value="fmt.value"
              v-model="selectedFormats"
              class="rounded border-muted-foreground"
            />
            <span class="text-sm">{{ fmt.label }}</span>
          </label>
        </div>
      </div>

      <div
        class="flex items-center gap-2 rounded-lg border p-3 cursor-pointer transition-colors hover:bg-accent"
        :class="withLogo ? 'border-primary bg-primary/5' : 'border-border'"
        title="台标走远程 CDN，Kodi 导入时开机逐个下载会导致启动缓慢，建议保持关闭"
      >
        <input id="withLogo" type="checkbox" v-model="withLogo" class="rounded border-muted-foreground" />
        <div>
          <label for="withLogo" class="text-sm cursor-pointer">包含台标</label>
          <div class="text-xs text-muted-foreground">远程台标会让 Kodi 开机变慢，建议关闭</div>
        </div>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">导出范围</label>
        <div class="grid grid-cols-2 gap-2">
          <label
            v-for="scope in scopes"
            :key="scope.value"
            class="flex items-center gap-2 rounded-lg border p-3 cursor-pointer transition-colors hover:bg-accent"
            :class="exportScope === scope.value ? 'border-primary bg-primary/5' : 'border-border'"
          >
            <input type="radio" :value="scope.value" v-model="exportScope" class="accent-primary" />
            <div>
              <div class="text-sm">{{ scope.label }}</div>
              <div class="text-xs text-muted-foreground">{{ scope.desc }}</div>
            </div>
          </label>
        </div>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">媒体类型</label>
        <div class="flex gap-2">
          <Button
            v-for="mt in mediaTypes" :key="mt.value"
            size="sm" variant="outline"
            :class="mediaType === mt.value ? 'border-primary text-primary bg-primary/5' : ''"
            @click="mediaType = mt.value"
          >{{ mt.label }}</Button>
        </div>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">国家/地区</label>
        <div class="flex gap-2">
          <Button
            v-for="cs in countryScopes" :key="cs.value"
            size="sm" variant="outline"
            :class="countryScope === cs.value ? 'border-primary text-primary bg-primary/5' : ''"
            @click="setCountryScope(cs.value)"
          >{{ cs.label }}</Button>
        </div>
        <div v-if="availableCountries.length > 0" class="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto rounded-lg border p-2">
          <Button
            v-for="c in availableCountries" :key="c.code"
            size="sm" variant="outline"
            class="h-7 px-2 text-xs"
            :class="selectedCountries.includes(c.code) ? 'border-primary text-primary bg-primary/5' : ''"
            @click="toggleCountry(c.code)"
          >{{ c.flag }} {{ c.name }}</Button>
        </div>
        <div v-else class="text-xs text-muted-foreground">当前检测结果无可用国家数据</div>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">文件名前缀</label>
        <Input v-model="baseName" placeholder="检测结果" />
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">导出模式</label>
        <Select v-model="exportMode">
          <option value="merged">合并导出</option>
          <option value="by_group">按分组导出</option>
          <option value="by_source">按源导出</option>
        </Select>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">播放器内频道分组</label>
        <Select v-model="groupMode">
          <option value="original">保持原分组</option>
          <option value="media">只按 电视 / 广播</option>
          <option value="media_country">电视/广播 × 国家地区（推荐）</option>
        </Select>
        <div class="text-xs text-muted-foreground">
          选「电视/广播 × 国家地区」时：外语台自动标注国家（如 电视·日本），港澳台归 香港/澳门/台湾，
          国内细分为 央视/卫视/省份，实在判不出的进「未识别」——一眼就能看出某台属于哪里。
        </div>
      </div>

      <div
        class="flex items-center gap-2 rounded-lg border p-3 cursor-pointer transition-colors hover:bg-accent"
        :class="annotateCountryName ? 'border-primary bg-primary/5' : 'border-border'"
      >
        <input id="annotateName" type="checkbox" v-model="annotateCountryName" class="rounded border-muted-foreground" />
        <div>
          <label for="annotateName" class="text-sm cursor-pointer">外语频道名加国家前缀</label>
          <div class="text-xs text-muted-foreground">
            播放器显示名加「国旗+归属」，如 🇯🇵 日本 NHK World；不改频道原名，不影响 EPG 节目单匹配
          </div>
        </div>
      </div>
    </div>

    <DialogFooter class="flex-wrap gap-2">
      <Button variant="outline" @click="$emit('update:open', false)">取消</Button>
      <Button
        :disabled="exporting"
        @click="exportPlaylistEpgZip"
        title="M3U 播放列表 + 仅本列表频道的瘦身节目单，解压后两文件放同一目录，Kodi 本地路径导入即可秒出节目单"
      >
        <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
        导出 M3U+节目单(ZIP)
      </Button>
      <Button :disabled="selectedFormats.length === 0 || exporting" @click="doExport">
        <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
        导出
      </Button>
    </DialogFooter>
  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Download, Loader2 } from 'lucide-vue-next'
import { exportResults, exportPlaylistEpg, getAvailableCountries } from '../api'
import { useToast } from '../composables/useToast'
import { Dialog, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Select } from './ui/select'

const props = defineProps({
  open: { type: Boolean, default: false },
  selectedUrls: { type: Array, default: () => [] },
  selectedGroups: { type: Array, default: () => [] },
})

defineEmits(['update:open'])

const selectedFormats = ref(['m3u'])
const baseName = ref('检测结果')
const exportMode = ref('merged')
const exportScope = ref('valid')
const withLogo = ref(false)
const exporting = ref(false)
const mediaType = ref('all')
const countryScope = ref('all')
const selectedCountries = ref([])
const availableCountries = ref([])
const groupMode = ref('original')
const annotateCountryName = ref(false)
const { toast } = useToast()

const mediaTypes = [
  { label: '全部', value: 'all' },
  { label: '电视', value: 'tv' },
  { label: '广播', value: 'radio' },
]
const countryScopes = [
  { label: '全部', value: 'all' },
  { label: '国内', value: 'domestic' },
  { label: '国外', value: 'foreign' },
]

function toggleCountry(code) {
  const i = selectedCountries.value.indexOf(code)
  if (i > -1) selectedCountries.value.splice(i, 1)
  else selectedCountries.value.push(code)
  countryScope.value = 'all'
}

function setCountryScope(scope) {
  countryScope.value = scope
  selectedCountries.value = []
}

watch(() => props.open, async (open) => {
  if (open && availableCountries.value.length === 0) {
    try {
      const { data } = await getAvailableCountries()
      availableCountries.value = data || []
    } catch {}
  }
})

const formats = [
  { label: 'M3U 播放列表', value: 'm3u' },
  { label: 'M3U8 播放列表', value: 'm3u8' },
  { label: 'TXT 频道列表', value: 'txt' },
  { label: 'CSV 表格', value: 'csv' },
  { label: 'EPG 节目单(瘦身)', value: 'epg' },
]

const scopes = [
  { label: '仅有效频道', value: 'valid', desc: '过滤掉无效源' },
  { label: '全部频道', value: 'all', desc: '包含无效源' },
  { label: '仅选中频道', value: 'selected', desc: '导出勾选的频道' },
]

async function doExport() {
  exporting.value = true
  try {
    const payload = {
      format: '',
      base_name: baseName.value,
      export_mode: exportMode.value,
      only_valid: exportScope.value === 'valid',
      media_type: mediaType.value,
      country_scope: countryScope.value,
      countries: selectedCountries.value,
      with_logo: withLogo.value,
      group_mode: groupMode.value,
      annotate_country_name: annotateCountryName.value,
    }
    if (exportScope.value === 'selected' && props.selectedUrls.length > 0) {
      payload.channel_urls = props.selectedUrls
      payload.only_valid = false
    }
    if (props.selectedGroups.length > 0) {
      payload.groups = props.selectedGroups
    }
    const files = []
    for (const format of selectedFormats.value) {
      payload.format = format
      const { data } = await exportResults(payload)
      if (data && Array.isArray(data.exported)) {
        files.push(...data.exported)
      }
    }
    if (files.length > 0) {
      files.forEach(f => downloadExported(typeof f === 'string' ? f : (f?.filename || '')))
      toast.success(`导出成功，已开始下载 ${files.length} 个文件`)
    } else {
      toast.success('导出成功')
    }
  } catch (e) {
    toast.error('导出失败', e.response?.data?.detail || e.message)
  } finally {
    exporting.value = false
  }
}

async function exportPlaylistEpgZip() {
  exporting.value = true
  try {
    const payload = {
      base_name: baseName.value,
      only_valid: exportScope.value === 'valid',
      channel_urls: exportScope.value === 'selected' ? props.selectedUrls : [],
      groups: props.selectedGroups,
      media_type: mediaType.value,
      country_scope: countryScope.value,
      countries: selectedCountries.value,
      local_isp: '',
      with_logo: withLogo.value,
      group_mode: groupMode.value,
      annotate_country_name: annotateCountryName.value,
    }
    const { data } = await exportPlaylistEpg(payload)
    const url = window.URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${baseName.value}_播放列表+节目单.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    toast.success('已导出 M3U + 瘦身节目单 (ZIP)，解压后两文件放同一目录，Kodi 本地路径导入即可')
  } catch (e) {
    toast.error('导出失败', e.response?.data?.detail || e.message)
  } finally {
    exporting.value = false
  }
}

function downloadExported(filename) {
  if (!filename) return
  const name = String(filename).split(/[\\/]/).pop()
  const a = document.createElement('a')
  a.href = `/api/export/download?filename=${encodeURIComponent(name)}`
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>
