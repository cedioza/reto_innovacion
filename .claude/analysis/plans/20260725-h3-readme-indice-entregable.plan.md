# Plan — H3: README índice del entregable · (por fases, checkpoint por fase)

> **Fecha**: 2026-07-25 · **Tipo**: plan de implementación por fases (solo documentación).
> **Base**: [20260725-b3-propension-multicategoria-explicable.plan.md](.claude/analysis/plans/20260725-b3-propension-multicategoria-explicable.plan.md)
> (✅ motor multi-categoría — es la lógica que el README debe documentar),
> [20260725-c2-base-afiliados-postgres.plan.md](.claude/analysis/plans/20260725-c2-base-afiliados-postgres.plan.md)
> (✅ base real + columnas sintéticas — la "nota de datos" del README sale de ahí) y
> [20260725-h1-spa-fallback-y-housekeeping-git.plan.md](.claude/analysis/plans/20260725-h1-spa-fallback-y-housekeeping-git.plan.md)
> (✅ la sección Deploy/Dokploy del README actual, que se conserva).
> Tarea del vault: `07 - Tareas/Feature H - Entrega y despliegue/H3 - README indice del entregable.md`
> (sin dependencias; capa integración; estimación 2h; **el jurado del prefiltro lee
> este archivo primero**). Estructura dictada por la charla
> `06 - Pitch/Charla Gana el mejor pitch (30X)` y DEC-009 (nombre **PólizIA**).
> **Proyectos afectados**: ambos (solo archivos `.md` en la raíz y `docs/` — cero
> código de aplicación).
> **Cómo usar este plan**: cada fase termina en un **🛑 CHECKPOINT**. Al iniciar la
> ejecución de **cada** fase el trabajo se DETIENE para tu aprobación; al cerrar una
> fase se **sugiere el nombre del commit** (no se commitea: lo haces tú tras revisar).
> No se avanza a la siguiente fase sin tu visto bueno.

## Objetivo

El README raíz de `cedioza/reto_innovacion` se convierte en la **documentación
oficial del entregable** con la estructura recomendada por la charla de pitch:
sobre el proyecto (PólizIA), construido con, **cómo ejecutar** (entregable oficial,
reproducible por un tercero), links a demo y video, arquitectura (mermaid del vault
actualizado), **cómo funciona la recomendación** (lógica del motor de propensión —
requisito no negociable del reto, con ≥3 ejemplos), **roadmap de los 3 meses de
piloto**, licencia, contacto y agradecimientos. La nota de datos deja claro que la
base de Colsubsidio NO está en el repo y cómo correr sin ella.

Criterios de aceptación del vault:
1. Un tercero ejecuta el proyecto siguiendo solo el README.
2. Links de demo y video funcionan (se completan sábado/domingo — quedan
   placeholders marcados).
3. La lógica de propensión explicada con al menos 3 ejemplos de perfil.

## Contexto / hallazgos del análisis

