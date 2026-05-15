import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getResults, getResultsStats } from '../api'

export const useResultStore = defineStore('result', () => {
  const checkResults = ref([])
  const resultsPage = ref(1)
  const resultsTotal = ref(0)
  const resultsPerPage = ref(50)
  const currentTab = ref('all')
  const searchQuery = ref('')
  const isLoading = ref(false)
  const error = ref(null)

  async function fetchResults(params = {}) {
    isLoading.value = true
    error.value = null
    try {
      const { data } = await getResults({
        tab: currentTab.value,
        page: resultsPage.value,
        per_page: resultsPerPage.value,
        search: searchQuery.value,
        ...params,
      })
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
    fetchResults,
    setTab,
    setSearch,
    setPage,
    reset,
  }
})
