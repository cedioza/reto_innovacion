<script setup>
import { computed } from 'vue'

const props = defineProps({
  producto: {
    type: Object,
    required: true,
    // { product_id, product_name, categoria, etapas: {recomendado, cotizado, consentimiento, comprado}, tasas: {...} }
  },
})

const ETAPAS = [
  { key: 'recomendado', label: 'Recomendado' },
  { key: 'cotizado', label: 'Cotizado' },
  { key: 'consentimiento', label: 'Consentimiento' },
  { key: 'comprado', label: 'Comprado' },
]

const maxEtapa = computed(() => Math.max(props.producto.etapas?.recomendado ?? 0, 1))

const sinVentas = computed(() => {
  const etapas = props.producto.etapas ?? {}
  return ETAPAS.every((etapa) => !(etapas[etapa.key] > 0))
})

const conversionPct = computed(() => {
  const tasa = props.producto.tasas?.comprado_sobre_recomendado ?? 0
  return Math.round(tasa * 100)
})

function anchoBarra(key) {
  const valor = props.producto.etapas?.[key] ?? 0
  return `${Math.min(100, Math.round((valor / maxEtapa.value) * 100))}%`
}

function valorEtapa(key) {
  return props.producto.etapas?.[key] ?? 0
}
</script>

<template>
  <article class="funnel-row" :class="{ 'sin-ventas': sinVentas }">
    <header class="funnel-row-header">
      <p class="funnel-row-nombre">{{ producto.product_name }}</p>
      <p v-if="sinVentas" class="funnel-row-vacio">sin ventas</p>
      <p v-else class="funnel-row-conversion">convierte {{ conversionPct }}%</p>
    </header>

    <div class="funnel-bars">
      <div v-for="etapa in ETAPAS" :key="etapa.key" class="funnel-bar-line">
        <span class="funnel-bar-label">{{ etapa.label }}</span>
        <span class="funnel-bar-track">
          <span
            class="funnel-bar-fill"
            :class="`funnel-bar-${etapa.key}`"
            :style="{ width: anchoBarra(etapa.key) }"
          ></span>
        </span>
        <span class="funnel-bar-valor">{{ valorEtapa(etapa.key) }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.funnel-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.65rem 0.8rem;
  border: 1px solid var(--chat-border);
  border-radius: 0.6rem;
  background: #fff;
}

.funnel-row.sin-ventas {
  opacity: 0.5;
}

.funnel-row-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.funnel-row-nombre {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--chat-text);
}

.funnel-row-conversion {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--chat-green-dark);
  white-space: nowrap;
}

.funnel-row-vacio {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--chat-text-muted);
  white-space: nowrap;
}

.funnel-bars {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.funnel-bar-line {
  display: grid;
  grid-template-columns: 6.5rem 1fr 2.2rem;
  align-items: center;
  gap: 0.5rem;
}

.funnel-bar-label {
  font-size: 0.72rem;
  color: var(--chat-text-muted);
}

.funnel-bar-track {
  display: block;
  height: 0.55rem;
  border-radius: 999px;
  background: var(--chat-green-light);
  overflow: hidden;
}

.funnel-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--chat-green);
}

.funnel-bar-comprado {
  background: var(--chat-green-dark);
}

.funnel-bar-valor {
  font-size: 0.75rem;
  color: var(--chat-text);
  text-align: right;
}
</style>
