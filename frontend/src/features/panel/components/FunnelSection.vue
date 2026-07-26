<script setup>
import { computed } from 'vue'
import { useFunnel } from '../composables/useFunnel'
import FunnelProductRow from './FunnelProductRow.vue'

const { metricas, isLoading, error, reintentar } = useFunnel()

const totales = computed(() => metricas.value?.totales ?? null)
const productos = computed(() => metricas.value?.funnel_por_producto ?? [])
const corte = computed(() => metricas.value?.corte_afiliacion ?? null)

function pct(valor) {
  return `${Math.round((valor ?? 0) * 100)}%`
}
</script>

<template>
  <div class="funnel-section">
    <p v-if="isLoading" class="state-text">Cargando funnel de ventas…</p>

    <div v-else-if="error" class="state-card">
      <p class="state-text">{{ error }}</p>
      <button type="button" class="retry-btn" @click="reintentar">Reintentar</button>
    </div>

    <div v-else>
      <p v-if="metricas?.fuente === 'sin_datos'" class="empty-banner">
        No hay datos de conversaciones aún — genera datos de demo con
        <code>python -m app.scripts.seed_demo</code>
      </p>

      <template v-else>
        <div v-if="totales" class="tiles-row">
          <div class="tile">
            <p class="tile-valor">{{ totales.conversaciones }}</p>
            <p class="tile-label">Conversaciones</p>
          </div>
          <div class="tile">
            <p class="tile-valor">{{ totales.compradas }}</p>
            <p class="tile-label">Compradas</p>
          </div>
          <div class="tile">
            <p class="tile-valor">{{ pct(totales.conversion_global) }}</p>
            <p class="tile-label">Conversión global</p>
          </div>
          <div v-if="corte" class="tile">
            <p class="tile-valor">{{ corte.base.compradas }} / {{ corte.declarado.compradas }}</p>
            <p class="tile-label">Afiliados vs Declarados</p>
          </div>
        </div>

        <div v-if="productos.length" class="productos-list">
          <FunnelProductRow
            v-for="producto in productos"
            :key="producto.product_id"
            :producto="producto"
          />
        </div>
        <p v-else class="state-text">No hay productos con datos de funnel.</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.funnel-section {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
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
  margin: 0;
  padding: 0.65rem 0.9rem;
  border-radius: 0.6rem;
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
  font-size: 0.85rem;
  font-weight: 600;
}

.tiles-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.6rem;
}

.tile {
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--chat-border);
  border-radius: 0.6rem;
  background: #fff;
  text-align: center;
}

.tile-valor {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--chat-green-dark);
}

.tile-label {
  margin: 0.15rem 0 0;
  font-size: 0.72rem;
  color: var(--chat-text-muted);
}

.productos-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

@media (max-width: 640px) {
  .tiles-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
