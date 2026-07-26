import { ref } from 'vue'
import { getPanelMetricas } from '../../../shared/services/api'

const ERROR_TEXT = 'No pudimos cargar el funnel de ventas. Inténtalo de nuevo en un momento.'

export function useFunnel() {
  const metricas = ref(null)
  const isLoading = ref(true)
  const error = ref(null)

  async function cargar() {
    isLoading.value = true
    error.value = null
    try {
      metricas.value = await getPanelMetricas()
    } catch (err) {
      error.value = ERROR_TEXT
    } finally {
      isLoading.value = false
    }
  }

  function reintentar() {
    cargar()
  }

  cargar()

  return {
    metricas,
    isLoading,
    error,
    cargar,
    reintentar,
  }
}
