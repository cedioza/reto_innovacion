import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../features/chat/ChatView.vue'
import PanelView from '../features/panel/PanelView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/panel', name: 'panel', component: PanelView },
  ],
})

export default router
