# Frontend — Reglas de arquitectura

Vue 3 + Vite con arquitectura por features.

## Estructura

- `src/features/<feature>/` — cada feature es autocontenida: sus vistas (`*View.vue`), `components/` y `composables/` viven dentro de su carpeta. Una feature no importa de otra feature; si dos features necesitan lo mismo, se mueve a `shared/`.
- `src/shared/` — solo lo reutilizado por 2+ features: `components/`, `composables/` y `services/`.
- `src/stores/` — estado global con Pinia (`defineStore`). Estado que solo usa una feature puede vivir como composable dentro de la feature.
- `src/router/index.js` — todas las rutas se registran aquí, apuntando a vistas de features.

## Regla de acceso a datos (obligatoria)

- Los componentes NUNCA hacen `fetch`/HTTP directo. Toda llamada a la API pasa por `src/shared/services/` (cliente base: `api.js`).
- Nuevo recurso de API = nueva función exportada en un servicio de `shared/services/` (patrón: `getHealth()` en `api.js`); los componentes/stores importan esa función.

## Convenciones

- Variables de entorno solo con prefijo `VITE_`, leídas con `import.meta.env`, y documentadas en `.env.example`. La URL del backend viene únicamente de `VITE_API_URL`.
- Componentes con `<script setup>` y Composition API.
- Nueva feature = carpeta en `features/` + ruta en `router/index.js`; nada de vistas sueltas fuera de features.
