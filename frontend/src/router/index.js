import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/source' },
  { path: '/source', name: 'source', component: () => import('../views/SourceView.vue') },
  { path: '/checking', name: 'checking', component: () => import('../views/CheckingView.vue') },
  { path: '/result', name: 'result', component: () => import('../views/ResultView.vue') },
  { path: '/report', name: 'report', component: () => import('../views/ReportView.vue') },
  { path: '/trend', name: 'trend', component: () => import('../views/TrendView.vue') },
  { path: '/toolbox', name: 'toolbox', component: () => import('../views/ToolboxView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
