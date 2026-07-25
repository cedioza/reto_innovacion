<script setup>
import { ref } from 'vue'

const emit = defineEmits(['send'])
const draft = ref('')

function submitMessage() {
  const text = draft.value.trim()
  if (!text) return
  emit('send', text)
  draft.value = ''
}
</script>

<template>
  <form class="composer" @submit.prevent="submitMessage">
    <label class="sr-only" for="chat-message">Write a message</label>
    <input id="chat-message" v-model="draft" type="text" autocomplete="off" enterkeyhint="send" maxlength="1000" placeholder="Write a message…" />
    <button type="submit" :disabled="!draft.trim()" aria-label="Send message">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 4 16 8-16 8 3-8-3-8Zm3.1 8h6.5" /></svg>
    </button>
  </form>
</template>

<style scoped>
.composer { display: flex; align-items: center; gap: 10px; padding: 15px 22px 18px; border-top: 1px solid #e8eee5; background: rgba(255,255,255,.94); }.composer input { width: 100%; min-width: 0; padding: 14px 17px; border: 1px solid #c7d9c6; border-radius: 15px; outline: none; color: #24463b; background: #f4f8f1; font: inherit; font-size: 16px; transition: border .2s, box-shadow .2s; }.composer input::placeholder { color: #70887d; }.composer input:focus { border-color: #3f7c57; box-shadow: 0 0 0 3px rgba(63,124,87,.22); }.composer button { display: grid; width: 44px; height: 44px; flex: 0 0 44px; place-items: center; border: 0; border-radius: 14px; color: #173f34; background: #b9e184; cursor: pointer; transition: transform .2s, background .2s, box-shadow .2s; }.composer button:hover:not(:disabled) { transform: translateY(-1px); background: #a9d875; }.composer button:focus-visible { outline: 3px solid #2d684a; outline-offset: 3px; }.composer button:disabled { cursor: not-allowed; opacity: .5; }.composer svg { width: 19px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) { .composer { padding: 11px 13px max(13px, env(safe-area-inset-bottom)); } }
@media (prefers-reduced-motion: reduce) { .composer input, .composer button { transition: none; }.composer button:hover:not(:disabled) { transform: none; } }
</style>
