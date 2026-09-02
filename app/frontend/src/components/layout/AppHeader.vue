<template>
  <header class="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="flex h-14 items-center px-4 gap-4">
      <RouterLink to="/source" class="flex items-center gap-2 shrink-0 hover:opacity-80 transition-opacity">
        <Tv class="h-6 w-6 text-primary" />
        <span class="font-semibold text-lg hidden sm:inline">电视直播源检测工具</span>
        <span class="font-semibold text-lg sm:hidden">IPTV检测</span>
      </RouterLink>

      <nav class="hidden md:flex items-center gap-1 ml-4">
        <RouterLink
          v-for="item in navItems"
          :key="item.id"
          :to="item.to"
          custom
          v-slot="{ isActive, navigate }"
        >
          <button
            @click="navigate"
            :class="cn(
              'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )"
          >
            <component :is="item.icon" class="h-4 w-4" />
            {{ item.label }}
            <Badge
              v-if="item.badge"
              variant="secondary"
              class="ml-0.5 text-[10px] px-1.5 py-0 h-4"
            >
              {{ item.badge }}
            </Badge>
            <span
              v-if="item.id === 'checking' && store.isChecking"
              class="w-2 h-2 rounded-full bg-success animate-ping"
            />
          </button>
        </RouterLink>
      </nav>

      <div class="flex-1" />

      <div class="flex items-center gap-2">
        <div
          :class="cn(
            'w-2 h-2 rounded-full',
            wsConnected ? 'bg-success' : wsReconnecting ? 'bg-warning animate-pulse' : 'bg-destructive'
          )"
          :title="wsConnected ? '已连接' : wsReconnecting ? '重连中...' : '已断开'"
        />

        <Badge variant="secondary" class="gap-1">
          <Globe class="h-3 w-3" />
          <span class="hidden sm:inline">{{ store.localIsp }}</span>
          <span class="sm:hidden">{{ store.localIsp.slice(0, 2) }}</span>
          <Loader2 v-if="store.localIsp === '检测中...' || store.localIsp === '未知'" class="h-3 w-3 animate-spin ml-1" />
        </Badge>

        <button
          class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-8 w-8"
          @click="store.doRefreshIsp()"
          :disabled="store.localIsp === '检测中...'"
          :title="store.localIsp === '检测中...' ? '检测中...' : '刷新运营商'"
        >
          <RefreshCw :class="cn('h-4 w-4', store.localIsp === '检测中...' && 'animate-spin')" />
        </button>

        <button
          class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-8 w-8"
          @click="toggleTheme"
          :title="mode === 'dark' ? '切换到亮色模式' : '切换到暗色模式'"
        >
          <Sun v-if="mode === 'light'" class="h-4 w-4" />
          <Moon v-else class="h-4 w-4" />
        </button>
      </div>
    </div>
  </header>

  <nav class="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background">
    <div class="flex justify-around py-2">
      <RouterLink
        v-for="item in mobileNavItems"
        :key="item.id"
        :to="item.to"
        custom
        v-slot="{ isActive, navigate }"
      >
        <button
          @click="navigate"
          :class="cn(
            'flex flex-1 flex-col items-center gap-0.5 px-1 py-1 text-xs transition-colors',
            isActive
              ? 'text-primary'
              : 'text-muted-foreground'
          )"
        >
          <component :is="item.icon" class="h-5 w-5" />
          <span class="text-[10px]">{{ item.label }}</span>
        </button>
      </RouterLink>
    </div>
  </nav>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { Tv, Globe, RefreshCw, Sun, Moon, Radio, PlayCircle, BarChart3, FileBarChart2, TrendingUp, Wrench, Star, Loader2 } from 'lucide-vue-next'
import { useAppStore } from '../../stores/app'
import { useDarkMode } from '../../composables/useDarkMode'
import { cn } from '../../lib/utils'
import { sseStatus } from '../../api'
import { Badge } from '../ui/badge'

const store = useAppStore()
const { mode, toggleTheme } = useDarkMode()

const wsConnected = ref(false)
const wsReconnecting = ref(false)
let wsPollTimer = null

onMounted(() => {
  wsPollTimer = setInterval(() => {
    wsConnected.value = sseStatus.connected
    wsReconnecting.value = sseStatus.reconnecting
  }, 1000)
})
onUnmounted(() => clearInterval(wsPollTimer))

const navItems = computed(() => [
  { id: 'source', to: '/source', label: '源配置', icon: Radio },
  { id: 'checking', to: '/checking', label: store.isChecking ? '检测中' : '开始检测', icon: PlayCircle, badge: store.isChecking ? '进行中' : null },
  { id: 'result', to: '/result', label: '结果', icon: BarChart3 },
  { id: 'report', to: '/report', label: '报告', icon: FileBarChart2 },
  { id: 'trend', to: '/trend', label: '趋势', icon: TrendingUp },
  { id: 'toolbox', to: '/toolbox', label: '工具箱', icon: Wrench },
  { id: 'favorites', to: '/favorites', label: '收藏夹', icon: Star },
])

// 移动端底部导航与桌面顶栏保持一致（7 项），避免报告/趋势在移动端无入口
const mobileNavItems = computed(() => [
  { id: 'source', to: '/source', label: '源', icon: Radio },
  { id: 'checking', to: '/checking', label: store.isChecking ? '检测中' : '检测', icon: PlayCircle },
  { id: 'result', to: '/result', label: '结果', icon: BarChart3 },
  { id: 'report', to: '/report', label: '报告', icon: FileBarChart2 },
  { id: 'trend', to: '/trend', label: '趋势', icon: TrendingUp },
  { id: 'favorites', to: '/favorites', label: '收藏', icon: Star },
  { id: 'toolbox', to: '/toolbox', label: '工具', icon: Wrench },
])
</script>
