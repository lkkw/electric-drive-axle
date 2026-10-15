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
          redirect: '/can',
        },
        {
          path: 'can',
          name: 'can-comm',
          component: () => import('@/views/CanCommView.vue'),
          meta: { title: 'CAN 通讯控制' },
        },
        {
          path: 'power',
          name: 'bench-power',
          component: () => import('@/views/PowerView.vue'),
          meta: { title: '台架供电' },
        },
        {
          path: 'axle',
          name: 'axle-control',
          component: () => import('@/views/AxleControlView.vue'),
          meta: { title: '下线测试' },
        },
        {
          path: 'records',
          name: 'test-records',
          component: () => import('@/views/TestRecordsView.vue'),
          meta: { title: '试车记录' },
        },
        {
          path: 'safety',
          name: 'safety-config',
          component: () => import('@/views/SafetyConfigView.vue'),
          meta: { title: '安全配置' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/can',
    },
  ],
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · 株齿 2.5T 电驱桥下线测试上位机` : '株齿 2.5T 电驱桥下线测试上位机'
})

export default router
