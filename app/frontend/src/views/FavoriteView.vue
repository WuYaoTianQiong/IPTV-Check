<template>
  <div class="flex gap-0 h-[calc(100vh-10rem)]">
    <div v-show="!sidebarCollapsed" class="shrink-0 flex flex-col border-r border-border/60 relative" :style="{ width: sidebarWidth + 'px' }">
      <button
        class="absolute -right-3 top-2 z-20 h-6 w-6 rounded-full bg-background border border-border/60 shadow-sm flex items-center justify-center hover:bg-accent transition-colors"
        @click="toggleSidebar"
        title="折叠侧边栏"
        aria-label="折叠侧边栏"
      >
        <ChevronLeft class="h-3.5 w-3.5 text-muted-foreground" />
      </button>
      <div class="flex items-center justify-between shrink-0 px-3 py-2.5 border-b border-border/40">
        <h3 class="font-semibold text-sm">收藏夹</h3>
        <div class="flex items-center gap-1">
          <Button variant="ghost" size="icon" class="h-6 w-6" @click="showAddFolder = true" title="新建文件夹" aria-label="新建文件夹">
            <Plus class="h-3.5 w-3.5" />
          </Button>
          <Button variant="outline" size="sm" class="h-7 px-2 gap-1 text-xs" @click="showExportDialog = true">
            <Download class="h-3 w-3" />
            导出
          </Button>
          <Button variant="ghost" size="icon" class="h-6 w-6" @click="handleRefreshLatency" :disabled="isRefreshingLatency" title="刷新延迟" aria-label="刷新延迟">
            <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': isRefreshingLatency }" />
          </Button>
          <Button variant="ghost" size="icon" class="h-6 w-6" :class="batchRemoveMode ? 'text-destructive' : ''" @click="batchRemoveMode = !batchRemoveMode" title="批量管理" aria-label="批量管理">
            <Move class="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <!-- 排序栏 -->
      <div class="shrink-0 px-3 py-1.5 border-b border-border/40 flex items-center gap-2">
        <span class="text-xs text-muted-foreground whitespace-nowrap">排序</span>
        <select
          :value="favoriteStore.sortOrder"
          class="h-7 rounded-md border border-input bg-background px-2 text-[11px] flex-1 min-w-0"
          aria-label="收藏排序"
          @change="onFavSortChange($event.target.value)"
        >
          <option value="default">默认顺序</option>
          <option value="name_asc">名称 A-Z</option>
          <option value="name_desc">名称 Z-A</option>
          <option value="latency_asc">延迟低→高</option>
          <option value="latency_desc">延迟高→低</option>
        </select>
      </div>

      <div class="flex-1 overflow-y-auto space-y-0.5 px-2 py-2">
        <div v-if="favoriteStore.isLoading" class="space-y-2 py-4">
          <div v-for="i in 6" :key="i" class="h-8 rounded-lg bg-muted animate-pulse" />
        </div>

        <template v-else-if="groupedFavorites.length > 0">
          <div v-for="group in groupedFavorites" :key="group.folder.id ?? 'unfiled'" class="group/folder mb-0.5">
            <div
              :class="cn(
                'flex items-center gap-1 w-full rounded-lg px-3 py-2 text-sm transition-all relative',
                expandedFolders.has(String(group.folder.id))
                  ? 'bg-accent text-accent-foreground font-medium'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'
              )"
            >
              <span
                v-if="expandedFolders.has(String(group.folder.id))"
                class="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-primary"
              />
              <button class="flex items-center gap-2 flex-1 text-left min-w-0" @click="toggleFolder(group.folder.id)">
                <ChevronRight :class="cn('w-3.5 h-3.5 shrink-0 transition-transform', expandedFolders.has(String(group.folder.id)) && 'rotate-90')" />
                <component :is="group.folder.id === null ? Inbox : FolderIcon" class="h-4 w-4 shrink-0" />
                <template v-if="renamingFolderId === group.folder.id && group.folder.id !== null">
                  <Input
                    v-model="renamingFolderName"
                    class="h-7 text-xs flex-1 min-w-0 folder-rename-input"
                    @click.stop
                    @keyup.enter="confirmRename(group.folder.id)"
                    @keyup.esc="cancelRename"
                    @blur="confirmRename(group.folder.id)"
                    ref="renameInputRef"
                  />
                </template>
                <span v-else class="truncate flex-1">{{ group.folder.name }}</span>
              </button>
              <span class="text-xs opacity-60 shrink-0">{{ group.count }}</span>
              <template v-if="group.folder.id !== null">
                <button
                  v-if="renamingFolderId !== group.folder.id"
                  class="h-5 w-5 shrink-0 opacity-0 group-hover/folder:opacity-70 hover:opacity-100 transition-opacity flex items-center justify-center"
                  @click.stop="startRename(group.folder.id, group.folder.name)"
                  title="重命名"
                >
                  <Pencil class="h-3 w-3" />
                </button>
                <button
                  v-if="renamingFolderId !== group.folder.id"
                  class="h-5 w-5 shrink-0 opacity-0 group-hover/folder:opacity-70 hover:!opacity-100 hover:text-destructive transition-opacity flex items-center justify-center"
                  @click.stop="confirmDeleteFolder(group.folder.id, group.folder.name)"
                  title="删除"
                >
                  <Trash2 class="h-3 w-3" />
                </button>
              </template>
            </div>

            <div
              v-show="expandedFolders.has(String(group.folder.id))"
              class="mt-0.5 space-y-0.5 ml-1"
            >
              <button
                v-for="fav in group.channels" :key="fav.id"
                @click="playInline(fav)"
                class="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all text-left group/ch relative"
                :class="currentChannel?.url === fav.url ? 'bg-primary/10 text-primary font-semibold before:scale-y-100' : 'text-foreground hover:bg-accent/50 hover:translate-x-0.5 before:scale-y-0'"
                style="--tw-before-scale:1"
              >
                <span
                  :class="cn(
                    'absolute left-0 top-1/2 -translate-y-1/2 w-[2px] rounded-r-full bg-primary transition-transform origin-center',
                    currentChannel?.url === fav.url ? 'h-4 scale-y-100' : 'h-4 scale-y-0'
                  )"
                />
                <Checkbox
                  v-if="batchRemoveMode"
                  :model-value="selectedIds.has(fav.id)"
                  @click.stop="toggleSelect(fav.id)"
                  class="h-3.5 w-3.5 shrink-0"
                />
                <LatencyBadge :latency="fav.latency" class="shrink-0" />
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1">
                    <Badge v-if="fav.country && !['CN','HK','MO','TW'].includes(fav.country)" variant="secondary" class="text-[10px] shrink-0 px-1.5 py-0 h-4 bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800">{{ countryCodeToName(fav.country) }}</Badge>
                    <Badge
                      v-if="fav.region"
                      variant="default"
                      class="text-[10px] shrink-0 px-1.5 py-0 h-4 bg-emerald-600 text-white dark:bg-emerald-500"
                    >{{ fav.region }}</Badge>
                    <span class="truncate">{{ fav.name }}</span>
                  </div>
                  <span v-if="fav.name_cn && fav.name_cn !== fav.name" class="text-[10px] text-muted-foreground truncate block mt-0.5">{{ fav.name_cn }}</span>
                </div>
                <Button variant="ghost" size="icon" class="h-5 w-5 shrink-0 opacity-0 group-hover/ch:opacity-100" @click.stop="handleMoveToFolder(fav)" title="移动到文件夹">
                  <FolderInput class="h-3 w-3" />
                </Button>
                <Button variant="ghost" size="icon" class="h-5 w-5 shrink-0 opacity-0 group-hover/ch:opacity-100 text-muted-foreground hover:text-destructive" @click.stop="handleRemoveFavorite(fav)" title="取消收藏">
                  <X class="h-3 w-3" />
                </Button>
              </button>
            </div>
          </div>
        </template>

        <!-- 分页 -->
        <div v-if="!favoriteStore.isLoading && favoriteStore.favoritesTotal > 0" class="px-2 py-2 border-t border-border/40">
          <ResultPagination
            :current-page="favoriteStore.favoritesPage"
            :total-pages="favoriteStore.totalPages"
            :total="favoriteStore.favoritesTotal"
            :per-page="favoriteStore.favoritesPerPage"
            @update:current-page="changeFavPage"
            @update:per-page="changeFavPerPage"
          />
        </div>

        <div v-else class="text-center py-12 text-muted-foreground">
          <div class="w-14 h-14 mx-auto mb-3 rounded-xl bg-primary/5 flex items-center justify-center">
            <Star class="h-7 w-7 text-primary/30" />
          </div>
          <p class="text-xs font-medium">暂无收藏</p>
          <p class="text-[10px] mt-1 opacity-60">在检测结果页点击 ⭐ 即可收藏</p>
          <Button variant="outline" size="sm" class="mt-3 text-xs" @click="router.push('/source')">去选源检测</Button>
        </div>
      </div>

      <div v-if="batchRemoveMode" class="shrink-0 px-3 py-2 border-t border-border/40 bg-card/80 backdrop-blur-sm space-y-1.5">
        <div class="flex gap-1.5">
          <Button variant="outline" size="sm" class="flex-1 gap-1 text-xs h-8" @click="handleBatchMoveSelected" :disabled="selectedIds.size === 0">
            <FolderInput class="h-3 w-3" />
            移动
          </Button>
          <Button variant="outline" size="sm" class="flex-1 gap-1 text-xs h-8" @click="handleBatchExportSelected" :disabled="selectedIds.size === 0">
            <Download class="h-3 w-3" />
            导出
          </Button>
        </div>
        <Button variant="destructive" size="sm" class="w-full gap-1.5 h-8" @click="handleBatchRemove" :disabled="selectedIds.size === 0">
          <Trash2 class="h-3.5 w-3.5" />
          删除 {{ selectedIds.size }} 项
        </Button>
      </div>
    </div>

    <!-- Sidebar collapsed -->
    <div v-show="sidebarCollapsed" class="w-10 shrink-0 flex flex-col border-r border-border/60 items-center pt-3">
      <button
        class="h-7 w-7 rounded-lg flex items-center justify-center hover:bg-accent transition-colors"
        @click="toggleSidebar"
        title="展开侧边栏"
      >
        <ChevronRight class="h-4 w-4 text-muted-foreground" />
      </button>
    </div>

    <!-- Resize handle -->
    <div
      v-show="!sidebarCollapsed"
      class="w-[5px] shrink-0 cursor-col-resize relative hover:bg-primary/20 active:bg-primary/30 transition-colors"
      @mousedown="onResizeStart"
    ></div>

    <div class="flex-1 min-w-0 flex flex-col">
      <template v-if="currentChannel">
        <div class="shrink-0 flex items-center gap-2 px-4 py-2 border-b border-border/40 bg-card/80">
          <span :class="cn('w-2 h-2 rounded-full', currentChannel.is_radio ? 'bg-orange-400' : 'bg-green-500')" />
          <span class="font-medium text-sm truncate">{{ currentChannel.name }}</span>
          <Badge v-if="currentChannel.is_radio" variant="secondary" class="text-[10px]">电台</Badge>
          <Badge
            v-if="currentChannel.is_radio && currentChannel.frequency"
            variant="default"
            class="text-[10px] bg-emerald-600 text-white dark:bg-emerald-500"
          >{{ currentChannel.frequency }}</Badge>
          <Badge v-if="currentChannel.region" variant="secondary" class="text-[10px]">{{ currentChannel.region }}</Badge>
          <div class="flex-1" />
          <Button variant="ghost" size="icon" class="h-6 w-6" @click="openPlayerNewWindow(currentChannel)" title="新窗口播放">
            <ExternalLink class="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" class="h-6 w-6 text-muted-foreground hover:text-destructive" @click="stopPlayer" title="关闭播放器">
            <X class="h-3.5 w-3.5" />
          </Button>
        </div>
        <div class="flex-1 bg-black overflow-hidden relative">
          <iframe
            :src="iframeSrc"
            class="w-full h-full border-0"
            allow="autoplay; encrypted-media; fullscreen"
          />
        </div>
      </template>
      <template v-else>
        <div class="flex-1 flex items-center justify-center">
          <div class="text-center text-muted-foreground">
            <div class="w-20 h-20 mx-auto mb-5 rounded-2xl bg-primary/5 flex items-center justify-center">
              <Tv class="h-10 w-10 text-primary/30" />
            </div>
            <p class="font-medium text-foreground/70">选择一个频道开始观看</p>
            <p class="text-sm mt-1.5 opacity-50">点击左侧频道即可播放</p>
          </div>
        </div>
      </template>
    </div>
  </div>

  <Dialog v-model:open="showAddFolder">
    <DialogHeader><DialogTitle>新建收藏夹</DialogTitle></DialogHeader>
    <div class="p-6 pt-0 space-y-3">
      <Input v-model="newFolderName" placeholder="收藏夹名称" @keyup.enter="handleAddFolder" />
      <div class="flex justify-end gap-2">
        <Button variant="outline" @click="showAddFolder = false">取消</Button>
        <Button @click="handleAddFolder">创建</Button>
      </div>
    </div>
  </Dialog>

  <Dialog v-model:open="showMoveDialog">
    <DialogHeader><DialogTitle>移动到收藏夹</DialogTitle></DialogHeader>
    <div class="p-6 pt-0 space-y-3">
      <div class="max-h-56 overflow-y-auto space-y-2 pr-1">
        <div v-for="folder in allFolders.filter(f => f.id !== null)" :key="folder.id" class="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            class="w-full justify-start gap-2"
            @click="doMoveToFolder(folder.id)"
          >
            <FolderIcon class="h-3.5 w-3.5" />
            {{ folder.name }}
          </Button>
        </div>
        <Button
          variant="outline"
          size="sm"
          class="w-full justify-start gap-2"
          @click="doMoveToFolder(null)"
        >
          <Inbox class="h-3.5 w-3.5" />
          未分类
        </Button>
      </div>
      <div class="border-t pt-3 space-y-2">
        <template v-if="showMoveNewFolder">
          <div class="flex items-center gap-2">
            <Input v-model="moveNewFolderName" placeholder="收藏夹名称" class="h-8 text-xs flex-1" @keyup.enter="handleCreateFolderInMove" @keyup.esc="showMoveNewFolder = false; moveNewFolderName = ''" />
            <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="handleCreateFolderInMove" title="创建">
              <Check class="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="showMoveNewFolder = false; moveNewFolderName = ''" title="取消">
              <X class="h-3.5 w-3.5" />
            </Button>
          </div>
        </template>
        <template v-else>
          <Button variant="outline" size="sm" class="w-full gap-2" @click="showMoveNewFolder = true">
            <Plus class="h-3.5 w-3.5" />
            新建收藏夹
          </Button>
        </template>
      </div>
    </div>
  </Dialog>

  <Dialog v-model:open="showExportDialog" class="max-h-[80vh]">
    <DialogHeader>
      <DialogTitle>导出收藏</DialogTitle>
    </DialogHeader>
    <div class="px-6 pb-4 pt-0 flex gap-2 border-b">
      <Button
        variant="outline"
        size="sm"
        :class="exportMode === 'folder' ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
        @click="exportMode = 'folder'"
      >
        <FolderIcon class="h-3.5 w-3.5" />
        按文件夹导出
      </Button>
      <Button
        variant="outline"
        size="sm"
        :class="exportMode === 'channel' ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
        @click="exportMode = 'channel'"
      >
        <Star class="h-3.5 w-3.5" />
        按频道选择
      </Button>
    </div>
    <div v-if="exportMode === 'folder'" class="p-6 pt-4 space-y-3">
      <p class="text-sm text-muted-foreground">选择要导出的收藏夹</p>
      <div class="space-y-2">
        <Button
          :variant="exportFolderId === 'all' ? 'default' : 'outline'"
          size="sm"
          class="w-full justify-start gap-2"
          @click="exportFolderId = 'all'"
        >
          <FolderIcon class="h-3.5 w-3.5" />
          全部收藏
        </Button>
        <Button
          v-for="folder in allFolders.filter(f => f.id !== null)" :key="folder.id"
          :variant="exportFolderId === String(folder.id) ? 'default' : 'outline'"
          size="sm"
          class="w-full justify-start gap-2"
          @click="exportFolderId = String(folder.id)"
        >
          <FolderIcon class="h-3.5 w-3.5" />
          {{ folder.name }} ({{ folder.count }})
        </Button>
        <Button
          :variant="exportFolderId === 'null' ? 'default' : 'outline'"
          size="sm"
          class="w-full justify-start gap-2"
          @click="exportFolderId = 'null'"
        >
          <Inbox class="h-3.5 w-3.5" />
          未分类 ({{ allFolders.find(f => f.id === null)?.count || 0 }})
        </Button>
      </div>
      <div class="space-y-1.5">
        <p class="text-sm text-muted-foreground">导出格式</p>
        <div class="flex flex-wrap gap-2">
          <Button
            v-for="fmt in exportFormats"
            :key="fmt.value"
            variant="outline"
            size="sm"
            :class="exportFormat === fmt.value ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
            @click="exportFormat = fmt.value"
          >
            {{ fmt.label }}
          </Button>
        </div>
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" @click="showExportDialog = false">取消</Button>
        <Button @click="handleExportFolder">导出</Button>
      </div>
    </div>
    <div v-else class="p-6 pt-4 space-y-3">
      <div class="space-y-1.5">
        <p class="text-sm text-muted-foreground">导出格式</p>
        <div class="flex flex-wrap gap-2">
          <Button
            v-for="fmt in exportFormats"
            :key="fmt.value"
            variant="outline"
            size="sm"
            :class="exportFormat === fmt.value ? 'bg-primary text-primary-foreground hover:bg-primary/90' : ''"
            @click="exportFormat = fmt.value"
          >
            {{ fmt.label }}
          </Button>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Input v-model="exportChannelSearch" placeholder="搜索频道..." class="flex-1 text-xs" />
        <Button variant="outline" size="sm" @click="toggleSelectAllExport" class="text-xs shrink-0">
          {{ exportSelectedChannels.size === flatAllChannels.length ? '取消全选' : '全选' }}
        </Button>
      </div>
      <div class="max-h-72 overflow-y-auto space-y-1 border rounded-lg p-2">
        <div
          v-for="fav in filteredExportChannels" :key="fav.id"
          class="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent cursor-pointer text-sm"
          @click="toggleExportChannel(fav.id)"
        >
          <Checkbox
            :model-value="exportSelectedChannels.has(fav.id)"
            class="h-3.5 w-3.5 shrink-0 pointer-events-none"
          />
          <div class="min-w-0 flex-1">
            <span class="truncate block">{{ fav.name }}</span>
            <span v-if="fav.name_cn && fav.name_cn !== fav.name" class="text-[10px] text-muted-foreground truncate block">{{ fav.name_cn }}</span>
          </div>
          <Badge v-if="fav.region" variant="secondary" class="text-[10px] shrink-0">{{ fav.region }}</Badge>
        </div>
        <div v-if="filteredExportChannels.length === 0" class="text-center py-6 text-muted-foreground text-xs">
          没有匹配的频道
        </div>
      </div>
      <div class="flex items-center justify-between pt-1">
        <span class="text-xs text-muted-foreground">已选 {{ exportSelectedChannels.size }} 个频道</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" @click="showExportDialog = false">取消</Button>
          <Button size="sm" @click="handleExportSelected" :disabled="exportSelectedChannels.size === 0">
            导出所选 ({{ exportSelectedChannels.size }})
          </Button>
        </div>
      </div>
    </div>
  </Dialog>

  <AlertDialog v-model:open="showDeleteConfirm">
    <div class="space-y-3">
      <h3 class="text-lg font-semibold">删除收藏夹</h3>
      <p class="text-sm text-muted-foreground">
        确定删除收藏夹 <strong>{{ deletingFolderName }}</strong> 吗？其中的频道将移到未分类。
      </p>
      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" @click="showDeleteConfirm = false; deletingFolderId = null">取消</Button>
        <Button variant="destructive" @click="doDeleteFolder">删除</Button>
      </div>
    </div>
  </AlertDialog>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Star, Download, Plus, Trash2, X, ExternalLink, Tv, Folder as FolderIcon, Inbox, FolderInput, ChevronLeft, ChevronRight, Check, Pencil, Move, RefreshCw } from 'lucide-vue-next'
