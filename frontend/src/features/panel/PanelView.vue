<script setup>
// Panel de negocio. Cada vista ("oferta", "funnel", "clientes") es una ruta
// propia y la navegación entre ellas vive en el header de la app: aquí solo
// se resuelve qué contenido corresponde a la ruta activa (`meta.vista`).
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { usePanel } from './composables/usePanel'
import { useClientes } from './composables/useClientes'
import CohortCard from './components/CohortCard.vue'
import FunnelSection from './components/FunnelSection.vue'
import ClientesTab from './components/ClientesTab.vue'
import ClienteDrawer from './components/ClienteDrawer.vue'

const route = useRoute()

const { cohortes, fuente, isLoading, error, disparandoSerie, errorDisparo, reintentar, disparar } =
  usePanel()

const { ficha, isLoadingFicha, errorFicha, abrirFicha, reintentarFicha, cerrarFicha } =
  useClientes({ autoLoad: false })

const vista = computed(() => route.meta.vista ?? 'oferta')
const titulo = computed(() => route.meta.titulo ?? 'Panel')
const descripcion = computed(() => route.meta.descripcion ?? '')

// Las vistas de datos densos (tiles del funnel, tabla de clientes) respiran
// mejor con más ancho que las tarjetas de cohorte.
const esVistaAncha = computed(() => vista.value !== 'oferta')

// El componente se reutiliza entre las tres rutas, así que la ficha abierta
// sobreviviría al cambio de vista y quedaría flotando sobre otra pantalla.
watch(vista, () => cerrarFicha())

function handleDisparar(cohorteId, serie) {
  disparar(cohorteId, serie)
}

function handleVerCliente(clienteId) {
  abrirFicha(clienteId)
}
</script>

<template>
  <section class="panel-view" :class="{ 'is-wide': esVistaAncha }">
    <header class="panel-header">
      <h1>{{ titulo }}</h1>
      <p class="pitch">{{ descripcion }}</p>
    </header>

    <div v-if="vista === 'oferta'" class="panel-body">
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

    <div v-else-if="vista === 'funnel'" class="panel-body">
      <FunnelSection />
    </div>

    <div v-else-if="vista === 'clientes'" class="panel-body">
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

.panel-body {
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

  .panel-body {
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
