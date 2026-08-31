import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getFavorites, addFavorite, removeFavorite, getFavoriteFolders, createFavoriteFolder, updateFavoriteFolder, deleteFavoriteFolder } from '../api'

export const useFavoriteStore = defineStore('favorite', () => {
  const favorites = ref([])
  const folders = ref([])
  const isLoading = ref(false)
  const activeFolderId = ref(null)

  const favoritesPage = ref(1)
  const favoritesTotal = ref(0)
  const favoritesPerPage = ref(50)
  try {
    const saved = localStorage.getItem('iptv_fav_per_page')
    if (saved) favoritesPerPage.value = parseInt(saved, 10)
  } catch {}

  const sortOrder = ref('default')
  try {
    const saved = localStorage.getItem('iptv_fav_sort_order')
    if (saved) sortOrder.value = saved
  } catch {}

  const totalPages = computed(() => Math.ceil(favoritesTotal.value / favoritesPerPage.value) || 1)

  const favoriteUrlSet = computed(() => new Set(favorites.value.map(f => f.url)))

  async function fetchFavorites(folderId = null, page = null, perPage = null) {
    isLoading.value = true
    try {
      const params = {}
      if (folderId !== null) params.folder_id = folderId
      params.page = page ?? favoritesPage.value
      params.per_page = perPage ?? favoritesPerPage.value
      params.sort = sortOrder.value
      const { data } = await getFavorites(params)
      favorites.value = data.favorites || []
      favoritesTotal.value = data.total || 0
      favoritesPage.value = data.page || 1
    } catch (e) {
      favorites.value = []
      throw e
    } finally {
      isLoading.value = false
    }
  }

  function setFavoritesPage(page) {
    favoritesPage.value = page
  }

  function setFavoritesPerPage(n) {
    favoritesPerPage.value = n
    try { localStorage.setItem('iptv_fav_per_page', n) } catch {}
  }

  function setFavoritesSort(s) {
    sortOrder.value = s
    try { localStorage.setItem('iptv_fav_sort_order', s) } catch {}
  }

  async function fetchFolders() {
    try {
      const { data } = await getFavoriteFolders()
      folders.value = data.folders || []
    } catch {
      folders.value = []
    }
  }

  function isFavorite(url) {
    return favoriteUrlSet.value.has(url)
  }

  async function setDefaultFolder(folderId) {
    activeFolderId.value = folderId
  }

  async function toggleFavorite(channel) {
    const existing = favorites.value.find(f => f.url === channel.url)
    if (existing) {
      await removeFavorite(existing.id)
      favorites.value = favorites.value.filter(f => f.id !== existing.id)
    } else {
      const { data } = await addFavorite({
        channel_id: channel.channel_id || 0,
        name: channel.name,
        url: channel.url,
        folder_id: activeFolderId.value,
        channel_group: channel.group || '',
      })
      favorites.value.push(data)
    }
  }

  async function addFavoriteTo(channel, folderId) {
    const existing = favorites.value.find(f => f.url === channel.url)
    if (existing) {
      await removeFavorite(existing.id)
      favorites.value = favorites.value.filter(f => f.id !== existing.id)
      return { action: 'removed' }
    }
    const { data } = await addFavorite({
      channel_id: channel.channel_id || 0,
      name: channel.name,
      url: channel.url,
      folder_id: folderId,
      channel_group: channel.group || '',
    })
    favorites.value.push(data)
    return { action: 'added', data }
  }

  async function addFolder(name) {
    const { data } = await createFavoriteFolder({ name })
    folders.value.push(data)
    return data
  }

  async function updateFolder(id, data) {
    try {
      await updateFavoriteFolder(id, data)
      const idx = folders.value.findIndex(f => f.id === id)
      if (idx !== -1) {
        folders.value[idx] = { ...folders.value[idx], ...data }
      }
    } catch {}
  }

  async function removeFolder(id) {
    try {
      await deleteFavoriteFolder(id)
      folders.value = folders.value.filter(f => f.id !== id)
      if (activeFolderId.value === id) {
        activeFolderId.value = null
      }
    } catch {}
  }

  return {
    favorites,
    folders,
    isLoading,
    activeFolderId,
    favoritesPage,
    favoritesTotal,
    favoritesPerPage,
    sortOrder,
    totalPages,
    favoriteUrlSet,
    fetchFavorites,
    fetchFolders,
    isFavorite,
    toggleFavorite,
    addFavoriteTo,
    setDefaultFolder,
    setFavoritesPage,
    setFavoritesPerPage,
    setFavoritesSort,
    addFolder,
    updateFolder,
    removeFolder,
  }
})
