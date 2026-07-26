<script setup>
// Página pública de la "aseguradora simulada". Se abre desde el link del
// correo de comprobante (`/aseguradora/{token}`), sin sesión del chat: todo
// el estado sale del token de la URL, cero localStorage/sesión (debe
// funcionar en incógnito).
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { finalizeHandoff, getHandoff } from '../../shared/services/api'

const route = useRoute()
const token = route.params.token

// 'loading' | 'summary' | 'success' | 'not-found' | 'error'
const status = ref('loading')
const handoff = ref(null)
const finalizing = ref(false)
const finalizeFailed = ref(false)

function formatAmount(amount) {
  return Number(amount).toLocaleString('es-CO')
}

async function loadHandoff() {
  status.value = 'loading'
  finalizeFailed.value = false
  try {
    const data = await getHandoff(token)
    handoff.value = data
    status.value = data.state === 'finalizada_demo' ? 'success' : 'summary'
  } catch (err) {
    handoff.value = null
    status.value = err.status === 404 ? 'not-found' : 'error'
  }
}

async function handleFinalize() {
  finalizing.value = true
  finalizeFailed.value = false
  try {
    const data = await finalizeHandoff(token)
    handoff.value = data
    status.value = 'success'
  } catch {
    finalizeFailed.value = true
  } finally {
    finalizing.value = false
  }
}

onMounted(loadHandoff)
</script>

<template>
  <div class="insurer-page">
    <div class="demo-banner" role="status">
      Entorno de demostración — aquí entraría la pasarela real de la aseguradora
    </div>

    <main class="content">
      <div v-if="status === 'loading'" class="state-card">
        <div class="spinner" aria-hidden="true"></div>
        <p>Cargando tu solicitud…</p>
      </div>

      <div v-else-if="status === 'not-found'" class="state-card">
        <p class="state-title">No encontramos tu solicitud</p>
        <p class="state-text">Puede haber expirado. Vuelve al chat para retomarla.</p>
        <router-link to="/" class="link-btn">Volver al chat</router-link>
      </div>

      <div v-else-if="status === 'error'" class="state-card">
        <p class="state-title">No pudimos cargar tu solicitud</p>
        <p class="state-text">Revisa tu conexión e inténtalo de nuevo.</p>
        <button type="button" class="primary-btn" @click="loadHandoff">Reintentar</button>
      </div>

      <div v-else-if="status === 'success'" class="state-card success-card">
        <p class="success-emoji" aria-hidden="true">🎉</p>
        <p class="state-title">Tu póliza quedó activa (simulación)</p>
        <p class="state-text" v-if="handoff">
          {{ handoff.product_name }} con {{ handoff.insurer_name || 'la aseguradora' }}.
        </p>
        <router-link to="/" class="link-btn">Volver al chat</router-link>
      </div>

      <div v-else-if="status === 'summary' && handoff" class="summary">
        <header class="insurer-header">
          <p class="insurer-name">{{ handoff.insurer_name || 'Aseguradora' }}</p>
          <p class="product-name">{{ handoff.product_name }}</p>
        </header>

        <div class="premium-block">
          <p class="premium-monthly">
            {{ formatAmount(handoff.monthly_premium) }}
            <span class="unit">{{ handoff.currency }}/mes</span>
          </p>
          <p v-if="handoff.annual_premium" class="premium-annual">
            {{ formatAmount(handoff.annual_premium) }} {{ handoff.currency }}/año
          </p>
        </div>

        <div v-if="handoff.coverage_details?.length" class="section">
          <p class="section-title">Coberturas</p>
          <ul class="coverage-list">
            <li v-for="(coverage, index) in handoff.coverage_details" :key="index">
              {{ coverage }}
            </li>
          </ul>
        </div>

        <details v-if="handoff.exclusions?.length" class="collapsible">
          <summary>Exclusiones</summary>
          <ul class="exclusion-list">
            <li v-for="(exclusion, index) in handoff.exclusions" :key="index">
              {{ exclusion }}
            </li>
          </ul>
        </details>

        <p v-if="finalizeFailed" class="finalize-error">
          No pudimos continuar. Inténtalo de nuevo.
        </p>

        <button
          type="button"
          class="primary-btn continue-btn"
          :disabled="finalizing"
          @click="handleFinalize"
        >
          {{ finalizing ? 'Procesando…' : 'Continuar al pago' }}
        </button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.insurer-page {
  min-height: 100vh;
  background: var(--chat-bg, #f4f6f5);
  color: var(--chat-text, #1f2a24);
  display: flex;
  flex-direction: column;
}

.demo-banner {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--chat-green-dark, #005c3a);
  color: #fff;
  text-align: center;
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.3;
}

.content {
  flex: 1;
  display: flex;
  justify-content: center;
  padding: 1rem;
}

.state-card {
  width: 100%;
  max-width: 24rem;
  margin-top: 2rem;
  background: #fff;
  border: 1px solid var(--chat-border, #e0e5e2);
  border-radius: 1rem;
  padding: 1.5rem 1.25rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
}

.success-card {
  margin-top: 3rem;
}

.success-emoji {
  font-size: 2.5rem;
  margin: 0;
}

.state-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--chat-green-dark, #005c3a);
}

.state-text {
  margin: 0;
  font-size: 0.9rem;
  color: var(--chat-text-muted, #6b7570);
}

.spinner {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  border: 3px solid var(--chat-border, #e0e5e2);
  border-top-color: var(--chat-green, #00754a);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.link-btn,
.primary-btn {
  margin-top: 0.4rem;
  padding: 0.6rem 1.25rem;
  border-radius: 0.6rem;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  text-decoration: none;
  border: none;
}

.link-btn {
  background: transparent;
  color: var(--chat-green-dark, #005c3a);
  border: 1px solid var(--chat-green, #00754a);
}

.primary-btn {
  background: var(--chat-green, #00754a);
  color: #fff;
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.summary {
  width: 100%;
  max-width: 24rem;
  margin-top: 1rem;
  background: #fff;
  border: 1px solid var(--chat-border, #e0e5e2);
  border-radius: 1rem;
  padding: 1.25rem;
  height: fit-content;
}

.insurer-header {
  margin-bottom: 0.8rem;
  padding-bottom: 0.6rem;
  border-bottom: 1px solid var(--chat-border, #e0e5e2);
}

.insurer-name {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--chat-green, #00754a);
}

.product-name {
  margin: 0.15rem 0 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--chat-text, #1f2a24);
}

.premium-block {
  margin-bottom: 0.8rem;
}

.premium-monthly {
  margin: 0;
  color: var(--chat-green-dark, #005c3a);
  font-size: 1.8rem;
  font-weight: 800;
  line-height: 1.2;
}

.premium-monthly .unit {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--chat-text-muted, #6b7570);
}

.premium-annual {
  margin: 0.2rem 0 0;
  color: var(--chat-text-muted, #6b7570);
  font-size: 0.85rem;
}

.section {
  margin: 0.8rem 0;
}

.section-title {
  margin: 0 0 0.3rem;
  font-size: 0.85rem;
  font-weight: 700;
}

.coverage-list,
.exclusion-list {
  list-style: disc;
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
}

.collapsible {
  margin: 0.6rem 0;
  font-size: 0.85rem;
}

.collapsible summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--chat-green-dark, #005c3a);
}

.collapsible[open] summary {
  margin-bottom: 0.3rem;
}

.finalize-error {
  margin: 0.6rem 0 0;
  color: #b3261e;
  font-size: 0.8rem;
}

.continue-btn {
  width: 100%;
  margin-top: 1rem;
  padding: 0.75rem;
  font-size: 1rem;
}
</style>
