<script setup>
defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'bot', text, type: 'recommendation', payload: { product_id, product_name, reasons: [{code, label, evidence}] }, timestamp }
  },
})

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
      <span class="badge">Recomendado para ti</span>
      <p class="product-name">{{ message.payload.product_name }}</p>
      <ul class="reasons">
        <li v-for="reason in message.payload.reasons" :key="reason.code" class="reason">
          <p class="label">{{ reason.label }}</p>
          <p v-if="reason.evidence" class="evidence">{{ reason.evidence }}</p>
        </li>
      </ul>
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

.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
  font-size: 0.7rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
}

.product-name {
  margin: 0 0 0.5rem;
  color: var(--chat-text);
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.3;
}

.reasons {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.reason {
  padding-left: 0.65rem;
  border-left: 3px solid var(--chat-green);
}

.label {
  margin: 0;
  color: var(--chat-text);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.35;
}

.evidence {
  margin: 0.15rem 0 0;
  color: var(--chat-text-muted);
  font-size: 0.78rem;
  line-height: 1.35;
}

.time {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
