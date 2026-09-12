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
          meta: { title: 'CAN 通讯诊断' },
        },
        {
          path: 'axle',
          name: 'axle-control',
          component: () => import('@/views/AxleControlView.vue'),
          meta: { title: '电驱桥控制台' },
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
  document.title = title ? `${title} · 电驱桥上位机系统` : '电驱桥上位机系统'
})

export default router
