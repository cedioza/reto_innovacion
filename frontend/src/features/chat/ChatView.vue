<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ChatInput from './components/ChatInput.vue'
import MessageBubble from './components/MessageBubble.vue'
import TypingIndicator from './components/TypingIndicator.vue'

const messages = ref([
  {
    id: 1,
    author: 'assistant',
    text: 'Hi! I’m your Colsubsidio insurance guide. I can help you understand your coverage and find the right next step.',
    time: '09:41',
  },
  {
    id: 2,
    author: 'user',
    text: 'I want to protect my family, but I’m not sure where to start.',
    time: '09:42',
  },
  {
    id: 3,
    author: 'assistant',
    text: 'That’s a thoughtful place to begin. Let’s make it simple: is your main priority everyday health, income protection, or support for unexpected events?',
    time: '09:42',
  },
])

const conversation = ref(null)
const isTyping = ref(false)
let replyTimer

const assistantReplies = [
  'I’ve noted that down. We can compare the options calmly and keep the recommendation focused on what matters most to your family.',
  'A good next step is to define who needs cover and what kind of support would make the biggest difference. I’ll guide you from there.',
  'Thanks for sharing that. I can help you turn that priority into a clear, easy-to-understand insurance option.',
]

function scrollToLatest() {
  nextTick(() => {
    conversation.value?.scrollTo({ top: conversation.value.scrollHeight, behavior: 'smooth' })
  })
}

function sendMessage(text) {
  messages.value.push({
    id: Date.now(),
    author: 'user',
    text,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  })
  isTyping.value = true
  scrollToLatest()

  clearTimeout(replyTimer)
  replyTimer = setTimeout(() => {
    messages.value.push({
      id: Date.now() + 1,
      author: 'assistant',
      text: assistantReplies[messages.value.length % assistantReplies.length],
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })
    isTyping.value = false
    scrollToLatest()
  }, 1100)
}

watch(isTyping, scrollToLatest)

onBeforeUnmount(() => clearTimeout(replyTimer))
</script>

<template>
  <main class="chat-page">
    <section class="chat-shell" aria-label="Insurance assistant chat">
      <header class="chat-header">
        <div class="brand-mark" aria-hidden="true">
          <span></span>
          <span></span>
        </div>
        <div class="header-copy">
          <p class="eyebrow">Colsubsidio · Insurance</p>
          <h1>Clara, your guide</h1>
          <p class="presence"><span class="status-dot"></span>Online and ready to help</p>
        </div>
        <div class="header-mark" aria-hidden="true">
          <span></span><span></span><span></span>
        </div>
      </header>

      <div ref="conversation" class="conversation" role="log" aria-live="polite" aria-relevant="additions text" aria-label="Conversation messages">
        <div class="date-divider"><span>Today</span></div>
        <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
        <TypingIndicator v-if="isTyping" />
      </div>

      <ChatInput @send="sendMessage" />
    </section>
    <p class="page-note">A safe space to ask, understand, and choose with confidence.</p>
  </main>
</template>

<style scoped>
:global(*) { box-sizing: border-box; }
:global(body) { margin: 0; background: #f2f3ed; color: #18342d; font-family: ui-rounded, "Avenir Next", Avenir, "Segoe UI", sans-serif; }

.chat-page { min-height: calc(100vh - 58px); min-height: calc(100dvh - 58px); padding: 30px 18px 24px; background: radial-gradient(circle at 8% 12%, rgba(219, 235, 218, .8), transparent 28%), #f2f3ed; }
.chat-shell { width: min(100%, 820px); height: min(760px, calc(100vh - 134px)); height: min(760px, calc(100dvh - 134px)); min-height: 580px; margin: auto; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; border: 1px solid rgba(21, 65, 55, .12); border-radius: 28px; background: #fbfcf8; box-shadow: 0 24px 70px rgba(39, 72, 59, .12); }
.chat-header { display: flex; align-items: center; gap: 14px; padding: 20px 26px; color: #f8fff9; background: linear-gradient(120deg, #134f42, #236a55); }
.brand-mark { position: relative; width: 46px; height: 46px; flex: 0 0 46px; border-radius: 15px 15px 15px 5px; background: #a8d86d; transform: rotate(-8deg); }
.brand-mark span { position: absolute; width: 7px; height: 7px; top: 17px; border-radius: 50%; background: #165441; transform: rotate(8deg); }
.brand-mark span:first-child { left: 13px; }.brand-mark span:last-child { left: 26px; }
.header-copy { min-width: 0; }.eyebrow { margin: 0 0 3px; color: #bce193; font-size: 10px; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
h1 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(20px, 3vw, 25px); font-weight: 600; letter-spacing: -.02em; }
.presence { display: flex; align-items: center; gap: 6px; margin: 4px 0 0; color: rgba(248, 255, 249, .74); font-size: 12px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: #b5e476; box-shadow: 0 0 0 3px rgba(181, 228, 118, .15); }
.header-mark { display: flex; gap: 4px; align-items: center; margin-left: auto; padding: 10px; }.header-mark span { width: 4px; height: 4px; border-radius: 50%; background: #dff2db; }
.conversation { min-height: 0; overflow-x: hidden; overflow-y: auto; overscroll-behavior: contain; padding: 25px clamp(17px, 5vw, 58px); scroll-behavior: smooth; scrollbar-color: #aac6aa transparent; background: linear-gradient(rgba(251,252,248,.91), rgba(251,252,248,.91)), radial-gradient(#d9e7d7 1px, transparent 1px); background-size: auto, 20px 20px; }
.date-divider { display: flex; align-items: center; gap: 12px; margin: 0 auto 24px; color: #7d9185; font-size: 11px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }.date-divider::before, .date-divider::after { content: ''; height: 1px; flex: 1; background: #dce6dc; }.date-divider span { padding: 5px 10px; border-radius: 20px; background: #edf3ec; }
.page-note { margin: 15px auto 0; color: #789086; font-size: 12px; text-align: center; }
@media (max-width: 600px) { .chat-page { min-height: calc(100vh - 51px); min-height: calc(100dvh - 51px); padding: 0; }.chat-shell { height: calc(100vh - 51px); height: calc(100dvh - 51px); min-height: 0; border: 0; border-radius: 0; }.chat-header { padding: max(17px, env(safe-area-inset-top)) 18px 17px; }.conversation { padding: 20px 16px; }.page-note { display: none; } }
@media (prefers-reduced-motion: reduce) { .conversation { scroll-behavior: auto; } }
</style>
