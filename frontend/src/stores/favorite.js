import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getFavorites, addFavorite, removeFavorite, getFavoriteFolders, createFavoriteFolder, deleteFavoriteFolder } from '../api'

export const useFavoriteStore = defineStore('favorite', () => {
  const favorites = ref([])
  const folders = ref([])
  const isLoading = ref(false)
  const activeFolderId = ref(null)

  const favoriteUrlSet = computed(() => new Set(favorites.value.map(f => f.url)))

  async function fetchFavorites(folderId = null) {
    isLoading.value = true
    try {
      const params = {}
      if (folderId !== null) params.folder_id = folderId
      const { data } = await getFavorites(params)
      favorites.value = data.favorites || []
    } catch {
      favorites.value = []
    } finally {
      isLoading.value = false
    }
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

  async function toggleFavorite(channel) {
    const existing = favorites.value.find(f => f.url === channel.url)
    if (existing) {
      try {
        await removeFavorite(existing.id)
        favorites.value = favorites.value.filter(f => f.id !== existing.id)
      } catch {}
    } else {
      try {
        const { data } = await addFavorite({
          channel_id: channel.channel_id || 0,
          name: channel.name,
          url: channel.url,
          folder_id: activeFolderId.value,
          channel_group: channel.group || '',
        })
        favorites.value.push(data)
      } catch {}
    }
  }

  async function addFolder(name) {
    try {
      const { data } = await createFavoriteFolder({ name })
      folders.value.splice(-1, 0, data)
      return data
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
    favoriteUrlSet,
    fetchFavorites,
    fetchFolders,
    isFavorite,
    toggleFavorite,
    addFolder,
    removeFolder,
  }
})
