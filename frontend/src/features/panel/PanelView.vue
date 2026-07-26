<script setup>
// Panel de negocio en tres vistas independientes: "Oferta proactiva"
// (cohortes del disparador), "Funnel de ventas" (métricas por producto) y
// "Clientes" (buscador + ficha). El encabezado se adapta a la pestaña activa.
import { computed, ref } from 'vue'
import { usePanel } from './composables/usePanel'
import { useClientes } from './composables/useClientes'
import CohortCard from './components/CohortCard.vue'
import FunnelSection from './components/FunnelSection.vue'
import ClientesTab from './components/ClientesTab.vue'
import ClienteDrawer from './components/ClienteDrawer.vue'

const { cohortes, fuente, isLoading, error, disparandoSerie, errorDisparo, reintentar, disparar } =
  usePanel()

const { ficha, isLoadingFicha, errorFicha, abrirFicha, reintentarFicha, cerrarFicha } =
  useClientes({ autoLoad: false })

function handleDisparar(cohorteId, serie) {
  disparar(cohorteId, serie)
}

const tabs = [
  {
    id: 'proactiva',
    label: 'Oferta proactiva',
    titulo: 'Panel — Oferta proactiva',
    descripcion: 'El seguro correcto, en el momento correcto, por el canal correcto.',
  },
  {
    id: 'funnel',
    label: 'Funnel de ventas',
    titulo: 'Funnel de ventas',
    descripcion: 'De la conversación a la compra: conversión por producto.',
  },
  {
    id: 'clientes',
    label: 'Clientes',
    titulo: 'Clientes',
    descripcion: 'Quién pasó por el funnel: perfil, seguros ofrecidos y comprados.',
  },
]

const tabActiva = ref('proactiva')
const tabActual = computed(() => tabs.find((tab) => tab.id === tabActiva.value) ?? tabs[0])

// Las vistas de datos densos (tabla de clientes, tiles del funnel) respiran
// mejor con más ancho que las tarjetas de cohorte.
const esVistaAncha = computed(() => tabActiva.value !== 'proactiva')

function cambiarTab(id) {
  if (id === tabActiva.value) return
  // Salir de "Clientes" con la ficha abierta dejaría el drawer flotando
  // sobre una vista que no le corresponde.
  if (tabActiva.value === 'clientes') cerrarFicha()
  tabActiva.value = id
}

function handleVerCliente(clienteId) {
  abrirFicha(clienteId)
}
</script>

<template>
  <section class="panel-view" :class="{ 'is-wide': esVistaAncha }">
    <header class="panel-header">
      <h1>{{ tabActual.titulo }}</h1>
      <p class="pitch">{{ tabActual.descripcion }}</p>
    </header>

    <nav class="tabs" role="tablist" aria-label="Vistas del panel">
      <button
        v-for="tab in tabs"
        :id="`tab-${tab.id}`"
        :key="tab.id"
        type="button"
        class="tab-btn"
        :class="{ active: tabActiva === tab.id }"
        role="tab"
        :aria-selected="tabActiva === tab.id"
        :aria-controls="`panel-${tab.id}`"
        @click="cambiarTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div
      v-if="tabActiva === 'proactiva'"
      id="panel-proactiva"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="tab-proactiva"
    >
      <p v-if="isLoading" class="state-text">Cargando cohortes…</p>

      <div v-else-if="error" class="state-card">
        <p class="state-text">{{ error }}</p>
        <button type="button" class="retry-btn" @click="reintentar">Reintentar</button>
      </div>

      <div v-else>
        <p v-if="fuente === 'sin_datos'" class="empty-banner">
          La base de afiliados está vacía — carga el dataset con cargar_afiliados.py
        </p>

        <p v-if="errorDisparo" class="disparo-error">{{ errorDisparo }}</p>

        <div v-if="cohortes.length" class="cohortes-list">
          <CohortCard
            v-for="cohorte in cohortes"
            :key="cohorte.id"
            :cohorte="cohorte"
            :disparando-serie="disparandoSerie"
            @disparar="(serie) => handleDisparar(cohorte.id, serie)"
          />
        </div>

        <p v-else-if="fuente !== 'sin_datos'" class="state-text">No hay cohortes disponibles.</p>
      </div>
    </div>

    <div
      v-else-if="tabActiva === 'funnel'"
      id="panel-funnel"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="tab-funnel"
    >
      <FunnelSection />
    </div>

    <div
      v-else-if="tabActiva === 'clientes'"
      id="panel-clientes"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="tab-clientes"
    >
      <ClientesTab @ver-cliente="handleVerCliente" />
    </div>

    <ClienteDrawer
      v-if="ficha || isLoadingFicha || errorFicha"
      :ficha="ficha"
      :is-loading="isLoadingFicha"
      :error="errorFicha"
      @cerrar="cerrarFicha"
      @reintentar="reintentarFicha"
    />
  </section>
</template>

<style scoped>
.panel-view {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  transition: max-width 0.24s ease;
}

.panel-view.is-wide {
  max-width: 980px;
}

.panel-header {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.panel-header h1 {
  margin: 0;
  font-size: 1.4rem;
  color: var(--chat-text);
}

.pitch {
  margin: 0;
  font-size: 0.9rem;
  color: var(--chat-green-dark);
  font-weight: 600;
}

/* Control segmentado: cada vista es un panel propio, no una sección más
   de una página larga. */
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  padding: 0.25rem;
  border: 1px solid var(--chat-border);
  border-radius: 0.7rem;
  background: #fff;
}

.tab-btn {
  flex: 1 1 auto;
  padding: 0.55rem 1rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--chat-text-muted);
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.tab-btn:hover:not(.active) {
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
}

.tab-btn.active {
  background: var(--chat-green);
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 92, 58, 0.28);
}

.tab-panel {
  animation: panel-in 0.22s ease both;
}

@keyframes panel-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel-view {
    transition: none;
  }

  .tab-panel {
    animation: none;
  }
}

.state-text {
  margin: 0;
  color: var(--chat-text-muted);
  font-size: 0.95rem;
}

.state-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.6rem;
}

.retry-btn {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--chat-green);
  background: transparent;
  color: var(--chat-green-dark);
  font-weight: 700;
  cursor: pointer;
}

.empty-banner {
  margin: 0 0 1rem;
  padding: 0.65rem 0.9rem;
  border-radius: 0.6rem;
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
  font-size: 0.85rem;
  font-weight: 600;
}

.disparo-error {
  margin: 0 0 1rem;
  padding: 0.6rem 0.9rem;
  border-radius: 0.6rem;
  background: #fdecea;
  color: #b3261e;
  font-size: 0.85rem;
}

.cohortes-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
</style>
