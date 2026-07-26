<script setup>
import { useClientes } from '../composables/useClientes'

const { clientes, total, isLoading, error, q, reintentar, buscar } = useClientes()

const emit = defineEmits(['ver-cliente'])

function handleInput(event) {
  buscar(event.target.value)
}

function serieOProspecto(cliente) {
  if (cliente.serie) return cliente.serie
  const session = cliente.cliente_id || ''
  return `Prospecto — ${session.slice(0, 8)}`
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

function verCliente(cliente) {
  emit('ver-cliente', cliente.cliente_id)
}
</script>

<template>
  <section class="clientes-tab">
    <div class="buscador">
      <input
        type="search"
        class="buscador-input"
        placeholder="Buscar por SERIE, correo o nombre"
        :value="q"
        @input="handleInput"
      />
    </div>

    <p v-if="isLoading" class="state-text">Cargando clientes…</p>

    <div v-else-if="error" class="state-card">
      <p class="state-text">{{ error }}</p>
      <button type="button" class="retry-btn" @click="reintentar">Reintentar</button>
    </div>

    <div v-else>
      <p v-if="!clientes.length" class="state-text">Sin resultados.</p>

      <div v-else class="tabla-wrapper">
        <table class="clientes-table">
          <thead>
            <tr>
              <th>SERIE</th>
              <th>Afiliado</th>
              <th>Correo</th>
              <th>Conversaciones</th>
              <th>Solicitudes</th>
              <th>Último estado</th>
              <th>Última actividad</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="cliente in clientes"
              :key="cliente.cliente_id"
              class="cliente-row"
              @click="verCliente(cliente)"
            >
              <td>{{ serieOProspecto(cliente) }}</td>
              <td>
                <span class="badge" :class="cliente.afiliado ? 'badge-afiliado' : 'badge-no-afiliado'">
                  {{ cliente.afiliado ? 'Afiliado' : 'No afiliado' }}
                </span>
              </td>
              <td>{{ cliente.email || '—' }}</td>
              <td>{{ cliente.conversaciones }}</td>
              <td>{{ cliente.solicitudes }}</td>
              <td>{{ cliente.ultimo_estado || '—' }}</td>
              <td>{{ formatFecha(cliente.ultima_actividad) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="clientes.length" class="total-text">{{ total }} cliente(s) en total</p>
    </div>
  </section>
</template>

<style scoped>
.clientes-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.buscador-input {
  width: 100%;
  padding: 0.6rem 0.9rem;
  border-radius: 0.6rem;
  border: 1px solid var(--chat-border);
  font-size: 0.9rem;
  color: var(--chat-text);
  box-sizing: border-box;
}

.buscador-input:focus {
  outline: none;
  border-color: var(--chat-green);
}

.state-text {
  margin: 0;
  color: var(--chat-text-muted);
  font-size: 0.95rem;
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

.tabla-wrapper {
  overflow-x: auto;
  border: 1px solid var(--chat-border);
  border-radius: 0.9rem;
  background: #fff;
}

.clientes-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.clientes-table thead th {
  text-align: left;
  padding: 0.65rem 0.85rem;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--chat-green-dark);
  background: var(--chat-green-light);
  white-space: nowrap;
}

.cliente-row {
  cursor: pointer;
  border-top: 1px solid var(--chat-border);
}

.cliente-row:hover {
  background: var(--chat-bg);
}

.cliente-row td {
  padding: 0.65rem 0.85rem;
  color: var(--chat-text);
  white-space: nowrap;
}

.badge {
  display: inline-block;
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

.total-text {
  margin: 0;
  font-size: 0.8rem;
  color: var(--chat-text-muted);
}
</style>
