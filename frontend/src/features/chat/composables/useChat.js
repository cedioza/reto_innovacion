import { ref } from 'vue'

let nextId = 1

function mockMessage(from, text, minutesAgo = 0) {
  const timestamp = new Date(Date.now() - minutesAgo * 60_000)
  return { id: nextId++, from, text, timestamp }
}

const MOCK_BOT_REPLIES = [
  'Cuéntame un poco más — ¿tienes hijos o alguna mascota en casa?',
  'Con eso ya tengo una idea más clara de lo que necesitas. Dame un momento.',
  'Entiendo. Puedo mostrarte un par de opciones que se ajustan a tu perfil.',
]

export function useChat() {
  const messages = ref([
    mockMessage('bot', 'Hola 👋 Soy tu asistente de seguros Colsubsidio. Contame qué te gustaría proteger y te ayudo a encontrar el seguro correcto.', 2),
    mockMessage('user', 'Hola, quiero un seguro para mi carro', 1),
    mockMessage('bot', 'Perfecto, vamos a armar tu perfil para recomendarte lo más adecuado.', 1),
  ])
  const isTyping = ref(false)

  function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed) return

    messages.value.push(mockMessage('user', trimmed))
    isTyping.value = true

    const delay = 900 + Math.random() * 600
    setTimeout(() => {
      const reply = MOCK_BOT_REPLIES[Math.floor(Math.random() * MOCK_BOT_REPLIES.length)]
      messages.value.push(mockMessage('bot', reply))
      isTyping.value = false
    }, delay)
  }

  return { messages, isTyping, sendMessage }
}
