<script setup>
import { computed } from 'vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'bot', text, type: 'comparison', payload: {
    //   actual: { monthly_premium, annual_premium, currency, adjustments: [{code,...}], ... },
    //   propuesta: { monthly_premium, annual_premium, currency, adjustments: [{code,...}], ... },
    //   diferencia_mensual, ajustes_disponibles: [{code, name, description}]
    // }, timestamp }
  },
  busy: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['apply'])

const propuestaCodes = computed(
  () => new Set((props.message.payload.propuesta.adjustments ?? []).map((adj) => adj.code)),
)

const diferencia = computed(() => props.message.payload.diferencia_mensual)

const diferenciaClass = computed(() => {
  if (diferencia.value < 0) return 'saving'
  if (diferencia.value > 0) return 'surcharge'
  return 'neutral'
})

function formatAmount(amount) {
  return Number(amount).toLocaleString('es-CO')
}

function formatSigned(amount) {
  const formatted = formatAmount(Math.abs(amount))
  if (amount < 0) return `-${formatted}`
  if (amount > 0) return `+${formatted}`
  return formatted
}

function isActive(code) {
  return propuestaCodes.value.has(code)
}

function toggle(code) {
  if (props.busy) return
  const active = new Set(propuestaCodes.value)
  if (active.has(code)) {
    active.delete(code)
  } else {
    active.add(code)
  }
  emit('apply', Array.from(active))
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="row">
    <div class="avatar" aria-hidden="true">C</div>
    <div class="card">
      <p class="title">Comparador de coberturas</p>

      <div class="columns">
        <div class="column">
          <p class="column-label">Actual</p>
          <p class="premium-monthly">
            {{ formatAmount(message.payload.actual.monthly_premium) }}
            <span class="unit">{{ message.payload.actual.currency }}/mes</span>
          </p>
          <p v-if="message.payload.actual.annual_premium" class="premium-annual">
            {{ formatAmount(message.payload.actual.annual_premium) }}
            {{ message.payload.actual.currency }}/año
          </p>
        </div>
        <div class="column">
          <p class="column-label">Propuesta</p>
          <p class="premium-monthly">
            {{ formatAmount(message.payload.propuesta.monthly_premium) }}
            <span class="unit">{{ message.payload.propuesta.currency }}/mes</span>
          </p>
          <p v-if="message.payload.propuesta.annual_premium" class="premium-annual">
            {{ formatAmount(message.payload.propuesta.annual_premium) }}
            {{ message.payload.propuesta.currency }}/año
          </p>
        </div>
      </div>

      <p class="diferencia" :class="diferenciaClass">
        {{ formatSigned(diferencia) }} {{ message.payload.propuesta.currency }}/mes
      </p>

      <div class="section">
        <p class="section-title">
          Ajustes
          <span v-if="busy" class="busy-indicator">Actualizando…</span>
        </p>
        <ul class="toggle-list">
          <li v-for="adjustment in message.payload.ajustes_disponibles" :key="adjustment.code" class="toggle-item">
            <label class="toggle-label">
              <input
                type="checkbox"
                :checked="isActive(adjustment.code)"
                :disabled="busy"
                @change="toggle(adjustment.code)"
              />
              <span class="toggle-text">
                <strong>{{ adjustment.name }}</strong>
                <span v-if="adjustment.description" class="toggle-description">
                  {{ adjustment.description }}
                </span>
              </span>
            </label>
          </li>
        </ul>
      </div>

      <span v-if="message.timestamp" class="time">{{ formatTime(message.timestamp) }}</span>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  max-width: 100%;
  justify-content: flex-start;
}

.avatar {
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: var(--chat-green);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card {
  max-width: 90%;
  padding: 0.75rem 0.9rem;
  border-radius: 1rem;
  border-bottom-left-radius: 0.25rem;
  background: var(--chat-bubble-bot);
  border: 1px solid var(--chat-border);
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.06);
}

.title {
  margin: 0 0 0.5rem;
  color: var(--chat-text);
  font-size: 0.9rem;
  font-weight: 700;
}

.columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.column {
  min-width: 0;
  padding: 0.5rem;
  border-radius: 0.6rem;
  background: var(--chat-green-light);
}

.column-label {
  margin: 0 0 0.15rem;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--chat-text-muted);
}

.premium-monthly {
  margin: 0;
  color: var(--chat-green-dark);
  font-size: 1.05rem;
  font-weight: 800;
  line-height: 1.2;
  word-break: break-word;
}

.premium-monthly .unit {
  display: block;
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--chat-text-muted);
}

.premium-annual {
  margin: 0.15rem 0 0;
  color: var(--chat-text-muted);
  font-size: 0.68rem;
}

.diferencia {
  margin: 0.6rem 0 0.2rem;
  font-size: 0.95rem;
  font-weight: 800;
  text-align: center;
}

.diferencia.saving {
  color: var(--chat-green-dark);
}

.diferencia.surcharge {
  color: #b3261e;
}

.diferencia.neutral {
  color: var(--chat-text-muted);
}

.section {
  margin-top: 0.6rem;
}

.section-title {
  margin: 0 0 0.35rem;
  color: var(--chat-text);
  font-size: 0.85rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.busy-indicator {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--chat-text-muted);
}

.toggle-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.toggle-item {
  padding: 0.4rem 0.5rem;
  border-radius: 0.5rem;
  background: var(--chat-bg);
}

.toggle-label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.toggle-label input[type='checkbox'] {
  margin-top: 0.15rem;
  accent-color: var(--chat-green);
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.toggle-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  color: var(--chat-text);
}

.toggle-description {
  font-size: 0.75rem;
  color: var(--chat-text-muted);
}

.time {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
