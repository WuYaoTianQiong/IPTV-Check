<template>
  <header class="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="flex h-14 items-center px-4 gap-4">
      <div class="flex items-center gap-2 shrink-0">
        <Tv class="h-6 w-6 text-primary" />
        <span class="font-semibold text-lg hidden sm:inline">电视直播源检测工具</span>
        <span class="font-semibold text-lg sm:hidden">IPTV检测</span>
      </div>

      <nav class="hidden md:flex items-center gap-1 ml-4">
        <button
          v-for="item in navItems"
          :key="item.id"
          @click="store.activeView = item.id"
          :class="cn(
            'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
            store.activeView === item.id
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
        </button>
      </nav>

      <div class="flex-1" />

      <div class="flex items-center gap-2">
        <Badge variant="secondary" class="gap-1">
          <Globe class="h-3 w-3" />
          <span class="hidden sm:inline">{{ store.localIsp }}</span>
          <span class="sm:hidden">{{ store.localIsp.slice(0, 2) }}</span>
        </Badge>

        <button
          class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-8 w-8"
          @click="store.doRefreshIsp()"
        >
          <RefreshCw class="h-4 w-4" />
        </button>

        <button
          class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-8 w-8"
          @click="toggleTheme"
        >
          <Sun v-if="mode === 'light'" class="h-4 w-4" />
          <Moon v-else-if="mode === 'dark'" class="h-4 w-4" />
          <Monitor v-else class="h-4 w-4" />
        </button>
      </div>
    </div>
  </header>

  <nav class="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background">
    <div class="flex justify-around py-2">
      <button
        v-for="item in navItems"
        :key="item.id"
        @click="store.activeView = item.id"
        :class="cn(
          'flex flex-col items-center gap-0.5 px-3 py-1 text-xs transition-colors',
          store.activeView === item.id
            ? 'text-primary'
            : 'text-muted-foreground'
        )"
      >
        <component :is="item.icon" class="h-5 w-5" />
        <span class="text-[10px]">{{ item.mobileLabel || item.label }}</span>
      </button>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { Tv, Globe, RefreshCw, Sun, Moon, Monitor, Radio, PlayCircle, BarChart3, Wrench, FileText } from 'lucide-vue-next'
import { useAppStore } from '../../stores/app'
import { useDarkMode } from '../../composables/useDarkMode'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'

const store = useAppStore()
const { mode, toggleTheme } = useDarkMode()

const navItems = computed(() => [
  { id: 'source', label: '源配置', mobileLabel: '源', icon: Radio },
  { id: 'checking', label: '检测中', mobileLabel: '检测', icon: PlayCircle, badge: store.isChecking ? '进行中' : null },
  { id: 'result', label: '结果', mobileLabel: '结果', icon: BarChart3 },
  { id: 'report', label: '报告', mobileLabel: '报告', icon: FileText },
  { id: 'toolbox', label: '工具箱', mobileLabel: '工具', icon: Wrench },
])
</script>
