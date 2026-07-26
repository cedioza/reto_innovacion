<script setup>
// Panel del disparador proactivo: muestra cohortes de afiliados con un
// producto recomendado y permite simular el envío de una oferta proactiva
// que abre el chat en la sesión recién creada por el backend.
import { usePanel } from './composables/usePanel'
import CohortCard from './components/CohortCard.vue'

const { cohortes, fuente, isLoading, error, disparandoSerie, errorDisparo, reintentar, disparar } =
  usePanel()

function handleDisparar(cohorteId, serie) {
  disparar(cohorteId, serie)
}
</script>

<template>
  <section class="panel-view">
    <header class="panel-header">
      <h1>Panel — Oferta proactiva</h1>
      <p class="pitch">El seguro correcto, en el momento correcto, por el canal correcto.</p>
    </header>

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
  </section>
</template>

<style scoped>
.panel-view {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
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
