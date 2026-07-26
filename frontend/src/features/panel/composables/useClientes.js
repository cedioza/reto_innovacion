import { ref } from 'vue'
import { getPanelClientes } from '../../../shared/services/api'

const ERROR_TEXT = 'No pudimos cargar la lista de clientes. Inténtalo de nuevo en un momento.'
const DEBOUNCE_MS = 300

export function useClientes() {
  const clientes = ref([])
  const total = ref(0)
  const isLoading = ref(true)
  const error = ref(null)
  const q = ref('')

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

  cargar()

  return {
    clientes,
    total,
    isLoading,
    error,
    q,
    cargar,
    reintentar,
    buscar,
  }
}
