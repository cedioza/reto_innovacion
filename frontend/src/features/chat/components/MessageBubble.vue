<script setup>
defineProps({
  message: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <article class="message-row" :class="`message-row--${message.author}`">
    <div v-if="message.author === 'assistant'" class="assistant-avatar" aria-hidden="true">C</div>
    <div class="message-stack">
      <div class="bubble" :class="`bubble--${message.author}`">
        <p>{{ message.text }}</p>
        <span class="timestamp">{{ message.time }} <span v-if="message.author === 'user'" class="read-mark">✓✓</span></span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.message-row { display: flex; align-items: flex-end; gap: 10px; margin: 0 0 18px; animation: rise-in .35s ease both; }.message-row--user { justify-content: flex-end; }.message-stack { max-width: min(82%, 560px); min-width: 0; }.assistant-avatar { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border-radius: 10px 10px 10px 3px; color: #174d40; background: #c7e4a0; font-family: Georgia, serif; font-weight: 700; }
.bubble { padding: 13px 15px 9px; border-radius: 17px 17px 17px 4px; color: #234238; background: #e4efe2; box-shadow: 0 2px 6px rgba(39,72,59,.04); }.bubble--user { border-radius: 17px 17px 4px 17px; color: #fff; background: #236850; box-shadow: 0 5px 12px rgba(40,114,92,.14); }.bubble p { margin: 0; overflow-wrap: anywhere; font-size: 14px; line-height: 1.5; }.timestamp { display: block; margin-top: 7px; color: #6d8378; font-size: 10px; text-align: right; }.bubble--user .timestamp { color: #d0ead8; }.read-mark { margin-left: 3px; color: #dcf7ac; font-size: 9px; letter-spacing: -2px; }
@keyframes rise-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
@media (max-width: 360px) { .message-stack { max-width: 86%; }.message-row { gap: 7px; }.assistant-avatar { width: 25px; height: 25px; flex-basis: 25px; } }
@media (prefers-reduced-motion: reduce) { .message-row { animation: none; } }
</style>
