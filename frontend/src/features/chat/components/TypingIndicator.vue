<template>
  <div class="typing-row" role="status" aria-label="Clara is typing">
    <div class="assistant-avatar" aria-hidden="true">C</div>
    <div class="typing-bubble"><span></span><span></span><span></span></div>
    <span class="typing-label">Clara is typing</span>
  </div>
</template>

<style scoped>
.typing-row { display: flex; align-items: center; gap: 10px; margin-bottom: 5px; animation: fade-in .25s ease both; }.assistant-avatar { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border-radius: 10px 10px 10px 3px; color: #174d40; background: #c7e4a0; font-family: Georgia, serif; font-weight: 700; }.typing-bubble { display: flex; gap: 4px; padding: 13px 15px; border-radius: 17px 17px 17px 4px; background: #e9f1e7; }.typing-bubble span { width: 5px; height: 5px; border-radius: 50%; background: #6c9580; animation: bounce 1s infinite ease-in-out; }.typing-bubble span:nth-child(2) { animation-delay: .15s; }.typing-bubble span:nth-child(3) { animation-delay: .3s; }.typing-label { color: #82978c; font-size: 11px; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .55; } 30% { transform: translateY(-4px); opacity: 1; } } @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .typing-row, .typing-bubble span { animation: none; }.typing-bubble span { opacity: .8; } }
</style>
