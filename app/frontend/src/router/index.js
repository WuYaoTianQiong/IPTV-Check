import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/source' },
  { path: '/source', name: 'source', component: () => import('../views/SourceView.vue') },
  { path: '/checking', name: 'checking', component: () => import('../views/CheckingView.vue') },
  { path: '/result', name: 'result', component: () => import('../views/ResultView.vue') },
  { path: '/favorites', name: 'favorites', component: () => import('../views/FavoriteView.vue') },
  { path: '/report', name: 'report', component: () => import('../views/ReportView.vue') },
  { path: '/trend', name: 'trend', component: () => import('../views/TrendView.vue') },
  { path: '/toolbox', name: 'toolbox', component: () => import('../views/ToolboxView.vue') },
  // 404 兜底：未知路径重定向回首页
  { path: '/:pathMatch(.*)*', redirect: '/source' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 预热所有懒加载页签 chunk：页面启动时后台下载，避免检测初期首次点击
// 结果/报告/趋势/工具箱/收藏夹等页签时卡在 chunk 下载上（表现为"点击不动"）
export function prefetchAllRoutes() {
  return Promise.allSettled(
    routes
      .filter((r) => typeof r.component === 'function')
      .map((r) => r.component())
  )
}

export default router
