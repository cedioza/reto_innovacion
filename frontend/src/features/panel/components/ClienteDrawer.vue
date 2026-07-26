<script setup>
// Ficha de detalle de un cliente: perfil fusionado con origen del dato,
// funnel ofrecido/cotizado/solicitado y acceso a las conversaciones asociadas.
import { onMounted, onUnmounted, reactive } from 'vue'
import { getConversation } from '../../../shared/services/api'

const props = defineProps({
  ficha: {
    type: Object,
    default: null,
  },
  isLoading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['cerrar', 'reintentar'])

const ORIGEN_LABELS = {
  base: 'base',
  conversacion: 'conversación',
  declarado: 'declarado',
  sintetico: 'sintético',
}

const TIPO_OFERTA_LABELS = {
  proactivo: 'Proactivo',
  recomendacion: 'Recomendación',
}

// session_id -> { expandido, cargando, error, mensajes }
const transcripciones = reactive({})

function handleKeydown(event) {
  if (event.key === 'Escape') emit('cerrar')
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

function serieOProspecto(ficha) {
  if (!ficha) return ''
  if (ficha.serie) return ficha.serie
  const session = ficha.cliente_id || ''
  return `Prospecto — sesión ${session.slice(0, 8)}`
}

function origenLabel(origen) {
  return ORIGEN_LABELS[origen] || origen
}

function origenClase(origen) {
  return `chip-origen chip-origen-${origen}`
}

function tipoOfertaLabel(tipo) {
  return TIPO_OFERTA_LABELS[tipo] || tipo
}

function formatFecha(iso) {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleDateString('es-CO', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function formatHora(iso) {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })
}

function formatCOP(valor) {
  if (valor === null || valor === undefined) return '—'
  return `$${Number(valor).toLocaleString('es-CO')}`
}

function toggleTranscripcion(sessionId) {
  const estado = transcripciones[sessionId]
  if (estado) {
    estado.expandido = !estado.expandido
    if (estado.expandido && !estado.mensajes && !estado.cargando) {
      cargarTranscripcion(sessionId)
    }
    return
  }
  transcripciones[sessionId] = { expandido: true, cargando: false, error: null, mensajes: null }
  cargarTranscripcion(sessionId)
}

async function cargarTranscripcion(sessionId) {
  const estado = transcripciones[sessionId]
  estado.cargando = true
  estado.error = null
  try {
    const conversacion = await getConversation(sessionId)
    estado.mensajes = (conversacion.messages || []).filter((m) => m.type === 'text')
  } catch (err) {
    estado.error = 'No pudimos cargar la transcripción de esta conversación.'
  } finally {
    estado.cargando = false
  }
}

function handleBackdropClick() {
  emit('cerrar')
}
</script>

<template>
  <div class="drawer-backdrop" @click.self="handleBackdropClick">
    <aside class="drawer">
      <header class="drawer-header">
        <div class="drawer-header-info">
          <h2 class="drawer-title">{{ serieOProspecto(ficha) }}</h2>
          <span
            v-if="ficha"
            class="badge"
            :class="ficha.afiliado ? 'badge-afiliado' : 'badge-no-afiliado'"
          >
            {{ ficha.afiliado ? 'Afiliado (base)' : 'No afiliado (declarado)' }}
          </span>
        </div>
        <button type="button" class="close-btn" aria-label="Cerrar" @click="emit('cerrar')">
          ✕
        </button>
      </header>

      <div class="drawer-body">
        <p v-if="isLoading" class="state-text">Cargando ficha del cliente…</p>

        <div v-else-if="error" class="state-card">
          <p class="state-text">{{ error }}</p>
          <button type="button" class="retry-btn" @click="emit('reintentar')">Reintentar</button>
        </div>

        <div v-else-if="ficha">
          <section class="seccion">
            <h3 class="seccion-title">Perfil</h3>
            <ul v-if="ficha.perfil && ficha.perfil.length" class="perfil-list">
              <li v-for="item in ficha.perfil" :key="item.campo" class="perfil-item">
                <span class="perfil-campo">{{ item.campo }}</span>
                <span class="perfil-valor">{{ item.valor }}</span>
                <span :class="origenClase(item.origen)">{{ origenLabel(item.origen) }}</span>
              </li>
            </ul>
            <p v-else class="state-text">Sin datos de perfil.</p>
          </section>

          <section class="seccion">
            <h3 class="seccion-title">Funnel</h3>

            <div class="funnel-bloque">
              <h4 class="funnel-subtitle">Ofrecidos</h4>
              <ul v-if="ficha.ofertas && ficha.ofertas.length" class="funnel-list">
                <li v-for="(oferta, idx) in ficha.ofertas" :key="`oferta-${idx}`" class="funnel-item">
                  <span class="funnel-nombre">{{ oferta.product_name || oferta.product_id }}</span>
                  <span class="chip chip-tipo">{{ tipoOfertaLabel(oferta.tipo) }}</span>
                  <span class="funnel-fecha">{{ formatFecha(oferta.fecha) }}</span>
                </li>
              </ul>
              <p v-else class="state-text-sm">Sin ofertas registradas.</p>
            </div>

            <div class="funnel-bloque">
              <h4 class="funnel-subtitle">Cotizados</h4>
              <ul v-if="ficha.cotizaciones && ficha.cotizaciones.length" class="funnel-list">
                <li
                  v-for="(cotizacion, idx) in ficha.cotizaciones"
                  :key="`cotizacion-${idx}`"
                  class="funnel-item"
                >
                  <span class="funnel-nombre">
                    {{ cotizacion.product_name || cotizacion.product_id }}
                  </span>
                  <span class="funnel-prima">{{ formatCOP(cotizacion.monthly_premium) }}/mes</span>
                  <span class="funnel-fecha">{{ formatFecha(cotizacion.fecha) }}</span>
                </li>
              </ul>
              <p v-else class="state-text-sm">Sin cotizaciones registradas.</p>
            </div>

            <div class="funnel-bloque">
              <h4 class="funnel-subtitle">Solicitudes</h4>
              <ul v-if="ficha.solicitudes && ficha.solicitudes.length" class="funnel-list">
                <li
                  v-for="(solicitud, idx) in ficha.solicitudes"
                  :key="`solicitud-${idx}`"
                  class="funnel-item"
                >
                  <span class="funnel-nombre">
                    {{ solicitud.product_name || solicitud.product_id }}
                  </span>
                  <span
                    class="chip"
                    :class="solicitud.comprado ? 'chip-comprado' : 'chip-estado'"
                  >
                    {{ solicitud.comprado ? 'Comprado' : solicitud.estado }}
                  </span>
                  <span class="funnel-email">{{ solicitud.email || '—' }}</span>
                  <span class="funnel-fecha">{{ formatFecha(solicitud.fecha) }}</span>
                </li>
              </ul>
              <p v-else class="state-text-sm">Sin solicitudes registradas.</p>
            </div>
          </section>

          <section class="seccion">
            <h3 class="seccion-title">Conversaciones</h3>
            <ul v-if="ficha.conversaciones && ficha.conversaciones.length" class="conversaciones-list">
              <li
                v-for="conversacion in ficha.conversaciones"
                :key="conversacion.session_id"
                class="conversacion-item"
              >
                <div class="conversacion-fila">
                  <span class="conversacion-canal">{{ conversacion.canal || 'web' }}</span>
                  <span class="conversacion-estado">{{ conversacion.estado }}</span>
                  <span class="conversacion-mensajes">{{ conversacion.mensajes }} mensajes</span>
                  <span class="conversacion-fecha">{{ formatFecha(conversacion.ultima_actividad) }}</span>
                  <button
                    type="button"
                    class="link-btn"
                    @click="toggleTranscripcion(conversacion.session_id)"
                  >
                    {{
                      transcripciones[conversacion.session_id]?.expandido
                        ? 'Ocultar transcripción'
                        : 'Ver transcripción'
                    }}
                  </button>
                </div>

                <div
                  v-if="transcripciones[conversacion.session_id]?.expandido"
                  class="transcripcion"
                >
                  <p v-if="transcripciones[conversacion.session_id].cargando" class="state-text-sm">
                    Cargando transcripción…
                  </p>
                  <p
                    v-else-if="transcripciones[conversacion.session_id].error"
                    class="state-text-sm error-text"
                  >
                    {{ transcripciones[conversacion.session_id].error }}
                  </p>
                  <ul
                    v-else-if="transcripciones[conversacion.session_id].mensajes?.length"
                    class="mensajes-list"
                  >
                    <li
                      v-for="(mensaje, idx) in transcripciones[conversacion.session_id].mensajes"
                      :key="idx"
                      class="mensaje-item"
                    >
                      <span class="mensaje-rol">
                        {{ mensaje.role === 'assistant' ? 'Asistente' : 'Cliente' }}
                      </span>
                      <span class="mensaje-contenido">{{ mensaje.content }}</span>
                      <span class="mensaje-hora">{{ formatHora(mensaje.timestamp) }}</span>
                    </li>
                  </ul>
                  <p v-else class="state-text-sm">Sin mensajes de texto en esta conversación.</p>
                </div>
              </li>
            </ul>
            <p v-else class="state-text">Sin conversaciones registradas.</p>
          </section>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(31, 42, 36, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 50;
}

.drawer {
  width: 100%;
  max-width: 460px;
  height: 100%;
  background: #fff;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--chat-border);
}

.drawer-header-info {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.drawer-title {
  margin: 0;
  font-size: 1.1rem;
  color: var(--chat-text);
}

.close-btn {
  border: none;
  background: transparent;
  color: var(--chat-text-muted);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
}

.close-btn:hover {
  color: var(--chat-text);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.1rem 1.25rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.4rem;
}

.state-text {
  margin: 0;
  color: var(--chat-text-muted);
  font-size: 0.95rem;
}

.state-text-sm {
  margin: 0;
  color: var(--chat-text-muted);
  font-size: 0.8rem;
}

.error-text {
  color: #b3261e;
}

.state-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.6rem;
}

.retry-btn {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--chat-green);
  background: transparent;
  color: var(--chat-green-dark);
  font-weight: 700;
  cursor: pointer;
}

.badge {
  display: inline-block;
  width: fit-content;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
}

.badge-afiliado {
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
}

.badge-no-afiliado {
  background: #f0f0f0;
  color: var(--chat-text-muted);
}

.seccion {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.seccion-title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--chat-green-dark);
}

