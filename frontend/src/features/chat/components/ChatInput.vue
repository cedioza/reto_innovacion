<script setup>
import { ref } from 'vue'

defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['send'])

const text = ref('')

function submit() {
  const trimmed = text.value.trim()
  if (!trimmed) return
  emit('send', trimmed)
  text.value = ''
}
</script>

<template>
  <form class="input-bar" @submit.prevent="submit">
    <input
      v-model="text"
      type="text"
      placeholder="Escribe tu mensaje…"
      :disabled="disabled"
      autocomplete="off"
      aria-label="Mensaje"
    />
    <button type="submit" :disabled="disabled || !text.trim()" aria-label="Enviar mensaje">
      Enviar
    </button>
  </form>
</template>

<style scoped>
.input-bar {
  display: flex;
  gap: 0.5rem;
  padding: 0.6rem;
  background: #fff;
  border-top: 1px solid var(--chat-border);
}

input {
  flex: 1;
  min-height: 2.75rem;
  padding: 0 0.9rem;
  border: 1px solid var(--chat-border);
  border-radius: 1.5rem;
  font-size: 1rem;
  color: var(--chat-text);
  outline: none;
}

input:focus {
  border-color: var(--chat-green);
}

input:disabled {
  background: var(--chat-bg);
  color: var(--chat-text-muted);
}

button {
  min-height: 2.75rem;
  min-width: 4.5rem;
  padding: 0 1rem;
  border: none;
  border-radius: 1.5rem;
  background: var(--chat-green);
  color: #fff;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
}

button:disabled {
  background: var(--chat-border);
  color: var(--chat-text-muted);
  cursor: not-allowed;
}

button:not(:disabled):hover {
  background: var(--chat-green-dark);
}
</style>
