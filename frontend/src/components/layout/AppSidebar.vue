<template>
  <aside class="hidden lg:flex w-60 flex-col border-r border-border bg-card">
    <nav class="flex-1 space-y-1 p-3">
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
            'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
            isActive
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
          )"
        >
          <component :is="item.icon" class="h-5 w-5" />
          {{ item.label }}
          <Badge
            v-if="item.badge"
            variant="secondary"
            class="ml-auto"
          >
            {{ item.badge }}
          </Badge>
        </button>
      </RouterLink>
    </nav>

    <div class="border-t border-border p-4">
      <div class="flex items-center gap-2 text-xs text-muted-foreground">
        <Activity class="h-4 w-4" />
        <span v-if="store.isChecking">检测中...</span>
        <span v-else>就绪</span>
      </div>
    </div>
  </aside>

  <nav class="lg:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background">
    <div class="flex justify-around py-2">
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
            'flex flex-col items-center gap-0.5 px-3 py-1 text-xs transition-colors',
            isActive
              ? 'text-primary'
              : 'text-muted-foreground'
          )"
        >
          <component :is="item.icon" class="h-5 w-5" />
          <span class="text-[10px]">{{ item.mobileLabel || item.label }}</span>
        </button>
      </RouterLink>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { Radio, PlayCircle, BarChart3, Wrench, Activity, Star } from 'lucide-vue-next'
import { useAppStore } from '../../stores/app'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'

const store = useAppStore()

const navItems = computed(() => [
  { id: 'source', to: '/source', label: '源配置', mobileLabel: '源', icon: Radio },
  { id: 'checking', to: '/checking', label: '检测中', mobileLabel: '检测', icon: PlayCircle, badge: store.isChecking ? '进行中' : null },
  { id: 'result', to: '/result', label: '结果', mobileLabel: '结果', icon: BarChart3 },
  { id: 'favorites', to: '/favorites', label: '收藏', mobileLabel: '收藏', icon: Star },
  { id: 'toolbox', to: '/toolbox', label: '工具箱', mobileLabel: '工具', icon: Wrench },
])
</script>