**El README actual ([README.md](README.md)) es interno, no de entregable:** tiene
instrucciones de ejecución correctas y una buena sección Deploy/Dokploy
([README.md:46-54](README.md#L46-L54)) y de BD local
([README.md:62-87](README.md#L62-L87)), pero le falta TODO lo que el jurado busca:
qué es el producto, para quién, demo/video, arquitectura, lógica del motor, roadmap,
licencia y contacto. Nada de lo existente se pierde: se reorganiza bajo la nueva
estructura (Deploy y BD local pasan a subsecciones de "Cómo ejecutar" / se enlazan).

**Estructura exacta dictada por la charla** (`Charla Gana el mejor pitch (30X)` —
sección "README del repo índice"): sobre el proyecto · construido con · cómo
comenzar · link a demo desplegado + video · **roadmap de los 3 meses de piloto** ·
licencia/contacto/agradecimientos (mentores). La charla también avisa: **commits
limpios suman si auditan el repo** (ya cubierto por el hook) y el jurado pregunta
"¿qué harías con 3 meses de piloto?" — la respuesta del README debe coincidir con la
del pitch.

**El roadmap del piloto YA está escrito en el vault** (`02 - Idea y Negocio/Modelo
de negocio` → "Camino de implementación en Colsubsidio"): piloto semanas 1-8 (un
producto, un canal, tráfico limitado, humano supervisando transcripciones) →
validación (conversión vs. canal humano) → escala (más productos incluyendo
mediación con broker — idea de mentores 25-jul; integración API aseguradora;
campañas por segmento). El README lo condensa en 3 hitos; no se inventa contenido
nuevo.

**La lógica del motor a documentar es la REAL post-B3** (no la tabla teórica del
plan B3 — hubo 2 desviaciones en ejecución):
[propensity.py](backend/app/services/propensity.py) tiene 16 reglas declarativas en
`CATEGORY_RULES` ([propensity.py:99+](backend/app/services/propensity.py#L99)) con
codes/pesos verificados: hogar (`homeowner` 0.45, `income_tier` 0.15, `zone_risk`
0.10, `age_risk` −0.10), vida (`dependents` 0.50, `family_profile` 0.15,
`life_stage` 0.15, `family_segment` 0.10 — cita el conteo real de droguería),
accidentes (`young_profile` 0.40, `no_dependents` 0.15 — **solo con `False`
declarado, no ausencia**, `urban_exposure` 0.10), movilidad (`vehicle_declared`
0.75, `young_driver` 0.05, `asset_protection` 0.0 — razón explicativa), crédito
(`credit_declared` 0.70, `working_age` 0.10). Determinismo, ranking de 5 categorías,
desempate por orden de catálogo, umbral `recommended >= 0.5` y log JSON por
evaluación. Los **ejemplos de perfil ya están testeados** — los 5 perfiles canónicos
de [test_propensity_multicategory.py](backend/tests/test_propensity_multicategory.py)
son los ejemplos perfectos (perfil → producto → razones), más el caso "dato
enriquecido voltea el ranking" (hogar + vehículo → movilidad).

**Nota de datos (C1/C2, ya en master):** la base real NUNCA entra al repo
([.gitignore](.gitignore) la excluye); sin `DATABASE_URL` ni CSV el backend funciona
igual (fallback declarado); con archivo local se carga con
`python -m app.scripts.cargar_afiliados` (doc ya escrita en
[backend/README.md](backend/README.md) — el README raíz la enlaza, no la duplica).
Columnas sintéticas `sint_*` documentadas ahí mismo (defensa ante el jurado).

**El diagrama del vault necesita 3 retoques al pegarlo** —
`04 - Tecnología/arquitectura-funnel.mermaid` sigue diciendo "Perfiles sintéticos
base Faker" (hoy: base real Postgres + complemento `sint_*`), "[E1] Checkout
interno simulado" (el cierre real es handoff por correo a la aseguradora simulada,
E1/E2 ya implementados) y no menciona el panel/rutas reales. Se pega ACTUALIZADO
en el README (GitHub renderiza mermaid nativo); el `.mermaid` del vault se
actualiza aparte (fuera del repo, nota al vault).

**Dónde NO tocar:** [backend/README.md](backend/README.md) y
[frontend/README.md](frontend/README.md) ya cumplen su rol (se enlazan);
[README-IA.md](README-IA.md) se mantiene enlazado desde "Desarrollo".

**Ámbito de escritura:** los agentes implementer NO escriben en la raíz ni en
`docs/` (su ámbito es `app|tests|src`). **Estas fases las ejecuta el
orquestador/autor directamente** (en `/run-plan` las escribe la sesión principal;
en `/launch-plan` el orquestador, como ya pasó con el README de C2).

## Decisiones pendientes (bloqueantes)

(ninguna — resueltas por Carlos el 2026-07-25:
**1. Licencia: MIT** — se crea el archivo `LICENSE` (MIT) en la Fase 2 y la
sección del README lo enlaza.
**2. Contacto: NO se publica** — el README no lleva sección de contacto ni
correos/nombres; el cierre es solo Licencia · Agradecimientos.
**3. Se documenta el repo compañero
[zubcarz/colsubsidio-brain](https://github.com/zubcarz/colsubsidio-brain)** — el
README explica su propósito: es el "segundo cerebro" del reto (vault Obsidian)
donde vive todo el trabajo NO-código — análisis del enunciado y de la base de
afiliados, registro de decisiones (DEC-001…DEC-009), matriz de perfilamiento,
modelo de negocio, material del pitch y el tablero de tareas por feature (A…H) —
y del cual este repo se alimentó: cada plan de implementación de
`.claude/analysis/plans/` nace de una tarea de ese vault. Proyecto y
documentación se trabajaron de la mano.

Los links de demo/video NO bloquean: la propia tarea dice que se completan
sábado/domingo — van como placeholders visibles `> 🔗 pendiente: se publica el
sábado`.)

## Principios

- **Solo `.md`**: cero código de aplicación, cero dependencias, cero env vars. La
  suite y el build no pueden cambiar (verificación de humo por fase).
- **Documentar lo que ES, no lo que se planeó**: reglas/pesos copiados de
  `propensity.py` real; comandos copiados y PROBADOS, no de memoria.
- **No duplicar**: el README raíz es índice — enlaza a `backend/README.md`,
  `frontend/README.md` y `docs/propension.md` en vez de repetirlos.
- **Nada se pierde**: las secciones actuales (Deploy Dokploy, BD local, README-IA)
  sobreviven reorganizadas.
- Aditivo antes que destructivo: primero `docs/propension.md` (nuevo), después la
  reescritura del README.

## Mapa de fases

| Fase | Nombre | Proyecto | Impacto | Est. | Commit sugerido al cierre |
|------|--------|----------|---------|------|---------------------------|
| 0 | Pre-flight (read-only / verificación) | ambos | Ninguno | 10m | _(sin commit)_ |
| 1 | `docs/propension.md` — lógica del motor con ejemplos | ambos (docs) | Aditivo | 30m | `docs: explain propensity engine rules with profile examples` |
| 2 | README raíz reescrito como índice del entregable | ambos (docs) | Aditivo/Medio (reorganiza) | 40m | `docs: rewrite README as official deliverable index` |
| 3 | Dry-run de tercero + ajustes finos | ambos | Bajo (correcciones) | 20m | `docs: fix run instructions after clean dry-run` _(solo si hay ajustes)_ |

Total: ~100m (dentro de las 2h). Los placeholders de demo/video se llenan el
sábado tras H1/H6 (fuera de este plan).

---

## Fase 0 — Pre-flight (read-only / verificación)

**Proyecto**: ambos
**Objetivo**: confirmar que lo que el README va a prometer es cierto HOY.
**Archivos afectados**: ninguno.
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Backend desde `backend/`: `.venv\Scripts\python.exe -m pytest -q` → línea base
   verde (registrar conteo).
2. Frontend desde `frontend/`: `npm run build` → OK.
3. Verificar los comandos que el README actual promete: `python dev.py` levanta
   ambos (comprobación rápida de arranque y `Ctrl+C`), `docker compose up -d db`
   (si Docker está disponible; si no, registrar que la verificación va en Fase 3).
4. Confirmar en `propensity.py` los 16 codes/pesos listados en el contexto de este
   plan (lectura, para que la Fase 1 no documente cifras desactualizadas si otra
   rama tocó el motor).

**Pruebas / verificación**: las de arriba.
**Riesgos**: ninguno.

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 1 sin aprobación del usuario.
**Commit sugerido**: _(sin commit)_

---

## Fase 1 — `docs/propension.md`: lógica del motor con ejemplos

**Proyecto**: ambos (documentación; la escribe el orquestador/autor — fuera del
ámbito de los agentes)
**Objetivo**: el requisito no negociable ("lógica documentada, no caja negra") en un
documento propio, enlazable desde el README y defendible ante el jurado.
**Archivos afectados**: `docs/propension.md` (nuevo).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Escribir `docs/propension.md` con:
   - **Cómo decide el motor** (5 párrafos): reglas declarativas como datos
     (`CATEGORY_RULES`), score por categoría = suma de pesos de condiciones que
     aplican (clamp 0-1), ranking de las 5 categorías con desempate por orden de
     catálogo, `recommended` si el ganador ≥ 0.5, determinismo total (mismo perfil
     → mismo ranking, testeado) y log JSON de cada evaluación (auditoría).
   - **Tabla completa de reglas** (las 16 reales de
     [propensity.py](backend/app/services/propensity.py): categoría, condición en
     lenguaje claro, peso, code, evidencia que cita — incluida la calibración con
     la base real: "21,7% del segmento RHO usa droguería" y "50% de la base tiene
     20-35 años").
   - **≥3 ejemplos perfil → producto → razones** (criterio 3; usar 4: los perfiles
     canónicos testeados de
     [test_propensity_multicategory.py](backend/tests/test_propensity_multicategory.py)):
     casa/26-40/urbano/estrato 3 → **Hogar Estándar**; 26-40 + hijos + familia →
     **Vida Básico**; 18-25/urbano/sin dependientes → **Accidentes Personales**; y
     el caso estrella del demo: el MISMO perfil de hogar + "tengo carro" →
     **Auto Todo Riesgo** (el dato enriquecido voltea el ranking y la razón lo
     cita).
   - **De dónde salen las señales**: declaradas en conversación (siempre ganan),
     base real por SERIE y complemento sintético `sint_*` (enlace a
     [backend/README.md](backend/README.md) — sección C2), y matiz honesto: las
     marcas de consumo casi vacías NO se puntúan (anomalía droguería >45 sin
     aclarar por mentores).
   - **Qué lo hace defendible**: el LLM nunca decide precio ni producto — relata lo
     que el motor devuelve (cita al system prompt del orquestador).
2. Enlazar los archivos fuente con rutas relativas clicables (GitHub).

**Pruebas / verificación**: revisión de exactitud contra el código (cada peso/code
de la tabla existe en `propensity.py`); render del markdown (tabla y mermaid si
aplica) en preview; suite/build intactos (no se tocó código).
**Riesgos**: deriva doc↔código si B4/B5 recalibran pesos después — mitigado con una
línea al pie ("fuente de verdad: `propensity.py`; última sincronización: fecha").

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 2 sin aprobación del usuario.
**Commit sugerido**: `docs: explain propensity engine rules with profile examples`

---

## Fase 2 — README raíz reescrito como índice del entregable

**Proyecto**: ambos (documentación; orquestador/autor)
**Objetivo**: la estructura oficial de la charla, con todo lo actual reorganizado y
nada inventado.
**Archivos afectados**: [README.md](README.md) (reescritura), `LICENSE` (nuevo,
texto MIT estándar, copyright "2026 Equipo PólizIA"), `docs/` (ya existe por F1).
**Impacto en contrato API (front↔back)**: No.
**Acciones** (estructura final del README, en este orden):
1. **PólizIA** (DEC-009) — título + una línea: "asesora de seguros con IA para
   afiliados de Colsubsidio: recomienda, cotiza, compara y deja la solicitud lista
   — explicable de punta a punta". Badge/nota de hackathon (reto seguros).
2. **Sobre el proyecto** — 2 párrafos (problema: portafolio invisible para el
   afiliado; solución: canal conversacional que perfila con la base real + lo
   declarado). Para quién (afiliados y no afiliados).
3. **Construido con** — FastAPI + Python 3.12, Vue 3 + Vite, Gemini (function
   calling), Postgres/SQLModel, Dokploy; catálogo JSON versionado. Sin humo: solo
   lo que está en `pyproject.toml`/`package.json`.
4. **Demo y video** — `> 🔗 Demo desplegado: pendiente (se publica el sábado)` y
   `> 🎥 Video: pendiente (domingo)` — placeholders visibles e inconfundibles.
5. **Cómo ejecutar** (entregable oficial) — quickstart de 5 comandos (clonar →
   venv+deps backend → deps frontend → `python dev.py` → abrir 5173), enlaces a
   [backend/README.md](backend/README.md) y [frontend/README.md](frontend/README.md)
   para el detalle; subsección **"Nota de datos"**: la base de Colsubsidio NO está
   en el repo (regla), el proyecto corre SIN ella (perfil declarado), y cómo
   cargarla si se tiene el archivo (`python -m app.scripts.cargar_afiliados`,
   enlace a backend/README.md); subsección **BD local opcional** (docker compose,
   contenido actual [README.md:62-87](README.md#L62-L87) condensado); tests:
   `cd backend && pytest`.
6. **Cómo funciona la recomendación** — resumen de 6-8 líneas + los 2 ejemplos más
   ilustrativos (hogar; hogar+carro→movilidad) + enlace a
   [docs/propension.md](docs/propension.md) (F1).
7. **Arquitectura** — bloque ```mermaid``` pegado del vault CON los 3 retoques:
   "Perfiles: base real Postgres (tabla `afiliados`) + complemento sintético
   `sint_*`; Faker solo identidad de contacto", cierre por "handoff correo →
   página aseguradora simulada (E1/E2)" en lugar de "checkout interno", y nota de
   canales reales (web + WhatsApp YCloud/Meta + Telegram). Verificar que GitHub lo
   renderiza (sintaxis válida).
8. **Deploy (Dokploy)** — la sección actual [README.md:46-54](README.md#L46-L54)
   se conserva casi íntegra (ya está correcta y actualizada).
9. **Roadmap — 3 meses de piloto** — 3 hitos del vault (Modelo de negocio):
   semanas 1-8 piloto (un producto con acuerdo directo, un canal, humano
   supervisando transcripciones); validación (conversión y calidad vs. canal
   humano); escala (portafolio completo incl. mediación con broker, integración
   API aseguradora, campañas por segmento). Coincide palabra por palabra con la
   respuesta preparada del pitch.
10. **Cómo se construyó — repo compañero
    [colsubsidio-brain](https://github.com/zubcarz/colsubsidio-brain)** — párrafo
    propio (decisión 3): el proyecto se trabajó de la mano con ese vault Obsidian,
    el "segundo cerebro" del reto donde vive todo el trabajo no-código — análisis
    del enunciado y de la base real de afiliados, registro de decisiones
    (DEC-001…DEC-009), matriz de perfilamiento, modelo de negocio, material del
    pitch y el tablero de tareas por feature (A…H). Cada plan de
    `.claude/analysis/plans/` de este repo nace de una tarea de ese vault: la
    trazabilidad idea → decisión → tarea → plan → commit es parte del entregable.
11. **Desarrollo** — flujo IA (README-IA.md), PRs a master, commits convencionales
    (hook) — contenido actual condensado.
12. **Licencia · Agradecimientos** — Licencia **MIT** (enlace al `LICENSE` creado
    en esta fase). **Sin sección de contacto** (decisión 2: no se publican correos
    ni nombres). Agradecimientos a mentores del reto y a Colsubsidio por la base
    anonimizada.

**Pruebas / verificación**: preview del markdown (mermaid renderiza, anchors
funcionan, links relativos resuelven en GitHub — ojo: `docs/propension.md` y los
README anidados); `git diff` de lo eliminado = nada sin nuevo hogar; suite/build
intactos.
**Riesgos**: prometer en "Cómo ejecutar" algo no verificado → lo cubre la Fase 3;
links de demo/video muertos si se olvidan el sábado → placeholders con texto
"pendiente" explícito (nunca un link roto).

🛑 **CHECKPOINT** — Detente aquí. No inicies la Fase 3 sin aprobación del usuario.
**Commit sugerido**: `docs: rewrite README as official deliverable index`

---

## Fase 3 — Dry-run de tercero + ajustes finos

**Proyecto**: ambos
**Objetivo**: criterio 1 — que un tercero ejecute el proyecto siguiendo SOLO el
README (sin conocimiento tribal).
**Archivos afectados**: [README.md](README.md) y/o `docs/propension.md` (solo si el
dry-run encuentra fricciones).
**Impacto en contrato API (front↔back)**: No.
**Acciones**:
1. Simular máquina limpia en lo posible: clonar el repo a una carpeta temporal,
   crear venv NUEVO (`python -m venv .venv` + `pip install -e ".[dev]"`) y
   `npm ci` en frontend, siguiendo EXCLUSIVAMENTE los comandos del README (sin
   `.env`, sin Docker, sin base de datos — el caso "tercero sin nada").
2. Verificar: backend levanta y responde `/api/v1/health`; frontend `npm run dev`
   sirve la SPA; `pytest` verde en el venv limpio; el flujo REST básico responde
   (crear conversación + perfil → recomendación) sin `.env` (sin Gemini el chat
   LLM no aplica — confirmar que el README lo advierte en la Nota de datos/env).
3. Anotar cada fricción encontrada y corregir el README en el momento (comando
   faltante, paso implícito, versión de Python, etc.).
4. Checklist final de links internos (todos los relativos abren en GitHub).

**Pruebas / verificación**: el dry-run ES la prueba; borrar la carpeta temporal al
terminar. Suite/build del repo principal intactos.
**Riesgos**: diferencias Windows/Linux en comandos (venv activate) → el README ya
muestra ambas variantes (mantenerlas); Docker ausente en la máquina de prueba →
la sección BD local es opcional y está marcada como tal.

🛑 **CHECKPOINT** — fin del plan.
**Commit sugerido**: `docs: fix run instructions after clean dry-run` _(omitir si
no hubo cambios)_

---

## Deuda / fuera de alcance (anotada para el vault)

- **Links de demo y video** (criterio 2): se llenan sábado (deploy H1/H6) y domingo
  (video) — placeholder explícito hasta entonces.
- **Actualizar `arquitectura-funnel.mermaid` en el vault** con los mismos retoques
  que la copia del README (el vault no vive en este repo).
- **H4 (seed + guiones por categoría)** enlazará sus guiones desde el README si da
  el tiempo — hueco previsto en la sección Demo.
- Badges de CI (H2) — si H2 se implementa, agregar el badge al encabezado.
