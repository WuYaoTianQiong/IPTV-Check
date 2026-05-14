<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle class="flex items-center gap-2">
        <Download class="h-5 w-5" />
        导出检测结果
      </DialogTitle>
    </DialogHeader>

    <div class="space-y-4 p-6 pt-0">
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
    </div>

    <DialogFooter>
      <Button variant="outline" @click="$emit('update:open', false)">取消</Button>
      <Button :disabled="selectedFormats.length === 0 || exporting" @click="doExport">
        <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
        导出
      </Button>
    </DialogFooter>
  </Dialog>
</template>

<script setup>
import { ref } from 'vue'
import { Download, Loader2 } from 'lucide-vue-next'
import { exportResults } from '../api'
import { useToast } from '../composables/useToast'
import { Dialog, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Select } from './ui/select'

defineProps({
  open: { type: Boolean, default: false },
})

defineEmits(['update:open'])

const selectedFormats = ref(['m3u'])
const baseName = ref('检测结果')
const exportMode = ref('merged')
const exporting = ref(false)
const { toast } = useToast()

const formats = [
  { label: 'M3U 播放列表', value: 'm3u' },
  { label: 'M3U8 播放列表', value: 'm3u8' },
  { label: 'TXT 频道列表', value: 'txt' },
  { label: 'CSV 表格', value: 'csv' },
]

async function doExport() {
  exporting.value = true
  try {
    for (const format of selectedFormats.value) {
      const { data } = await exportResults({
        format,
        base_name: baseName.value,
        export_mode: exportMode.value,
      })
    }
    toast.success('导出成功')
  } catch (e) {
    toast.error('导出失败', e.response?.data?.detail || e.message)
  } finally {
    exporting.value = false
  }
}
</script>
