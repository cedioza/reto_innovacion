<script setup>
import { onMounted, ref } from 'vue'
import { getHealth } from '../../shared/services/api'

const backendConectado = ref(null) // null = verificando, true/false = resultado

onMounted(async () => {
  try {
    const data = await getHealth()
    backendConectado.value = data.status === 'ok'
  } catch {
    backendConectado.value = false
  }
})
</script>

<template>
  <section>
    <h1>Chat</h1>
    <p>Vista placeholder del chat.</p>
    <p v-if="backendConectado === null">Backend: ⏳ verificando…</p>
    <p v-else-if="backendConectado">Backend: ✅ conectado</p>
    <p v-else>Backend: ❌ sin conexión</p>
  </section>
</template>
