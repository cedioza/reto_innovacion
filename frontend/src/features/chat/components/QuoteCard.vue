<script setup>
defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'bot', text, type: 'quote', payload: {
    //   base_amount, adjustments: [{code,name,description,premium_modifier}],
    //   monthly_premium, annual_premium, currency, coverage_details: [str], exclusions: [str]
    // }, timestamp }
  },
})

defineEmits(['adjust'])

// Solo formateo visual (separador de miles) — el front nunca calcula precios,
// las cifras vienen tal cual del motor.
function formatAmount(amount) {
  return Number(amount).toLocaleString('es-CO')
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

      <details v-if="message.payload.exclusions?.length" class="collapsible">
        <summary>Exclusiones</summary>
        <ul class="exclusion-list">
          <li v-for="(exclusion, index) in message.payload.exclusions" :key="index">
            {{ exclusion }}
          </li>
        </ul>
      </details>

      <details v-if="message.payload.adjustments?.length" class="collapsible">
        <summary>Ajustes aplicados</summary>
        <ul class="adjustment-list">
          <li v-for="adjustment in message.payload.adjustments" :key="adjustment.code">
            <strong>{{ adjustment.name }}</strong>
            <span v-if="adjustment.description"> — {{ adjustment.description }}</span>
          </li>
        </ul>
      </details>

      <button
        type="button"
        class="adjust-btn"
        disabled
        hidden
        @click="$emit('adjust')"
      >
        Ajustar coberturas
      </button>

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

.coverage-list,
.exclusion-list,
.adjustment-list {
  list-style: disc;
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.85rem;
  color: var(--chat-text);
}

.collapsible {
  margin: 0.5rem 0;
  font-size: 0.85rem;
}

.collapsible summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--chat-green-dark);
}

.collapsible[open] summary {
  margin-bottom: 0.3rem;
}

.adjust-btn {
  margin-top: 0.5rem;
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--chat-green);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--chat-green-dark);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}

.time {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
