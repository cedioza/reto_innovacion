import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../features/chat/ChatView.vue'
import PanelView from '../features/panel/PanelView.vue'
import InsurerView from '../features/aseguradora/InsurerView.vue'

// Las tres vistas del panel son rutas propias: cada una tiene URL compartible
// y sobrevive a un refresh (el fallback de SPA de `frontend/nginx.conf` sirve
// index.html). Esta lista es la única fuente de verdad de las vistas: el
// header arma su navegación contextual filtrando por `meta.navGrupo`, y
// `PanelView` decide qué render mostrar con `meta.vista`.
const vistasPanel = [
  {
    path: '/panel/oferta',
    name: 'panel-oferta',
    component: PanelView,
    meta: {
      navGrupo: 'panel',
      navOrden: 1,
      navLabel: 'Oferta proactiva',
      vista: 'oferta',
      titulo: 'Panel — Oferta proactiva',
      descripcion: 'El seguro correcto, en el momento correcto, por el canal correcto.',
    },
  },
  {
    path: '/panel/funnel',
    name: 'panel-funnel',
    component: PanelView,
    meta: {
      navGrupo: 'panel',
      navOrden: 2,
      navLabel: 'Funnel de ventas',
      vista: 'funnel',
      titulo: 'Funnel de ventas',
      descripcion: 'De la conversación a la compra: conversión por producto.',
    },
  },
  {
    path: '/panel/clientes',
    name: 'panel-clientes',
    component: PanelView,
    meta: {
      navGrupo: 'panel',
      navOrden: 3,
      navLabel: 'Clientes',
      vista: 'clientes',
      titulo: 'Clientes',
      descripcion: 'Quién pasó por el funnel: perfil, seguros ofrecidos y comprados.',
    },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    // `/panel` sigue siendo un enlace válido (el header y los enlaces viejos
    // lo usan): entra por la vista de oferta proactiva.
    { path: '/panel', redirect: '/panel/oferta' },
    ...vistasPanel,
    { path: '/aseguradora/:token', name: 'aseguradora', component: InsurerView },
  ],
})

export default router
