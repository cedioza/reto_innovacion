# Motor de propensión explicable — cómo decide PólizIA

> Requisito no negociable del reto: **la recomendación cambia según el perfil y
> cada recomendación trae sus razones** — lógica documentada, no caja negra.
> Fuente de verdad: [`backend/app/services/propensity.py`](../backend/app/services/propensity.py)
> (última sincronización de este documento: 2026-07-25).

## Cómo decide el motor

1. **Reglas como datos, no código enredado.** Toda la lógica vive en una única
   tabla declarativa (`CATEGORY_RULES`): cada regla dice a qué **categoría**
   aporta, qué **condición** del perfil la activa, cuánto **peso** suma y qué
   **razón** (`code` / `label` / `evidence`) deja como rastro. Agregar una señal
   es agregar una entrada — nunca crece un `if` gigante.

2. **Score por categoría.** Para un perfil dado, el score de cada categoría es la
   suma de los pesos de sus reglas activas, acotada a `[0, 1]`. Se puntúan las
   **5 categorías del catálogo**: hogar, vida, accidentes, movilidad y crédito.

3. **Ranking completo, no solo un ganador.** El resultado ordena las 5 categorías
   por score (desempate estable: el orden del catálogo, hogar primero) y expone
   el ranking entero — el agente puede explicar también las alternativas. La
   categoría ganadora se marca `recommended` si su score es **≥ 0.5**.

4. **Determinismo total.** El mismo perfil produce siempre el mismo ranking, los
   mismos scores y las mismas razones (hay un test que lo fija). No hay azar ni
   LLM en la decisión: **el modelo de lenguaje relata lo que el motor decidió,
   nunca al revés** — un precio o recomendación salida de la generación libre de
   un LLM sería descalificatoria en un producto financiero.

5. **Auditable por diseño.** Cada evaluación emite un log JSON estructurado con
   el perfil (campos no nulos), el score de las 5 categorías, los códigos de
   razones y el ganador — evidencia de asesoría trazable.

## Las 16 reglas (pesos reales del código)

| Categoría | Condición (perfil) | Peso | `code` | Evidencia que cita |
|---|---|---|---|---|
| hogar | tipo de propiedad es casa o apartamento | +0.45 | `homeowner` | tipo de propiedad declarado/sintético |
| hogar | estrato 2–4 **y** hay propiedad | +0.15 | `income_tier` | estrato |
| hogar | zona urbana **y** hay propiedad | +0.10 | `zone_risk` | zona |
| hogar | edad 18–25 | −0.10 | `age_risk` | rango de edad |
| vida | hijos/dependientes declarados | +0.50 | `dependents` | hijos: sí |
| vida | familia a cargo declarada | +0.15 | `family_profile` | familia: sí |
| vida | edad 26–40 o 41–55 | +0.15 | `life_stage` | rango de edad |
| vida | segmento familiar RHO o LAMBDA (base real) | +0.10 | `family_segment` | **21,7% del segmento RHO usa droguería vs 16,8% de LAMBDA** (conteo real de la base) |
| accidentes | edad 18–25 | +0.40 | `young_profile` | **50% de la base de afiliados tiene 20–35 años** (conteo real) |
| accidentes | declaró explícitamente NO tener hijos ni familia | +0.15 | `no_dependents` | sin dependientes declarados |
| accidentes | zona urbana | +0.10 | `urban_exposure` | zona |
| movilidad | vehículo propio declarado | +0.75 | `vehicle_declared` | vehículo: sí |
| movilidad | edad 18–25 **y** vehículo | +0.05 | `young_driver` | rango de edad |
| movilidad | vehículo (razón explicativa, no puntúa) | +0.00 | `asset_protection` | el vehículo como activo patrimonial |
| crédito | crédito vigente declarado | +0.70 | `credit_declared` | crédito: sí |
| crédito | edad 26–40 o 41–55 **y** crédito | +0.10 | `working_age` | rango de edad |

Notas de diseño:

- `no_dependents` exige un **"no" declarado** (`False`), no la ausencia del dato —
  no saber si alguien tiene hijos no es evidencia de que no los tenga.
