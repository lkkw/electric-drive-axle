import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/components/layout/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '仪表盘' },
        },
        {
          path: 'realtime',
          name: 'realtime',
          component: () => import('@/views/SseDemo.vue'),
          meta: { title: 'SSE 实时消息' },
        },
        {
          path: 'pages/one',
          name: 'page-one',
          component: () => import('@/views/PageOneView.vue'),
          meta: { title: '示例页面一' },
        },
        {
          path: 'pages/two',
          name: 'page-two',
          component: () => import('@/views/PageTwoView.vue'),
          meta: { title: '示例页面二' },
        },
        // 以后新增页面：在这里追加一条路由，并在 AppSidebar.vue 中加菜单项。
      ],
    },
  ],
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · FastAPI + Vue 3 Starter` : 'FastAPI + Vue 3 Starter'
})

export default router
