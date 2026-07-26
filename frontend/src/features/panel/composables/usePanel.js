import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { dispararOferta, getPanelCohortes } from '../../../shared/services/api'

const SESSION_STORAGE_KEY = 'chat_session_id'

const ERROR_TEXT = 'No pudimos cargar el panel de cohortes. Inténtalo de nuevo en un momento.'
const DISPARO_ERROR_TEXT = 'No pudimos disparar la oferta. Inténtalo de nuevo.'

export function usePanel() {
  const router = useRouter()

  const cohortes = ref([])
  const fuente = ref(null)
  const isLoading = ref(true)
  const error = ref(null)
  const disparandoSerie = ref(null)
  const errorDisparo = ref(null)

  async function cargar() {
    isLoading.value = true
    error.value = null
    try {
      const data = await getPanelCohortes()
      cohortes.value = data.cohortes ?? []
      fuente.value = data.fuente ?? null
    } catch (err) {
      error.value = ERROR_TEXT
    } finally {
      isLoading.value = false
    }
  }

  function reintentar() {
    cargar()
  }

  async function disparar(cohorteId, serie) {
    errorDisparo.value = null
    disparandoSerie.value = serie
    try {
      const respuesta = await dispararOferta(cohorteId, serie)
      localStorage.setItem(SESSION_STORAGE_KEY, respuesta.session_id)
      router.push('/')
    } catch (err) {
      errorDisparo.value = DISPARO_ERROR_TEXT
    } finally {
      disparandoSerie.value = null
    }
  }

  cargar()

  return {
    cohortes,
    fuente,
    isLoading,
    error,
    disparandoSerie,
    errorDisparo,
    cargar,
    reintentar,
    disparar,
  }
}