.perfil-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.perfil-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.85rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--chat-border);
}

.perfil-campo {
  color: var(--chat-text-muted);
  min-width: 8rem;
}

.perfil-valor {
  color: var(--chat-text);
  font-weight: 600;
  flex: 1;
}

.chip-origen {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
}

.chip-origen-base {
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
}

.chip-origen-conversacion {
  background: #e4edfb;
  color: #1a4b8c;
}

.chip-origen-declarado {
  background: #f0f0f0;
  color: var(--chat-text-muted);
}

.chip-origen-sintetico {
  background: #fdf3d6;
  color: #8a6d1f;
}

.funnel-bloque {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}

.funnel-subtitle {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--chat-text);
}

.funnel-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.funnel-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.82rem;
  color: var(--chat-text);
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--chat-border);
}

.funnel-nombre {
  font-weight: 600;
  flex: 1;
  min-width: 8rem;
}

.funnel-prima,
.funnel-fecha,
.funnel-email {
  color: var(--chat-text-muted);
  font-size: 0.78rem;
}

.chip {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
}

.chip-tipo {
  background: var(--chat-green-light);
  color: var(--chat-green-dark);
}

.chip-estado {
  background: #f0f0f0;
  color: var(--chat-text-muted);
}

.chip-comprado {
  background: #d9f2e6;
  color: var(--chat-green-dark);
}

.conversaciones-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.conversacion-item {
  border: 1px solid var(--chat-border);
  border-radius: 0.6rem;
  padding: 0.55rem 0.7rem;
}

.conversacion-fila {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-size: 0.8rem;
  color: var(--chat-text);
}

.conversacion-canal {
  text-transform: capitalize;
  font-weight: 600;
}

.conversacion-estado,
.conversacion-mensajes,
.conversacion-fecha {
  color: var(--chat-text-muted);
}

.link-btn {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--chat-green-dark);
  font-weight: 700;
  font-size: 0.78rem;
  cursor: pointer;
  padding: 0;
}

.transcripcion {
  margin-top: 0.6rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--chat-border);
}

.mensajes-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 220px;
  overflow-y: auto;
}

.mensaje-item {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  font-size: 0.8rem;
  padding: 0.3rem 0.5rem;
  border-radius: 0.5rem;
  background: var(--chat-bg);
}

.mensaje-rol {
  font-weight: 700;
  color: var(--chat-green-dark);
  font-size: 0.72rem;
}

.mensaje-contenido {
  color: var(--chat-text);
}

.mensaje-hora {
  align-self: flex-end;
  color: var(--chat-text-muted);
  font-size: 0.68rem;
}
</style>
