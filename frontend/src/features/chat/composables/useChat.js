import { ref } from 'vue'
import { createConversation, getConversation, postMessage } from '../../../shared/services/api'

const SESSION_STORAGE_KEY = 'chat_session_id'

let nextId = 1

const WELCOME_TEXT =
  'Hola 👋 Soy tu asistente de seguros Colsubsidio. Contame qué te gustaría proteger y te ayudo a encontrar el seguro correcto.'

const ERROR_TEXT = 'Ups, tuve un problema para responderte. Inténtalo de nuevo en un momento 🙏'

function makeMessage(from, text, timestamp = new Date(), extra = {}) {
  return { id: nextId++, from, text, type: 'text', payload: null, timestamp, ...extra }
}

function mapSessionMessages(sessionMessages) {
  return sessionMessages.map((message) =>
    makeMessage(message.role === 'assistant' ? 'bot' : 'user', message.content, null, {
      type: message.type ?? 'text',
      payload: message.payload ?? null,
    }),
  )
}

export function useChat() {
  // Prefijo local: burbujas que no viven en `session.messages` del server
  // (bienvenida, y cualquier historial "congelado" tras un reset por 404).
  // Toda reconstrucción parte de este prefijo + lo que devuelva la sesión activa.
  let prefix = [makeMessage('bot', WELCOME_TEXT)]
  const messages = ref([...prefix])
  const isTyping = ref(false)
  let sessionId = null

  const storedSessionId = localStorage.getItem(SESSION_STORAGE_KEY)
  let hydrationPromise = null

  if (storedSessionId) {
    hydrationPromise = getConversation(storedSessionId)
      .then((session) => {
        sessionId = storedSessionId
        messages.value = [...prefix, ...mapSessionMessages(session.messages)]
      })
      .catch(() => {
        localStorage.removeItem(SESSION_STORAGE_KEY)
      })
      .finally(() => {
        hydrationPromise = null
      })
  }

  function persistSessionId(id) {
    sessionId = id
    localStorage.setItem(SESSION_STORAGE_KEY, id)
  }

  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed) return

    // Si hay una rehidratación pendiente, se espera antes de continuar para no
    // pisar el session_id recuperado ni el historial ya reconstruido.
    if (hydrationPromise) {
      await hydrationPromise
    }

    const previousMessages = messages.value
    messages.value = [...previousMessages, makeMessage('user', trimmed)]
    isTyping.value = true

    try {
      if (!sessionId) {
        const conversation = await createConversation()
        persistSessionId(conversation.session_id)
      }

      let session

      try {
        session = await postMessage(sessionId, trimmed)
      } catch (err) {
        if (err.status === 404) {
          // Backend reiniciado a mitad de conversación (sesión en memoria perdida):
          // se congela como prefijo local todo lo pintado EXCEPTO la burbuja
          // optimista del mensaje que se va a reenviar (esa ya viene incluida en
          // `session.messages` de la sesión nueva) y se reenvía una única vez.
          localStorage.removeItem(SESSION_STORAGE_KEY)
          prefix = messages.value.slice(0, -1)
          const conversation = await createConversation()
          persistSessionId(conversation.session_id)
          session = await postMessage(sessionId, trimmed)
        } else {
          throw err
        }
      }

      const previousTimestamps = messages.value.map((message) => message.timestamp)
      const now = new Date()

      messages.value = [
        ...prefix,
        ...session.messages.map((message, index) =>
          makeMessage(
            message.role === 'assistant' ? 'bot' : 'user',
            message.content,
            previousTimestamps[prefix.length + index] ?? now,
            {
              type: message.type ?? 'text',
              payload: message.payload ?? null,
            },
          ),
        ),
      ]
    } catch (err) {
      messages.value = [...messages.value, makeMessage('bot', ERROR_TEXT, new Date(), { isError: true })]
    } finally {
      isTyping.value = false
    }
  }

  return { messages, isTyping, sendMessage }
}
