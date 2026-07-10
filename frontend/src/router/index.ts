import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard.vue'),
    },
    {
      path: '/strategy',
      name: 'Strategy',
      component: () => import('@/views/Strategy.vue'),
    },
    {
      path: '/config',
      name: 'Config',
      component: () => import('@/views/Config.vue'),
    },
  ],
})

export default router
