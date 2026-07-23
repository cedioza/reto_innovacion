// Cliente HTTP base. Todos los componentes consumen la API a través de este
// módulo — nunca hacen fetch directo.

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!response.ok) {
    throw new Error(`Error HTTP ${response.status} en ${path}`)
  }
  return response.json()
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) =>
    request(path, { ...options, method: 'POST', body: JSON.stringify(body) }),
}

export function getHealth() {
  return api.get('/health')
}
