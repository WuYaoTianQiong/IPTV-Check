import { ref } from 'vue'

const toasts = ref([])
let idCounter = 0

export function useToast() {
  function addToast({ title, description, variant = 'default', duration = 5000, action = null }) {
    const id = ++idCounter
    toasts.value.push({ id, title, description, variant, duration, action })
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration)
    }
    return id
  }

  function removeToast(id) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
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
