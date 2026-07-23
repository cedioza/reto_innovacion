# features/

Cada feature es una carpeta autocontenida con sus propios `components/`, `composables/` y vistas (`*View.vue`). Lo que se reutiliza entre features va en `src/shared/`.

Convención importante: los componentes NUNCA hacen `fetch` directo — toda llamada HTTP pasa por `src/shared/services/` (por ejemplo `api.js`).
