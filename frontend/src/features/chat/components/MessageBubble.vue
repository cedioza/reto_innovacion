<script setup>
defineProps({
  message: {
    type: Object,
    required: true,
    // { id, from: 'user' | 'bot', text, timestamp }
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
  <div class="row" :class="message.from">
    <div v-if="message.from === 'bot'" class="avatar" aria-hidden="true">C</div>
    <div class="bubble">
      <p class="text">{{ message.text }}</p>
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
}

.row.user {
  justify-content: flex-end;
}

.row.bot {
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

.bubble {
  max-width: 78%;
  padding: 0.55rem 0.75rem;
  border-radius: 1rem;
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.06);
}

.row.user .bubble {
  background: var(--chat-bubble-user);
  border-bottom-right-radius: 0.25rem;
}

.row.bot .bubble {
  background: var(--chat-bubble-bot);
  border: 1px solid var(--chat-border);
  border-bottom-left-radius: 0.25rem;
}

.text {
  margin: 0;
  color: var(--chat-text);
  font-size: 0.95rem;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}

.time {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.7rem;
  color: var(--chat-text-muted);
  text-align: right;
}
</style>
