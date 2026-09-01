import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getOnlineSources } from '../api'

export const useSourceStore = defineStore('source', () => {
  const onlineSources = ref([])
  const isLoading = ref(false)
  const error = ref(null)
  const selectedOnlineIds = ref([])
  let pendingPromise = null

  // 用 Set 做 O(1) 存在性查找，避免 selectedOnlineIds（可达数万项）上多次 includes 造成主线程卡顿
  const selectedIdSet = computed(() => new Set(selectedOnlineIds.value))

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

  function toggleOnline(id) {
    const idx = selectedOnlineIds.value.indexOf(id)
    if (idx >= 0) selectedOnlineIds.value.splice(idx, 1)
    else selectedOnlineIds.value.push(id)
  }

  function selectAllMatched() {
    const matched = onlineSources.value
      .filter(s => !s.disabled && (s.isp_compatible || s.category === '广播电台' || s.category === '国际电视'))
      .map(s => s.id)
    selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...matched])]
  }

  function selectAllCompatible() {
    const ids = onlineSources.value.filter(s => !s.disabled && s.isp_compatible).map(s => s.id)
    selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...ids])]
  }

  function clearOnline() {
    selectedOnlineIds.value = []
  }

  function selectCategory(category) {
    const ids = onlineSources.value
      .filter(s => !s.disabled && s.category === category)
      .map(s => s.id)
    selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...ids])]
  }

  function selectCompatibleInCategory(category) {
    const ids = onlineSources.value
      .filter(s => !s.disabled && s.category === category && s.isp_compatible)
      .map(s => s.id)
    selectedOnlineIds.value = [...new Set([...selectedOnlineIds.value, ...ids])]
  }

  function clearCategory(category) {
    const ids = onlineSources.value.filter(s => s.category === category).map(s => s.id)
    selectedOnlineIds.value = selectedOnlineIds.value.filter(id => !ids.includes(id))
  }

  return {
    onlineSources,
    isLoading,
    error,
    selectedOnlineIds,
    selectedIdSet,
    categorizedSources,
    fetchOnlineSources,
    reset,
    toggleOnline,
    selectAllMatched,
    selectAllCompatible,
    clearOnline,
    selectCategory,
    selectCompatibleInCategory,
    clearCategory,
  }
})
