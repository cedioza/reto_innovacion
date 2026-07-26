<script setup>
defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'bot', text, type: 'application', payload: {
    //   product_name, monthly_premium, currency, insurer_name, email,
    //   consent_timestamp
    // }, timestamp }
  },
})

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
      <p class="title">🎉 ¡Ya quedaste asegurado! (pendiente de pago)</p>

      <p class="product-name">{{ message.payload.product_name }}</p>

      <p class="premium-monthly">
        {{ formatAmount(message.payload.monthly_premium) }}
        <span class="unit">{{ message.payload.currency }}/mes</span>
      </p>

      <div v-if="message.payload.email" class="section">
        <p class="email-line">
          Tu solicitud va en camino: revisa tu correo <strong>{{ message.payload.email }}</strong>
          para finalizar con <strong>{{ message.payload.insurer_name }}</strong>
        </p>
        <p class="section-title">A tu correo llegará</p>
        <ul class="info-list">
          <li>Comprobante con el producto ({{ message.payload.product_name }}) y la prima
            ({{ formatAmount(message.payload.monthly_premium) }} {{ message.payload.currency }}/mes)</li>
          <li>Un link de {{ message.payload.insurer_name }} para finalizar el proceso</li>
        </ul>
      </div>
      <div v-else class="section">
        <p class="email-line">
          Tu solicitud quedó registrada y lista para pago con <strong>{{ message.payload.insurer_name }}</strong>.
        </p>
      </div>

      <p class="demo-note">(simulación — entorno de demostración)</p>

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
  color: var(--chat-green-dark);
  font-size: 0.95rem;
  font-weight: 700;
}

.product-name {
  margin: 0 0 0.3rem;
  color: var(--chat-text);
  font-size: 0.85rem;
  font-weight: 600;
}

.premium-monthly {
  margin: 0 0 0.5rem;
  color: var(--chat-green-dark);
  font-size: 1.3rem;
  font-weight: 800;
  line-height: 1.2;
}

.premium-monthly .unit {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--chat-text-muted);
}

.section {
  margin: 0.6rem 0;
}

.section-title {
  margin: 0.4rem 0 0.3rem;
  color: var(--chat-text);
  font-size: 0.85rem;
  font-weight: 700;
}

.email-line {
  margin: 0;
  font-size: 0.85rem;
  color: var(--chat-text);
}

.info-list {
  list-style: disc;
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.85rem;
  color: var(--chat-text);
}

.demo-note {
  margin: 0.5rem 0 0;
  font-size: 0.72rem;
  color: var(--chat-text-muted);
  font-style: italic;
}

.time {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
