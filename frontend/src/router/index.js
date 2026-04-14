import { createRouter, createWebHistory } from 'vue-router'
import SupplyChainProjectView from '../views/SupplyChainProjectView.vue'
import SCProcessView from '../views/SCProcessView.vue'
import VisualizationView from '../views/cape/VisualizationView.vue'

const routes = [
  {
    path: '/',
    redirect: '/supply-chain'
  },
  {
    path: '/supply-chain',
    name: 'SupplyChainProject',
    component: SupplyChainProjectView
  },
  {
    path: '/supply-chain/process',
    name: 'SupplyChainProcess',
    component: SCProcessView
  },
  {
    path: '/supply-chain/visualization',
    name: 'SupplyChainVisualization',
    component: VisualizationView
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/supply-chain'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
