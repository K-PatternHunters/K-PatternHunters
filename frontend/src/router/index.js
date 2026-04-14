import { createRouter, createWebHistory } from 'vue-router'
import MainView from '../views/Main.vue'
import DashboardView from '../views/Dashboard.vue'

const routes = [
  {
    path: '/',
    name: 'main',
    component: MainView,
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: DashboardView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
