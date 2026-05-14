<template>
  <Teleport to="body">
    <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      <TransitionGroup
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="translate-x-full opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-full opacity-0"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="cn(
            'rounded-lg border px-4 py-3 shadow-lg cursor-pointer',
            'flex items-start gap-3',
            variantStyles[toast.variant] || variantStyles.default
          )"
          @click="removeToast(toast.id)"
        >
          <component :is="icons[toast.variant] || icons.default" class="h-5 w-5 shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div v-if="toast.title" class="text-sm font-semibold leading-tight">{{ toast.title }}</div>
            <div v-if="toast.description" class="text-sm mt-0.5 opacity-90 leading-tight">{{ toast.description }}</div>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { CircleCheck, CircleX, AlertTriangle, Info, Bell } from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { cn } from '../lib/utils'

const { toasts, removeToast } = useToast()

const variantStyles = {
  default: 'bg-card border-border text-card-foreground',
  success: 'bg-success/10 border-success/20 text-success',
  destructive: 'bg-destructive/10 border-destructive/20 text-destructive',
  warning: 'bg-warning/10 border-warning/20 text-warning',
  info: 'bg-info/10 border-info/20 text-info',
}

const icons = {
  default: Bell,
  success: CircleCheck,
  destructive: CircleX,
  warning: AlertTriangle,
  info: Info,
}
</script>
