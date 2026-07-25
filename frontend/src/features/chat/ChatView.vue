<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useChat } from './composables/useChat'
import MessageBubble from './components/MessageBubble.vue'
import TypingIndicator from './components/TypingIndicator.vue'
import ChatInput from './components/ChatInput.vue'

const { messages, isTyping, sendMessage } = useChat()

const messagesEl = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

watch([messages, isTyping], scrollToBottom, { deep: true })
onMounted(scrollToBottom)
</script>

<template>
  <section class="chat-view">
    <header class="chat-header">
      <div class="avatar" aria-hidden="true">C</div>
      <div class="header-text">
        <p class="name">Asistente de Seguros Colsubsidio</p>
        <p class="status">{{ isTyping ? 'Escribiendo…' : 'En línea' }}</p>
      </div>
    </header>

    <div ref="messagesEl" class="messages">
      <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
      <TypingIndicator v-if="isTyping" />
    </div>

    <ChatInput :disabled="isTyping" @send="sendMessage" />
  </section>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 7rem);
  min-height: 22rem;
  max-width: 640px;
  margin: 0 auto;
  background: var(--chat-bg);
  border: 1px solid var(--chat-border);
  border-radius: 0.75rem;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.75rem 1rem;
  background: var(--chat-green);
  color: #fff;
  flex-shrink: 0;
}

.avatar {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
}

.header-text {
  min-width: 0;
}

.name {
  margin: 0;
  font-weight: 600;
  font-size: 0.95rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status {
  margin: 0;
  font-size: 0.75rem;
  color: var(--chat-green-light);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  scroll-behavior: smooth;
}
</style>
