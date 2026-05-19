import { ref } from 'vue'

const toasts = ref([])
const MAX_TOASTS = 5
const DEDUP_WINDOW = 3000
let idCounter = 0
const recentKeys = new Map()

export function useToast() {
  function addToast({ title, description, variant = 'default', duration = 5000, action = null }) {
    const dedupKey = `${title}:${variant}`
    const now = Date.now()
    const lastTime = recentKeys.get(dedupKey)
    if (lastTime && now - lastTime < DEDUP_WINDOW) {
      return -1
    }
    recentKeys.set(dedupKey, now)

    const id = ++idCounter
    toasts.value.push({ id, title, description, variant, duration, action })

    if (toasts.value.length > MAX_TOASTS) {
      const removed = toasts.value.splice(0, toasts.value.length - MAX_TOASTS)
      removed.forEach(t => {
        if (t._timer) clearTimeout(t._timer)
      })
    }

    let timer = null
    if (duration > 0) {
      timer = setTimeout(() => {
        removeToast(id)
      }, duration)
    }
    const item = toasts.value[toasts.value.length - 1]
    if (item && item.id === id) {
      item._timer = timer
    }
    return id
  }

  function removeToast(id) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) {
      const item = toasts.value[idx]
      if (item._timer) clearTimeout(item._timer)
      toasts.value.splice(idx, 1)
    }
  }

  function toast(options) {
    return addToast(options)
  }

  toast.success = (title, description, action = null) => addToast({ title, description, variant: 'success', action })
  toast.error = (title, description) => addToast({ title, description, variant: 'destructive' })
  toast.warning = (title, description) => addToast({ title, description, variant: 'warning' })
  toast.info = (title, description) => addToast({ title, description, variant: 'info' })

  return {
    toasts,
    addToast,
    removeToast,
    toast,
  }
}