- `asset_protection` pesa 0 a propósito: existe para que una recomendación de
  movilidad nunca llegue con una sola razón, sin alterar la calibración.
- Los pesos son un punto de partida calibrable; los tests fijan **qué categoría
  gana con cada perfil**, no cifras exactas — recalibrar no rompe la suite.

## Ejemplos (perfiles reales de la suite de tests)

Los cuatro casos siguientes están fijados por tests en
[`backend/tests/test_propensity_multicategory.py`](../backend/tests/test_propensity_multicategory.py).

### 1. Perfil de hogar → **Hogar Estándar** (score 0.70)

`casa · 26–40 · zona urbana · estrato 3`

- hogar = 0.45 (`homeowner`) + 0.15 (`income_tier`) + 0.10 (`zone_risk`) = **0.70** ✅
- vida = 0.15 (`life_stage`) · accidentes = 0.10 (`urban_exposure`) · movilidad = 0 · crédito = 0

### 2. Perfil familiar → **Vida Básico** (score 0.80)

`26–40 · hijos declarados · familia a cargo` (sin propiedad declarada)

- vida = 0.50 (`dependents`) + 0.15 (`family_profile`) + 0.15 (`life_stage`) = **0.80** ✅
- hogar = 0 (sin propiedad no hay señal de hogar)

### 3. Joven soltero → **Accidentes Personales** (score 0.65)

`18–25 · zona urbana · declaró no tener hijos ni familia`

- accidentes = 0.40 (`young_profile`) + 0.15 (`no_dependents`) + 0.10 (`urban_exposure`) = **0.65** ✅
- hogar queda en 0 (sin propiedad, y la juventud además resta con `age_risk`)

### 4. El dato enriquecido voltea el ranking → **Auto Todo Riesgo** (score 0.75)

El MISMO perfil del ejemplo 1 dice en la conversación **"tengo carro"**:

- movilidad = 0.75 (`vehicle_declared`, + razón `asset_protection`) > hogar = 0.70
- La recomendación **cambia de Hogar a Auto** y la primera razón cita
  exactamente el dato nuevo: "Vehículo propio declarado que proteger".

Este es el caso corazón del pitch: un solo dato declarado re-rankea todo el
portafolio y la explicación lo cita textualmente.

### Sin señales → fallback honesto

Un perfil vacío puntúa 0 en todo: gana hogar solo por el desempate del catálogo y
sale con `recommended: false` — el agente sigue conversando para conseguir
señales en lugar de vender sin sustento.

## De dónde salen las señales

| Fuente | Qué aporta | Prioridad |
|---|---|---|
| **Declarado en conversación** | propiedad, zona, estrato, edad, familia, hijos, vehículo, crédito | **Siempre gana** sobre cualquier otra fuente |
| **Base real de afiliados** (tabla `afiliados`, lookup por `SERIE`) | edad, segmento familiar/poblacional, salario, ciudad, marcas de consumo | Punto de partida del perfil de un afiliado |
| **Complemento sintético `sint_*`** | vehículo, crédito, hijos, tipo de vivienda (deterministas por SERIE) | Rellena lo que la base real no trae; claramente marcado — ver [backend/README.md](../backend/README.md) |

Matiz honesto: 4 de las 5 marcas de consumo de la base vienen casi vacías y la
marca de droguería muestra una anomalía en mayores de 45 años sin aclarar por los
mentores — por eso **ninguna regla depende de esas marcas**; el único uso de la
base en reglas es el conteo agregado del segmento familiar (`family_segment`).

## Por qué es defendible

- El precio, el producto y las razones salen **solo** de motores deterministas
  (propensión + tarifas del catálogo); el LLM tiene prohibido inventarlos (regla
  dura del system prompt del orquestador).
- Toda evaluación queda loggeada con sus scores y razones.
- La calibración citada es **real** (análisis de la muestra de 500k afiliados) y
  lo sintético está separado por naming (`sint_*`) para poder defenderlo tal
  cual ante el jurado.
