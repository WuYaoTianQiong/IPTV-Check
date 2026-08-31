import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getOnlineSources } from '../api'

export const useSourceStore = defineStore('source', () => {
  const onlineSources = ref([])
  const isLoading = ref(false)
  const error = ref(null)
  let pendingPromise = null

  const categorizedSources = computed(() => {
    const map = {}
    for (const src of onlineSources.value) {
      if (src.disabled) continue
      const cat = src.category || '未分类'
      if (!map[cat]) map[cat] = []
      map[cat].push(src)
    }
    return Object.entries(map).map(([category, sources]) => ({ category, sources }))
  })

  async function fetchOnlineSources() {
    if (isLoading.value) {
      return pendingPromise
    }
    if (onlineSources.value.length > 0) {
      return { sources: onlineSources.value }
    }

    isLoading.value = true
    error.value = null

    pendingPromise = getOnlineSources()
      .then(({ data }) => {
        onlineSources.value = data.sources || []
        return data
      })
      .catch((e) => {
        error.value = e.message || '加载在线源失败'
        throw e
      })
      .finally(() => {
        isLoading.value = false
        pendingPromise = null
      })

    return pendingPromise
  }

  function reset() {
    onlineSources.value = []
    isLoading.value = false
    error.value = null
    pendingPromise = null
  }

  return {
    onlineSources,
    isLoading,
    error,
    categorizedSources,
    fetchOnlineSources,
    reset,
  }
})
