import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getResults, getResultsStats, getCheckHistory } from '../api'

export const useResultStore = defineStore('result', () => {
  const checkResults = ref([])
  const resultsPage = ref(1)
  const resultsTotal = ref(0)
  const resultsPerPage = ref(50)
  const currentTab = ref('all')
  const searchQuery = ref('')
  const isLoading = ref(false)
  const error = ref(null)
  const history = ref([])
  const selectedSessionId = ref('')
  const isHistoryLoading = ref(false)

  async function fetchResults(params = {}) {
    isLoading.value = true
    error.value = null
    try {
      const baseParams = {
        tab: currentTab.value,
        page: resultsPage.value,
        per_page: resultsPerPage.value,
        search: searchQuery.value,
        ...params,
      }
      if (selectedSessionId.value) {
        baseParams.session_id = selectedSessionId.value
      }
      const { data } = await getResults(baseParams)
      checkResults.value = data.items || []
      resultsTotal.value = data.total || 0
      return data
    } catch (e) {
      error.value = e.message || '获取结果失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function fetchHistory() {
    isHistoryLoading.value = true
    try {
      const { data } = await getCheckHistory(50)
      history.value = Array.isArray(data) ? data : []
      if (history.value.length > 0 && !selectedSessionId.value) {
        selectedSessionId.value = history.value[0].session_id
      }
    } catch (e) {
      console.warn('加载历史记录失败:', e)
      history.value = []
    } finally {
      isHistoryLoading.value = false
    }
  }

  function selectSession(sessionId) {
    selectedSessionId.value = sessionId
    resultsPage.value = 1
  }

  function setTab(tab) {
    currentTab.value = tab
    resultsPage.value = 1
  }

  function setSearch(query) {
    searchQuery.value = query
    resultsPage.value = 1
  }

  function setPage(page) {
    resultsPage.value = page
  }

  function reset() {
    checkResults.value = []
    resultsPage.value = 1
    resultsTotal.value = 0
    currentTab.value = 'all'
    searchQuery.value = ''
    isLoading.value = false
    error.value = null
    history.value = []
    selectedSessionId.value = ''
    isHistoryLoading.value = false
  }

  return {
    checkResults,
    resultsPage,
    resultsTotal,
    resultsPerPage,
    currentTab,
    searchQuery,
    isLoading,
    error,
    history,
    selectedSessionId,
    isHistoryLoading,
    fetchResults,
    fetchHistory,
    selectSession,
    setTab,
    setSearch,
    setPage,
    reset,
  }
})
