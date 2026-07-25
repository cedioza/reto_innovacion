<template>
  <div class="row">
    <div class="avatar" aria-hidden="true">C</div>
    <div class="bubble" role="status" aria-label="El asistente está escribiendo">
      <span class="dot" />
      <span class="dot" />
      <span class="dot" />
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
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
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.65rem 0.9rem;
  border-radius: 1rem;
  border-bottom-left-radius: 0.25rem;
  background: var(--chat-bubble-bot);
  border: 1px solid var(--chat-border);
  width: fit-content;
}

.dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--chat-text-muted);
  animation: bounce 1.2s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.15s;
}

.dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-0.2rem);
    opacity: 1;
  }
}
</style>
