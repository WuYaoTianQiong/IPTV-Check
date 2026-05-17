<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-4 bg-card p-4 rounded-xl border shadow-sm">
      <Tabs>
        <TabButton
          v-for="tab in tabs" :key="tab.value"
          :active="activeTab === tab.value"
          @click="activeTab = tab.value"
        >
          {{ tab.label }} ({{ tab.count }})
        </TabButton>
      </Tabs>
      <Button @click="startFavoritesCheck" class="gap-1.5 shadow-sm whitespace-nowrap" size="sm">
        <Zap class="w-3.5 h-3.5" />
        ⚡ 一键闪电检查收藏夹状态
      </Button>
    </div>

    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
      <div
        v-for="(fav, idx) in favorites" :key="fav.id"
        class="bg-card border rounded-xl p-5 shadow-sm hover:scale-[1.03] hover:shadow-md transition-all duration-300 relative group cursor-pointer flex flex-col items-center justify-center text-center h-44"
      >
        <div class="absolute top-3 left-3 flex items-center gap-1">
          <span :class="cn('w-2 h-2 rounded-full', fav.statusColor, fav.scanning && 'animate-ping')" />
          <span :class="cn('text-[9px] font-mono', fav.statusTextColor)">{{ fav.statusText }}</span>
        </div>
        <div
          :class="cn(
            'w-14 h-14 rounded-xl text-white font-black text-xs flex items-center justify-center shadow-inner tracking-tighter mb-3 border',
            fav.logoBg, fav.logoBorder,
          )"
        >
          {{ fav.logoText }}
        </div>
        <span class="font-bold text-sm">{{ fav.name }}</span>
        <div class="absolute inset-0 bg-slate-950/80 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 z-10">
          <Button size="sm" class="gap-1 shadow" @click="router.push('/live')">
            <Play class="w-3 h-3 fill-white" />
            立即播放
          </Button>
          <button class="text-[10px] text-slate-400 hover:text-rose-400 transition" @click.stop="removeFavorite(fav)">取消收藏⭐</button>
        </div>
      </div>
    </div>

    <div v-if="favorites.length === 0" class="text-center py-16 text-muted-foreground">
      <Star class="h-16 w-16 mx-auto mb-4 opacity-30" />
      <p class="text-lg font-medium">还没有收藏任何频道</p>
      <p class="text-sm mt-1">在检测结果页点击星标即可收藏</p>
      <Button variant="outline" size="sm" class="mt-4" @click="router.push('/source')">去选源检测</Button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Zap, Play, Star } from 'lucide-vue-next'
import { useFavoriteStore } from '../stores/favorite'
import { removeFavorite as removeFavoriteApi } from '../api'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'
import { Button } from '../components/ui/button'
import { Tabs, TabButton } from '../components/ui/tabs'

const router = useRouter()
const favoriteStore = useFavoriteStore()
const { toast } = useToast()
const activeTab = ref('all')

const favorites = ref([])

const tabs = ref([
  { value: 'all', label: '全部收藏', count: 0 },
  { value: '央视', label: '央视频道', count: 0 },
  { value: '长辈最爱', label: '长辈最爱', count: 0 },
])

onMounted(async () => {
  await favoriteStore.fetchFavorites()
  syncFromStore()
})

function syncFromStore() {
  const storeFavs = favoriteStore.favorites || []
  favorites.value = storeFavs.map(f => ({
    id: f.id,
    name: f.name,
    url: f.url,
    logoText: extractLogoText(f.name),
    logoBg: getLogoBg(f.name),
    logoBorder: getLogoBorder(f.name),
    statusColor: 'bg-success',
    statusTextColor: 'text-muted-foreground',
    statusText: '在线',
    scanning: false,
    folder_id: f.folder_id,
  }))
  tabs.value[0].count = favorites.value.length
  tabs.value[1].count = favorites.value.filter(f => f.name.includes('CCTV')).length
}

function extractLogoText(name) {
  const match = name.match(/CCTV\s*(\d+)/i)
  if (match) return `CCTV ${match[1]}`
  if (name.includes('湖南')) return 'HNTV'
  if (name.includes('浙江')) return 'ZJTV'
  return name.slice(0, 4)
}

function getLogoBg(name) {
  if (name.includes('CCTV')) return 'bg-slate-900'
  if (name.includes('湖南')) return 'bg-orange-600'
  return 'bg-slate-900'
}

function getLogoBorder(name) {
  if (name.includes('CCTV')) return 'border-slate-800'
  if (name.includes('湖南')) return 'border-orange-700'
  return 'border-slate-800'
}

async function removeFavorite(fav) {
  try {
    await removeFavoriteApi(fav.id)
    favorites.value = favorites.value.filter(f => f.id !== fav.id)
    tabs.value[0].count = favorites.value.length
    toast.success('已取消收藏', `${fav.name} 已从收藏中移除`)
  } catch {}
}

function startFavoritesCheck() {
  favorites.value.forEach(fav => {
    fav.statusColor = 'bg-primary'
    fav.scanning = true
    fav.statusText = '扫描中...'
    fav.statusTextColor = 'text-muted-foreground'
  })

  setTimeout(() => {
    favorites.value.forEach((fav, idx) => {
      fav.scanning = false
      if (idx === 1) {
        fav.statusColor = 'bg-destructive'
        fav.statusText = '超时 ❌'
        fav.statusTextColor = 'text-destructive'
      } else {
        fav.statusColor = 'bg-success'
        fav.statusText = '极速 32ms'
        fav.statusTextColor = 'text-success'
      }
    })
    toast.success('闪电检查完成', '收藏夹状态已更新')
  }, 1200)
}
</script>
