---
description: Genera un plan de implementación por fases (con checkpoints y commits sugeridos) bajo .claude/analysis/plans/ — solo análisis, sin tocar código. Cada fase declara qué proyecto toca (backend, frontend o ambos).
argument-hint: <qué planear, ej. "endpoint de mensajes y vista de chat que lo consume">
allowed-tools: Read, Glob, Grep, Write, Bash, PowerShell, Agent
---

# Generate Implementation Plan (Reto Innovación — monorepo)

Produce un plan de implementación por fases y guárdalo bajo `.claude/analysis/plans/`.
El plan es **análisis + staging solamente** — no se escribe código de producción al
generarlo. La ejecución ocurre después, fase por fase, con parada obligatoria y nombre
de commit sugerido en cada frontera de fase.

Este monorepo tiene DOS proyectos: `backend/` (FastAPI) y `frontend/` (Vue 3 + Vite).
**Cada fase del plan declara qué proyecto toca** — `backend`, `frontend` o `ambos` — y
eso determina qué agentes y verificaciones usa la ejecución.

## Instrucciones

1. Parsea los argumentos: `$ARGUMENTS` (qué planear). Si está vacío, pregunta al
   usuario qué feature/cambio planear antes de continuar.

### Paso 1 — Análisis a fondo del proyecto (OBLIGATORIO, no saltar)

Investiga antes de escribir una sola línea del plan. Lee el código real, no asumas:

- Determina el **alcance por proyecto**: ¿lo pedido toca solo el backend, solo el
  frontend, o ambos? Un feature típico full-stack toca ambos (endpoint + vista que
  lo consume).
- Backend: lee **completos** los módulos afectados bajo `backend/app/` (`api/routes/`,
  `services/`, `repositories/`, `models/`, `schemas/`, `helpers/`, `core/`) y rastrea
  **todos los callers** de lo que pienses cambiar.
- Frontend: lee las features afectadas bajo `frontend/src/features/`, los servicios de
  `frontend/src/shared/services/` (cliente base `api.js`), `router/index.js` y
  `stores/` si aplica.
- Lee las referencias que gobiernan este repo:
  - [CLAUDE.md](CLAUDE.md) — reglas generales: contrato HTTP/JSON entre front y back
    (`VITE_API_URL` / `FRONTEND_URL`), config solo por env vars, stack mínimo.
  - [backend/CLAUDE.md](backend/CLAUDE.md) — capas obligatorias
    `api → services → repositories → models` y sus convenciones.
  - [frontend/CLAUDE.md](frontend/CLAUDE.md) — arquitectura por features, HTTP solo
    vía `shared/services/`, env vars `VITE_*`.
  - [.claude/rules/commit-standards.md](.claude/rules/commit-standards.md) — los
    commits sugeridos DEBEN cumplirlo (el hook commit-msg los bloquea si no).
- Revisa `.claude/analysis/plans/` por planes previos sobre el mismo tema y construye
  sobre ellos (cítalos).
- Identifica el radio de impacto: routers, schemas, services, repositories (backend);
  features, servicios compartidos, rutas del router, stores (frontend); `.env.example`
  de cada proyecto; tests del backend.
- Surfacea **decisiones abiertas** (de producto o técnicas) que bloqueen la
  implementación, y **riesgos** propios de este repo: romper el contrato HTTP entre
  front y back (shape de respuesta, rutas, status codes), hardcodear URLs/puertos,
  agregar dependencias innecesarias (es un hackathon), y desalinear los `.env.example`.
- Para cambios amplios, delega la amplitud al agente `Explore` o `Plan` para mapear
  archivos y convenciones, y sintetiza — pero el autor del plan es dueño de las
  conclusiones.

Si el análisis revela una decisión bloqueante que no puedas resolver desde el código,
lístala en la sección **Decisiones pendientes** del plan en vez de adivinar.

### Paso 2 — Escribir el archivo del plan

- **Ubicación**: `.claude/analysis/plans/`
- **Nombre**: `YYYYMMDD-<slug-en-kebab-case>.plan.md` (fecha de hoy; agrega `-HHMMSS`
  solo si ya existe un archivo del mismo día con ese slug).
- **Idioma**: español.
- Usa enlaces clicables (`[archivo.py:42](ruta-relativa-a-raiz#L42)`) para cada
  referencia de código, resueltos desde la raíz del repo.

Sigue esta estructura:

