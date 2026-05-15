/**
 * useLoading — 页面级统一 loading 状态管理
 *
 * 用法:
 *   const { isLoading, withLoading } = usePageLoading('sourcePage')
 *   onMounted(() => withLoading(() => fetchData()))
 *   // 模板: <SkeletonCard v-if="isLoading" /> <div v-else>内容</div>
 */
import { reactive, ref, readonly } from 'vue'

const loaders = reactive({})

/**
 * 获取/创建页面的 loading 状态
 * @param {string} pageName 全局唯一的页面标识
 */
export function usePageLoading(pageName) {
  if (!loaders[pageName]) {
    loaders[pageName] = ref(false)
  }
  const isLoading = readonly(loaders[pageName])

  async function withLoading(asyncFn) {
    loaders[pageName].value = true
    try {
      return await asyncFn()
    } finally {
      loaders[pageName].value = false
    }
  }

  return { isLoading, withLoading }
}
