<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'bot', text, type: 'consent', payload: {
    //   product_id, product_name, monthly_premium, annual_premium, currency,
    //   coverage_details: [str]
    // }, timestamp }
  },
  busy: {
    type: Boolean,
    default: false,
  },
  closed: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['confirm'])

const email = ref('')
const authorized = ref(false)

const EMAIL_RE = /^\S+@\S+\.\S+$/

const emailValid = computed(() => EMAIL_RE.test(email.value))

const canConfirm = computed(
  () => authorized.value && emailValid.value && !props.busy && !props.closed,
)

function formatAmount(amount) {
  return Number(amount).toLocaleString('es-CO')
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function confirm() {
  if (!canConfirm.value) return
  emit('confirm', email.value)
}
</script>

<template>
  <div class="row">
    <div class="avatar" aria-hidden="true">C</div>
    <div class="card">
      <p class="title">Resumen de tu solicitud</p>

      <p class="product-name">{{ message.payload.product_name }}</p>

      <div class="premium-block">
        <p class="premium-monthly">
          {{ formatAmount(message.payload.monthly_premium) }}
          <span class="unit">{{ message.payload.currency }}/mes</span>
        </p>
        <p v-if="message.payload.annual_premium" class="premium-annual">
          {{ formatAmount(message.payload.annual_premium) }} {{ message.payload.currency }}/año
        </p>
      </div>

      <div v-if="message.payload.coverage_details?.length" class="section">
        <p class="section-title">Coberturas</p>
        <ul class="coverage-list">
          <li v-for="(coverage, index) in message.payload.coverage_details" :key="index">
            {{ coverage }}
          </li>
        </ul>
      </div>

      <div class="section form-section">
        <label class="field-label" for="consent-email">Correo electrónico</label>
        <input
          id="consent-email"
          v-model="email"
          type="email"
          placeholder="tu@correo.com"
          class="email-input"
          :disabled="busy || closed"
        />

        <label class="toggle-label">
          <input
            type="checkbox"
            v-model="authorized"
            :disabled="busy || closed"
          />
          <span class="toggle-text">
            Autorizo el tratamiento de mis datos personales (Ley 1581 de 2012) y confirmo que
            entiendo las coberturas y exclusiones para dejar mi solicitud lista para pago.
          </span>
        </label>

        <p class="demo-note">Entorno de demostración — no se realizará ningún cobro.</p>

        <button type="button" class="confirm-btn" :disabled="!canConfirm" @click="confirm">
          Confirmar solicitud
        </button>
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
  margin: 0 0 0.4rem;
  color: var(--chat-text);
  font-size: 0.9rem;
  font-weight: 700;
}

.product-name {
  margin: 0 0 0.3rem;
  color: var(--chat-text);
  font-size: 0.85rem;
  font-weight: 600;
}

.premium-block {
  margin-bottom: 0.6rem;
}

.premium-monthly {
  margin: 0;
  color: var(--chat-green-dark);
  font-size: 1.6rem;
  font-weight: 800;
  line-height: 1.2;
}

.premium-monthly .unit {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--chat-text-muted);
}

.premium-annual {
  margin: 0.15rem 0 0;
  color: var(--chat-text-muted);
  font-size: 0.8rem;
}

.section {
  margin: 0.6rem 0;
}

.section-title {
  margin: 0 0 0.3rem;
  color: var(--chat-text);
  font-size: 0.85rem;
  font-weight: 700;
}

.coverage-list {
  list-style: disc;
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.85rem;
  color: var(--chat-text);
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--chat-text);
}

.email-input {
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--chat-border);
  border-radius: 0.5rem;
  font-size: 0.85rem;
  background: var(--chat-bg);
  color: var(--chat-text);
}

.email-input:disabled {
  opacity: 0.6;
}

.toggle-label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--chat-text);
}

.toggle-label input[type='checkbox'] {
  margin-top: 0.15rem;
  accent-color: var(--chat-green);
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.demo-note {
  margin: 0;
  font-size: 0.72rem;
  color: var(--chat-text-muted);
  font-style: italic;
}

.confirm-btn {
  margin-top: 0.2rem;
  padding: 0.5rem 0.9rem;
  border: none;
  border-radius: 0.5rem;
  background: var(--chat-green);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.confirm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.time {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
