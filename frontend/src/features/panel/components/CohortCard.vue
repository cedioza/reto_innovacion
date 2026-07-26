<script setup>
import { ref } from 'vue'

defineProps({
  cohorte: {
    type: Object,
    required: true,
    // { id, nombre, descripcion, criterio_humano, total, muestra: [{serie, age_range, household_segment, senales}], producto: {product_id, product_name} | null, razones: [] }
  },
  disparandoSerie: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['disparar'])

const serieSeleccionada = ref(null)

function seleccionar(serie) {
  serieSeleccionada.value = serie
}

function formatTotal(total) {
  return Number(total).toLocaleString('es-CO')
}

function handleDisparar() {
  if (!serieSeleccionada.value) return
  emit('disparar', serieSeleccionada.value)
}
</script>

<template>
  <article class="cohort-card">
    <header class="cohort-header">
      <p class="cohort-name">{{ cohorte.nombre }}</p>
      <p v-if="cohorte.descripcion" class="cohort-descripcion">{{ cohorte.descripcion }}</p>
    </header>

    <p class="cohort-criterio">{{ cohorte.criterio_humano }}</p>

    <p class="cohort-total">
      <span class="total-number">{{ formatTotal(cohorte.total) }}</span>
      afiliados con este perfil
    </p>

    <div v-if="cohorte.producto" class="producto-block">
      <p class="producto-label">Producto recomendado</p>
      <p class="producto-nombre">{{ cohorte.producto.product_name }}</p>
      <ul v-if="cohorte.razones?.length" class="razones">
        <li v-for="(razon, index) in cohorte.razones" :key="index" class="razon">
          {{ razon }}
        </li>
      </ul>
    </div>

    <div v-if="cohorte.muestra?.length" class="muestra-block">
      <p class="muestra-label">Selecciona un afiliado para simular</p>
      <ul class="muestra-list">
        <li v-for="miembro in cohorte.muestra" :key="miembro.serie">
          <button
            type="button"
            class="miembro-row"
            :class="{ selected: serieSeleccionada === miembro.serie }"
            @click="seleccionar(miembro.serie)"
          >
            <span class="miembro-serie">{{ miembro.serie }}</span>
            <span class="miembro-detalle">
              {{ miembro.age_range }}<template v-if="miembro.household_segment"> · {{ miembro.household_segment }}</template>
            </span>
            <span v-if="miembro.senales?.length" class="miembro-senales">
              <span v-for="senal in miembro.senales" :key="senal" class="chip">{{ senal }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>

    <button
      type="button"
      class="disparar-btn"
      :disabled="!serieSeleccionada || disparandoSerie === serieSeleccionada"
      @click="handleDisparar"
    >
      {{ disparandoSerie === serieSeleccionada ? 'Disparando…' : 'Simular oferta proactiva' }}
    </button>
  </article>
</template>

<style scoped>
.cohort-card {
  background: #fff;
  border: 1px solid var(--chat-border);
  border-radius: 0.9rem;
  padding: 1.1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.cohort-header {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.cohort-name {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--chat-text);
}

.cohort-descripcion {
  margin: 0;
  font-size: 0.85rem;
  color: var(--chat-text-muted);
}

.cohort-criterio {
  margin: 0;
  font-size: 0.85rem;
  color: var(--chat-green-dark);
  font-style: italic;
}

.cohort-total {
  margin: 0;
  font-size: 0.9rem;
  color: var(--chat-text);
}

.total-number {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--chat-green-dark);
  margin-right: 0.3rem;
}

.producto-block {
  background: var(--chat-green-light);
  border-radius: 0.6rem;
  padding: 0.6rem 0.75rem;
}

.producto-label {
  margin: 0 0 0.15rem;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--chat-green-dark);
}

.producto-nombre {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--chat-text);
}

.razones {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.8rem;
  color: var(--chat-text-muted);
}

.muestra-block {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.muestra-label {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--chat-text-muted);
}

.muestra-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.miembro-row {
  width: 100%;
  text-align: left;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.65rem;
  border-radius: 0.5rem;
  border: 1px solid var(--chat-border);
  background: var(--chat-bg);
  cursor: pointer;
  font: inherit;
}

.miembro-row.selected {
  border-color: var(--chat-green);
  background: var(--chat-green-light);
}

.miembro-serie {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--chat-text);
}

.miembro-detalle {
  font-size: 0.8rem;
  color: var(--chat-text-muted);
}

.miembro-senales {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.chip {
  display: inline-block;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--chat-border);
  font-size: 0.7rem;
  color: var(--chat-text-muted);
}

.disparar-btn {
  align-self: flex-start;
  margin-top: 0.3rem;
  padding: 0.55rem 1.1rem;
  border-radius: 0.6rem;
  border: none;
  background: var(--chat-green);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
}

.disparar-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
