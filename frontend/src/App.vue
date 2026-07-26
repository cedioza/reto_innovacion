<script setup>
// Shell de la app: barra de marca + navegación principal (Chat / Panel) y,
// cuando estás dentro del panel, una segunda fila contextual con sus vistas.
// Las vistas del panel se leen del router (`meta.navGrupo === 'panel'`), así
// que agregar una vista nueva no obliga a tocar este archivo.
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const vistasPanel = computed(() =>
  router
    .getRoutes()
    .filter((r) => r.meta?.navGrupo === 'panel')
    .sort((a, b) => (a.meta.navOrden ?? 0) - (b.meta.navOrden ?? 0)),
)

// `/panel` es un redirect, así que su record no queda en `matched`: el estado
// activo del enlace principal se decide por prefijo, no por router-link-active.
const enPanel = computed(() => route.path.startsWith('/panel'))
const enChat = computed(() => route.path === '/')
</script>

<template>
  <header class="app-header">
    <div class="header-bar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3l7 3v5.5c0 4.3-2.9 7.9-7 9.5-4.1-1.6-7-5.2-7-9.5V6l7-3z" />
            <path d="M9.2 12.1l2 2 3.6-3.9" />
          </svg>
        </span>
        <span class="brand-text">
          <span class="brand-name">Reto Innovación</span>
          <span class="brand-sub">Asistente de seguros</span>
        </span>
      </RouterLink>

      <nav class="primary-nav" aria-label="Navegación principal">
        <RouterLink to="/" class="nav-link" :class="{ 'is-active': enChat }">Chat</RouterLink>
        <RouterLink to="/panel" class="nav-link" :class="{ 'is-active': enPanel }">Panel</RouterLink>
      </nav>
    </div>

    <nav v-if="enPanel" class="context-nav" aria-label="Vistas del panel">
      <RouterLink
        v-for="vista in vistasPanel"
        :key="vista.path"
        :to="vista.path"
        class="context-link"
        :class="{ 'is-active': route.path === vista.path }"
        :aria-current="route.path === vista.path ? 'page' : undefined"
      >
        {{ vista.meta.navLabel }}
      </RouterLink>
    </nav>
  </header>

  <main>
    <RouterView />
  </main>
</template>

<style>
body {
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  margin: 0;
  color: var(--chat-text);
  background: var(--chat-bg);
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 20;
}

.header-bar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.7rem 1.5rem;
  background: linear-gradient(105deg, #00402d 0%, #006943 52%, #0a8b58 100%);
  color: #fff;
  overflow: hidden;
}

/* Brillo diagonal: le da profundidad a la barra sin cargar una textura. */
.header-bar::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 180% at 88% -40%, rgba(255, 255, 255, 0.22), transparent 60%);
  pointer-events: none;
}

.brand {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  color: #fff;
  text-decoration: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 0.6rem;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.brand-name {
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.brand-sub {
  font-size: 0.66rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
}

.primary-nav {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 0.3rem;
}

.nav-link {
  padding: 0.45rem 0.95rem;
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.78);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 600;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}

.nav-link.is-active {
  background: #fff;
  color: var(--chat-green-dark);
  font-weight: 700;
}

.context-nav {
  display: flex;
  gap: 1.4rem;
  padding: 0 1.5rem;
  background: #fff;
  border-bottom: 1px solid var(--chat-border);
  overflow-x: auto;
}

.context-link {
  padding: 0.75rem 0.1rem;
  color: var(--chat-text-muted);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 700;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  transition: color 0.16s ease, border-color 0.16s ease;
}

.context-link:hover {
  color: var(--chat-green-dark);
}

.context-link.is-active {
  color: var(--chat-green-dark);
  border-bottom-color: var(--chat-green);
}

.nav-link:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.context-link:focus-visible {
  outline: 2px solid var(--chat-green);
  outline-offset: 2px;
}

main {
  padding: 1.5rem;
}

@media (max-width: 560px) {
  .header-bar {
    padding: 0.6rem 1rem;
  }

  .context-nav {
    gap: 1.1rem;
    padding: 0 1rem;
  }

  .brand-sub {
    display: none;
  }
}
</style>