```markdown
# Plan — <título> · (por fases, checkpoint por fase)

> **Fecha**: YYYY-MM-DD · **Tipo**: plan de implementación por fases.
> **Base**: <planes previos que sustentan esto, enlazados; "(ninguno)" si no hay>.
> **Proyectos afectados**: <backend | frontend | ambos>.
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo
<qué se logra y por qué>

## Contexto / hallazgos del análisis
<lo relevante descubierto en el código, con citas archivo:línea>

## Decisiones pendientes (bloqueantes)
<preguntas a resolver antes de codificar; "(ninguna)" si no hay>

## Principios
<reglas que rigen el plan: verde por fase (pytest backend / build frontend), backend
primero cuando el frontend consume algo nuevo, contrato HTTP explícito, aditivo antes
que destructivo, alcance mínimo, sin dependencias nuevas salvo necesidad clara>

## Mapa de fases
| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | Xm | _(sin commit)_ |
| 1 | <…> | <backend/frontend/ambos> | <Aditivo/Medio/Alto> | Xm | `type(scope): mensaje` |
| … | | | | | |

---

## Fase N — <nombre>
**Proyecto**: <backend | frontend | ambos>
**Objetivo**: <qué resuelve esta fase>
**Archivos afectados**: <lista con enlaces>
**Impacto en contrato API (front↔back)**: <Sí/No — si **Sí**, describe qué cambia de
lo que el otro proyecto ve: ruta, shape del JSON, status codes, variables de entorno.
Una fase que cambie el contrato debe decir en qué fase se actualiza el otro lado>.
**Acciones**:
1. <paso concreto, cada una indicando a qué proyecto pertenece si la fase es "ambos">
2. <…>
**Pruebas / verificación**: <pytest (backend), npm run build (frontend), levantar
uvicorn / vite y curl o revisión manual cuando aplique, casos negativos (payload
inválido → 4xx, API caída → el front no revienta)>
**Riesgos**: <si aplica>

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase N+1 sin aprobación del usuario.
**Commit sugerido**: `type(scope): mensaje en imperativo, ≤72 chars`
```

Reglas de forma del plan:
- **La Fase 0 siempre es pre-flight** (verificaciones read-only: estado de tests del
  backend, build del frontend, estado del venv y `node_modules`) y no lleva commit.
- **Toda fase declara su Proyecto.** Preferir fases de UN solo proyecto; una fase
  `ambos` solo cuando separar rompería el build (p. ej. renombrar un endpoint ya
  consumido). Con fases separadas: **backend primero**, para que el frontend consuma
  algo que ya existe.
- **Marca las fases que tocan el contrato front↔back.** Para cada fase decide si
  cambia algo que el otro proyecto ve: rutas, shape del JSON, status codes, env vars
  (`VITE_API_URL`, `FRONTEND_URL`). Márcalo en **Impacto en contrato API**.
- Ordena las fases para que cada una **deje el build verde** (pytest del backend en
  verde, `npm run build` del frontend OK, y ambos servidores levantan), sea revisable
  de forma independiente, y vaya de **aditivo a destructivo** (limpieza al final).
- Las fases que agreguen endpoints cierran con **tests de ruta negativa** en el
  backend (payload inválido → 4xx, nunca 500). Las fases de frontend que consuman la
  API contemplan el caso de API caída (mensaje de error, no pantalla rota).
- Variable de entorno nueva = actualizar el `.env.example` del proyecto en la misma
  fase.
- Toda sugerencia de commit sigue
  [commit-standards.md](.claude/rules/commit-standards.md): Conventional Commits,
  imperativo, primera línea ≤72 (el hook la bloquea si no). Alcances sugeridos:
  `back`, `front`, o el nombre de la feature.
- Comandos de verificación en Windows: backend desde `backend/` con
  `.venv\Scripts\python.exe -m pytest -q`; frontend desde `frontend/` con
  `npm run build`.
- Estima minutos por fase (es un hackathon: si el plan crece demasiado, propone qué
  recortar o aplazar).

### Paso 3 — Protocolo de ejecución (cuando el usuario apruebe el plan)

Generar el plan NO inicia la ejecución. Cuando el usuario pida ejecutarlo:

1. **Detente al inicio de cada fase.** Antes de trabajar, presenta objetivo y acciones
   de la fase y **espera aprobación explícita**. No encadenes fases.
2. Implementa solo esa fase. Deja el build verde (pytest backend y/o build frontend
   según el proyecto de la fase).
3. **En el 🛑 CHECKPOINT de la fase: detente, NO commitees automáticamente.** Muestra
   qué cambió y **sugiere el nombre del commit** (el de la columna del plan, refinado
   si el trabajo divergió). El usuario revisa y commitea.
3.5. **Si la fase ejecutada está marcada `Impacto en contrato API: Sí`**, resume en el
   checkpoint qué cambió del contrato y qué fase (o quién) actualiza el otro lado.
4. Solo después de que el usuario diga continuar, pasa a la siguiente fase — parando
   de nuevo en su inicio.

## Output

Tras escribir el archivo, imprime:
- La ruta del plan.
- La tabla **Mapa de fases** (fases + proyecto + estimaciones + commits sugeridos de
  un vistazo).
- Las **Decisiones pendientes**, si las hay, pidiendo resolverlas antes de ejecutar.
- Si el plan tiene **fases con impacto en el contrato front↔back** (`Sí`) y en qué
  fase se actualiza cada lado.
- El recordatorio de que la ejecución es fase por fase con parada y commit sugerido en
  cada frontera, y que nada se commitea automáticamente.

**RESTRICCIONES**: Mientras corre `/gen-plan` solo analizas y escribes el documento del
plan — no modificas código de la aplicación, no instalas dependencias ni commiteas. La
ejecución es un paso separado, aprobado por el usuario y compuerta por fases.
