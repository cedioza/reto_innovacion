import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../features/chat/ChatView.vue'
import PanelView from '../features/panel/PanelView.vue'
import InsurerView from '../features/aseguradora/InsurerView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/panel', name: 'panel', component: PanelView },
    { path: '/aseguradora/:token', name: 'aseguradora', component: InsurerView },
  ],
})

export default router