import { useFavoriteStore } from '../stores/favorite'
import { removeFavorite as removeFavoriteApi, updateFavorite, refreshFavoritesLatency } from '../api'
import { useToast } from '../composables/useToast'
import LatencyBadge from '../components/LatencyBadge.vue'
import ResultPagination from '../components/result/ResultPagination.vue'
import { cn, countryCodeToName } from '../lib/utils'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import { Dialog, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { AlertDialog } from '../components/ui/alert-dialog'

const router = useRouter()
const favoriteStore = useFavoriteStore()
const { toast } = useToast()

const expandedFolders = ref(new Set())
try {
  const saved = localStorage.getItem('iptv_fav_expanded_folders')
  if (saved) expandedFolders.value = new Set(JSON.parse(saved))
} catch {}
watch(expandedFolders, (val) => {
  try { localStorage.setItem('iptv_fav_expanded_folders', JSON.stringify([...val])) } catch {}
}, { deep: true })

// Sidebar resize & collapse
const sidebarWidth = ref(256)
const sidebarCollapsed = ref(false)

try {
  const saved = localStorage.getItem('iptv_fav_sidebar_width')
  if (saved) sidebarWidth.value = parseInt(saved, 10)
} catch {}
try {
  const saved = localStorage.getItem('iptv_fav_sidebar_collapsed')
  if (saved) sidebarCollapsed.value = saved === 'true'
} catch {}

watch(sidebarWidth, (val) => {
  localStorage.setItem('iptv_fav_sidebar_width', String(val))
})

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function onResizeStart(e) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = sidebarWidth.value

  function onMouseMove(e) {
    const newWidth = Math.max(120, Math.min(600, startWidth + e.clientX - startX))
    sidebarWidth.value = newWidth
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const batchRemoveMode = ref(false)
const selectedIds = ref(new Set())
const showAddFolder = ref(false)
const showMoveDialog = ref(false)
const showExportDialog = ref(false)
const exportMode = ref('folder')
const exportFolderId = ref('all')
const exportChannelSearch = ref('')
const exportSelectedChannels = ref(new Set())
const exportFormat = ref('m3u')

const exportFormats = [
  { label: 'M3U', value: 'm3u' },
  { label: 'M3U8', value: 'm3u8' },
  { label: 'TXT', value: 'txt' },
  { label: 'CSV', value: 'csv' },
]
const newFolderName = ref('')
const movingFav = ref(null)
const currentChannel = ref(null)
const iframeSrc = ref('')
const showMoveNewFolder = ref(false)
const moveNewFolderName = ref('')

// Folder rename state
const renamingFolderId = ref(null)
const renamingFolderName = ref('')
const renameInputRef = ref(null)

// Folder delete confirmation
const showDeleteConfirm = ref(false)
const deletingFolderId = ref(null)
const deletingFolderName = ref('')

watch(showDeleteConfirm, (val) => {
  if (!val) {
    deletingFolderId.value = null
    deletingFolderName.value = ''
  }
})

watch(showExportDialog, (val) => {
  if (!val) {
    exportMode.value = 'folder'
    exportFolderId.value = 'all'
    exportChannelSearch.value = ''
    exportSelectedChannels.value = new Set()
    exportFormat.value = 'm3u'
  }
})

const allFolders = computed(() => {
  const folders = favoriteStore.folders || []
  const unfiled = folders.find(f => f.id === null) || { id: null, name: '未分类', count: 0 }
  const named = folders.filter(f => f.id !== null)
  return [...named, unfiled]
})

const groupedFavorites = computed(() => {
  const favs = favoriteStore.favorites || []
  return allFolders.value
    .map(folder => ({
      folder,
      count: folder.id === null
        ? favs.filter(f => f.folder_id === null || f.folder_id === undefined).length
        : favs.filter(f => f.folder_id === folder.id).length,
      channels: folder.id === null
        ? favs.filter(f => f.folder_id === null || f.folder_id === undefined)
        : favs.filter(f => f.folder_id === folder.id),
    }))
    // Keep all folders visible even when empty; the filter below was hiding newly-created folders
    // .filter(g => g.channels.length > 0)
})

const flatAllChannels = computed(() => favoriteStore.favorites || [])

const filteredExportChannels = computed(() => {
  const q = exportChannelSearch.value.toLowerCase().trim()
  if (!q) return flatAllChannels.value
  return flatAllChannels.value.filter(f =>
    f.name.toLowerCase().includes(q) ||
    (f.channel_group && f.channel_group.toLowerCase().includes(q))
  )
})

onMounted(async () => {
  await favoriteStore.fetchFolders()
  await favoriteStore.fetchFavorites()
  if (groupedFavorites.value.length > 0 && expandedFolders.value.size === 0) {
    expandedFolders.value = new Set([String(groupedFavorites.value[0].folder.id)])
  }
})

function toggleFolder(folderId) {
  const key = String(folderId)
  const s = new Set(expandedFolders.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedFolders.value = s
}

function toggleSelect(id) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedIds.value = s
}

function toggleExportChannel(id) {
  const s = new Set(exportSelectedChannels.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  exportSelectedChannels.value = s
}

function toggleSelectAllExport() {
  const all = filteredExportChannels.value.map(f => f.id)
  const s = new Set(exportSelectedChannels.value)
  const allSelected = all.every(id => s.has(id))
  if (allSelected) {
    for (const id of all) s.delete(id)
  } else {
    for (const id of all) s.add(id)
  }
  exportSelectedChannels.value = s
}

function startRename(folderId, currentName) {
  if (folderId === null || folderId === undefined) return
  renamingFolderId.value = folderId
  renamingFolderName.value = currentName
  nextTick(() => {
    const el = document.querySelector('.folder-rename-input')
    if (el) el.focus()
  })
}

function cancelRename() {
  renamingFolderId.value = null
  renamingFolderName.value = ''
}

async function confirmRename(folderId) {
  if (folderId === null || folderId === undefined) return
  if (renamingFolderId.value !== folderId) return
  const name = renamingFolderName.value.trim()
  if (!name) {
    cancelRename()
    return
  }
  try {
    await favoriteStore.updateFolder(folderId, { name })
    toast.success('收藏夹已重命名')
  } catch (e) {
    toast.error('重命名失败', e.response?.data?.detail || e.message)
  }
  cancelRename()
}

function confirmDeleteFolder(folderId, folderName) {
  if (folderId === null || folderId === undefined) return
  deletingFolderId.value = folderId
  deletingFolderName.value = folderName
  showDeleteConfirm.value = true
}

async function doDeleteFolder() {
  if (deletingFolderId.value === null) return
  try {
    await favoriteStore.removeFolder(deletingFolderId.value)
    await favoriteStore.fetchFavorites()
    toast.success(`收藏夹「${deletingFolderName.value}」已删除`)
  } catch (e) {
    toast.error('删除失败', e.response?.data?.detail || e.message)
  }
  showDeleteConfirm.value = false
  deletingFolderId.value = null
  deletingFolderName.value = ''
}

async function handleRemoveFavorite(fav) {
  try {
    await removeFavoriteApi(fav.id)
    await favoriteStore.fetchFavorites()
    toast.success('已取消收藏', fav.name)
  } catch {}
}

async function handleBatchRemove() {
  try {
    for (const id of selectedIds.value) {
      await removeFavoriteApi(id)
    }
    selectedIds.value = new Set()
    batchRemoveMode.value = false
    await favoriteStore.fetchFavorites()
    toast.success('批量删除完成')
  } catch {}
}

// ---------- 刷新延迟 ----------
const isRefreshingLatency = ref(false)

async function handleRefreshLatency() {
  isRefreshingLatency.value = true
  try {
    const { data } = await refreshFavoritesLatency()
    await favoriteStore.fetchFavorites()
    toast.success(`延迟已刷新`, `更新了 ${data.updated} 个频道`)
  } catch (e) {
    const msg = e.response?.data?.error?.message || e.response?.data?.detail || e?.message || '刷新延迟失败'
    toast.error('刷新延迟失败', msg)
  } finally {
    isRefreshingLatency.value = false
  }
}

// ---------- 收藏分页 ----------
function changeFavPage(page) {
  favoriteStore.setFavoritesPage(page)
  favoriteStore.fetchFavorites()
}

function changeFavPerPage(n) {
  favoriteStore.setFavoritesPerPage(n)
  favoriteStore.setFavoritesPage(1)
  favoriteStore.fetchFavorites()
}

function onFavSortChange(sort) {
  favoriteStore.setFavoritesSort(sort)
  favoriteStore.setFavoritesPage(1)
  favoriteStore.fetchFavorites()
}

// ---------- 批量移动 ----------
function handleBatchMoveSelected() {
  if (selectedIds.value.size === 0) return
  // 复用移动弹窗：取第一个选中项作为触发源
  const firstId = [...selectedIds.value][0]
  const fav = flatAllChannels.value.find(f => f.id === firstId)
  if (fav) {
    // 临时修改 doMoveToFolder：批量移动所有选中项
    movingFav.value = fav
    showMoveDialog.value = true
  }
}

async function doMoveToFolder(folderId) {
  if (batchRemoveMode && selectedIds.value.size > 1) {
    // 批量移动所有选中项
    const count = selectedIds.value.size
    try {
      for (const id of selectedIds.value) {
        await updateFavorite(id, { folder_id: folderId })
      }
      selectedIds.value = new Set()
      batchRemoveMode.value = false
      await favoriteStore.fetchFavorites()
      toast.success(`已移动 ${count} 项`)
    } catch {
      toast.error('批量移动失败')
    }
    showMoveDialog.value = false
    return
  }
  // 单频道移动（原有逻辑）
  if (!movingFav.value) return
  try {
    await updateFavorite(movingFav.value.id, { folder_id: folderId })
    showMoveDialog.value = false
    await favoriteStore.fetchFavorites()
    toast.success('已移动')
  } catch {}
}

// ---------- 批量导出 ----------
function handleBatchExportSelected() {
  if (selectedIds.value.size === 0) return
  const ids = [...selectedIds.value]
  const selected = flatAllChannels.value.filter(f => ids.includes(f.id))
  if (!selected.length) return
  const content = generateExportContent(selected)
  downloadExport(content, exportFormat.value || 'm3u', 'selected')
  toast.success(`已导出 ${selected.length} 个频道`)
}

async function handleAddFolder() {
  if (!newFolderName.value.trim()) return
  try {
    await favoriteStore.addFolder(newFolderName.value.trim())
    newFolderName.value = ''
    showAddFolder.value = false
    toast.success('收藏夹已创建')
  } catch (e) {
    toast.error('创建收藏夹失败', e.response?.data?.detail || e.message)
  }
}

function handleMoveToFolder(fav) {
  movingFav.value = fav
  showMoveDialog.value = true
}

async function handleCreateFolderInMove() {
  const name = moveNewFolderName.value.trim()
  if (!name) return
  try {
    const data = await favoriteStore.addFolder(name)
    if (data && movingFav.value) {
      await updateFavorite(movingFav.value.id, { folder_id: data.id })
      await favoriteStore.fetchFavorites()
      toast.success('已移动')
    }
    showMoveNewFolder.value = false
    moveNewFolderName.value = ''
    showMoveDialog.value = false
  } catch (e) {
    toast.error('创建收藏夹失败', e.response?.data?.detail || e.message)
  }
}

async function handleExportFolder() {
  try {
    const favs = favoriteStore.favorites || []
    let channels
    if (exportFolderId.value === 'all') {
      channels = favs
    } else if (exportFolderId.value === 'null') {
      channels = favs.filter(ch => ch.folder_id === null || ch.folder_id === undefined)
    } else {
      const fid = parseInt(exportFolderId.value)
      channels = favs.filter(ch => ch.folder_id === fid)
    }
    if (!channels.length) {
      toast.error('该收藏夹没有可导出的频道')
      return
    }
    const content = generateExportContent(channels)
    downloadExport(content, exportFormat.value, getExportFolderName())
    showExportDialog.value = false
    toast.success('导出成功')
  } catch (e) {
    toast.error('导出失败')
  }
}

async function handleExportSelected() {
  try {
    const ids = [...exportSelectedChannels.value]
    const selected = flatAllChannels.value.filter(f => ids.includes(f.id))
    if (!selected.length) return
    const content = generateExportContent(selected)
    downloadExport(content, exportFormat.value, 'selected')
    showExportDialog.value = false
    toast.success(`已导出 ${selected.length} 个频道`)
  } catch (e) {
    toast.error('导出失败')
  }
}

function generateExportContent(channels) {
  const fmt = exportFormat.value
  switch (fmt) {
    case 'm3u':
    case 'm3u8': {
      const lines = [fmt === 'm3u8' ? '' : '#EXTM3U']
      for (const ch of channels) {
        lines.push(`#EXTINF:-1 group-title="${ch.channel_group || '未分类'}",${ch.name}`)
        lines.push(ch.url)
      }
      return lines.join('\n') + '\n'
    }
    case 'txt': {
      return channels.map(ch => ch.url).join('\n') + '\n'
    }
    case 'csv': {
      const lines = ['name,url,group']
      for (const ch of channels) {
        const name = (ch.name || '').replace(/"/g, '""')
        const url = (ch.url || '').replace(/"/g, '""')
        const group = (ch.channel_group || '').replace(/"/g, '""')
        lines.push(`"${name}","${url}","${group}"`)
      }
      return lines.join('\n') + '\n'
    }
    default:
      return ''
  }
}

function downloadExport(content, format, folderName) {
  const mimeMap = {
    m3u: 'audio/x-mpegurl',
    m3u8: 'audio/x-mpegurl',
    txt: 'text/plain',
    csv: 'text/csv',
  }
  const extMap = {
    m3u: 'm3u',
    m3u8: 'm3u8',
    txt: 'txt',
    csv: 'csv',
  }
  const blob = new Blob([content], { type: mimeMap[format] || 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `favorites${folderName ? '_' + folderName : ''}.${extMap[format] || ''}`
  a.click()
  URL.revokeObjectURL(url)
}

function getExportFolderName() {
  if (exportFolderId.value === 'all') return ''
  if (exportFolderId.value === 'null') return '未分类'
  const folder = allFolders.value.find(f => String(f.id) === exportFolderId.value)
  return folder ? folder.name : ''
}

function playInline(fav) {
  if (!fav.url) return
  currentChannel.value = fav
  const encoded = btoa(encodeURIComponent(fav.url))
  const radio = fav.is_radio ? '&radio=1' : ''
  iframeSrc.value = `/player?url=${encoded}&name=${encodeURIComponent(fav.name)}${radio}`
}

function openPlayerNewWindow(fav) {
  if (!fav.url) return
  const encoded = btoa(encodeURIComponent(fav.url))
  const radio = fav.is_radio ? '&radio=1' : ''
  window.open(`/player?url=${encoded}&name=${encodeURIComponent(fav.name)}${radio}`, '_blank')
}

function stopPlayer() {
  currentChannel.value = null
  iframeSrc.value = ''
}
</script>
