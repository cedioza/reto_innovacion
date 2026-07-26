// Cliente HTTP base. Todos los componentes consumen la API a través de este
// módulo — nunca hacen fetch directo.

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const DEFAULT_TIMEOUT_MS = 60000

// Convención: todos los paths llevan el prefijo /api/v1 explícito (contrato del backend)
async function request(path, options = {}) {
  const { timeout = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...fetchOptions.headers },
      ...fetchOptions,
      signal: controller.signal,
    })
    if (!response.ok) {
      const error = new Error(`Error HTTP ${response.status} en ${path}`)
      error.status = response.status
      throw error
    }
    return await response.json()
  } catch (err) {
    if (err.name === 'AbortError') {
      const timeoutError = new Error(`Timeout tras ${timeout}ms en ${path}`)
      timeoutError.isTimeout = true
      throw timeoutError
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) =>
    request(path, { ...options, method: 'POST', body: JSON.stringify(body) }),
}

export function getHealth() {
  return api.get('/api/v1/health')
}

export function createConversation() {
  return api.post('/api/v1/conversations', {})
}

export function getConversation(sessionId) {
  return api.get(`/api/v1/conversations/${sessionId}`)
}

export function postMessage(sessionId, content) {
  return api.post(`/api/v1/conversations/${sessionId}/message`, { content })
}

export function postAdjustments(sessionId, adjustments) {
  return api.post(`/api/v1/conversations/${sessionId}/adjustments`, { adjustments })
}

export function postAccept(sessionId) {
  return api.post(`/api/v1/conversations/${sessionId}/accept`, {})
}

export function postConsent(sessionId, email) {
  return api.post(`/api/v1/conversations/${sessionId}/consent`, { consent_given: true, email })
}

export function getHandoff(token) {
  return api.get(`/api/v1/handoff/${token}`)
}

export function finalizeHandoff(token) {
  return api.post(`/api/v1/handoff/${token}/finalize`)
}

export function getPanelCohortes() {
  return api.get('/api/v1/panel/cohortes')
}

export function dispararOferta(cohorteId, serie) {
  return api.post(`/api/v1/panel/cohortes/${cohorteId}/disparar`, { serie })
}

export function getPanelMetricas() {
  return api.get('/api/v1/panel/metricas')
}
