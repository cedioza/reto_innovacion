import { ref } from 'vue'
import { getPanelClientes, getPanelCliente } from '../../../shared/services/api'

const ERROR_TEXT = 'No pudimos cargar la lista de clientes. Inténtalo de nuevo en un momento.'
const FICHA_NOT_FOUND_TEXT = 'Cliente no encontrado.'
const FICHA_ERROR_TEXT = 'No pudimos cargar la ficha del cliente. Inténtalo de nuevo en un momento.'
const DEBOUNCE_MS = 300

export function useClientes({ autoLoad = true } = {}) {
  const clientes = ref([])
  const total = ref(0)
  const isLoading = ref(true)
  const error = ref(null)
  const q = ref('')

  const ficha = ref(null)
  const isLoadingFicha = ref(false)
  const errorFicha = ref(null)
  let ultimoClienteId = null

  let debounceTimer = null

  async function cargar() {
    isLoading.value = true
    error.value = null
    try {
      const data = await getPanelClientes(q.value)
      clientes.value = data.clientes ?? []
      total.value = data.total ?? 0
    } catch (err) {
      error.value = ERROR_TEXT
    } finally {
      isLoading.value = false
    }
  }

  function reintentar() {
    cargar()
  }

  function buscar(nuevoQ) {
    q.value = nuevoQ
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      cargar()
    }, DEBOUNCE_MS)
  }

  async function abrirFicha(clienteId) {
    ultimoClienteId = clienteId
    isLoadingFicha.value = true
    errorFicha.value = null
    ficha.value = null
    try {
      ficha.value = await getPanelCliente(clienteId)
    } catch (err) {
      errorFicha.value = err.status === 404 ? FICHA_NOT_FOUND_TEXT : FICHA_ERROR_TEXT
    } finally {
      isLoadingFicha.value = false
    }
  }

  function reintentarFicha() {
    if (ultimoClienteId) abrirFicha(ultimoClienteId)
  }

  function cerrarFicha() {
    ficha.value = null
    isLoadingFicha.value = false
    errorFicha.value = null
    ultimoClienteId = null
  }

  if (autoLoad) cargar()

  return {
    clientes,
    total,
    isLoading,
    error,
    q,
    cargar,
    reintentar,
    buscar,
    ficha,
    isLoadingFicha,
    errorFicha,
    abrirFicha,
    reintentarFicha,
    cerrarFicha,
  }
}
