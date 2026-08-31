import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSourceStore } from '../source'

describe('useSourceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始状态应为空', () => {
    const store = useSourceStore()
    expect(store.onlineSources).toEqual([])
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('categorizedSources 应按分类分组', () => {
    const store = useSourceStore()
    store.onlineSources = [
      { id: '1', name: '源A', category: '央视', disabled: false },
      { id: '2', name: '源B', category: '央视', disabled: false },
      { id: '3', name: '源C', category: '卫视', disabled: false },
      { id: '4', name: '源D', category: '央视', disabled: true },
    ]

    const categorized = store.categorizedSources
    expect(categorized).toHaveLength(2)
    expect(categorized[0].category).toBe('央视')
    expect(categorized[0].sources).toHaveLength(2)
    expect(categorized[1].category).toBe('卫视')
    expect(categorized[1].sources).toHaveLength(1)
  })

  it('reset 应清空所有状态', () => {
    const store = useSourceStore()
    store.onlineSources = [{ id: '1', name: '源A' }]
    store.isLoading = true
    store.error = '错误'

    store.reset()

    expect(store.onlineSources).toEqual([])
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })
})
