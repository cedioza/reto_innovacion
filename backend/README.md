# Backend — FastAPI

API del reto de innovación construida con [FastAPI](https://fastapi.tiangolo.com/).

## Requisitos

- Python 3.12+

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate    # Linux / macOS
pip install -e ".[dev]"
copy .env.example .env    # cp en Linux / macOS
```

## Ejecución

```bash
uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

## Tests

```bash
pytest
```

## Persistencia (C3)

Las conversaciones (transcripción completa), las solicitudes con consentimiento y
las sesiones de canal (teléfono→conversación) se persisten vía **SQLModel** en las
tablas `conversaciones`, `solicitudes`, `sesiones_canal` y `eventos_procesados`
(esta última deduplica webhooks de YCloud entre reinicios).

- **Motor**: `DATABASE_URL` (ver `.env.example`). Con la variable vacía el backend
  cae a un SQLite local de desarrollo (`app/data/local.db`, ignorado por git).
  Para Postgres local: `docker compose up -d db` desde la raíz del monorepo y
  `DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion`.
- **Esquema**: `SQLModel.metadata.create_all` en el lifespan de la app — sin
  Alembic, decisión de hackathon (los modelos se crean solos al arrancar).
- **Diseño**: cada registro guarda el documento Pydantic completo en una columna
  JSON (JSONB en Postgres) más columnas indexables (`estado`, `handoff_token`,
  `evidence_hash`); los repositorios conservan el contrato previo, así que
  services y API no cambiaron.
- **Tests**: los repos se prueban contra SQLite in-memory por velocidad/CI (nota
  de compatibilidad en cada módulo de tests); el shape SQL es compatible con
  Postgres.

## Base de afiliados y columnas sintéticas (C2)

La base anonimizada de afiliados vive en la tabla **`afiliados`** (PK `serie`, el
identificador que reemplaza a la cédula). El lookup de `perfilar_cliente()` sigue
la cascada **cache en memoria → tabla `afiliados` → CSV/xlsx local (fallback
dev)** — sin `DATABASE_URL` ni tabla cargada, todo funciona igual que antes con
`AFFILIATE_CSV_PATH`.

**Carga** (la fuente NUNCA se commitea al repo — regla del vault):

```bash
python -m app.scripts.cargar_afiliados "ruta\al\archivo.xlsx" --replace
```

Reusa el parser de C1 (xlsx de la muestra de 500k o CSV `;` de la base completa,
normalización incluida), inserta por lotes de 5.000 y reporta filas cargadas,
errores de parseo y duración.

**Columnas reales vs. sintéticas** — decisión de equipo (2026-07-24): 4 de las 5
marcas de consumo del dataset vienen casi vacías, así que el perfil se complementa
con columnas **sintéticas**, siempre con prefijo `sint_` para distinguirlas de la
data real ante el jurado:

| Columna | Origen | Generación |
|---|---|---|
| `gender`, `age_range`, `salary_range`, `category`, `household_segment`, `population_segment`, `pyramid`, `empresa_foco`, `city`, `uses_*` | **Real** (dataset Colsubsidio) | Parser C1, normalización por dígitos |
| `sint_tiene_vehiculo` | Sintética | ≈28%, hash determinista por SERIE |
| `sint_tiene_credito` | Sintética | ≈35%, hash determinista por SERIE |
| `sint_tiene_hijos` | Sintética | ≈65% si segmento familiar RHO/LAMBDA, ≈25% resto (correlada con la señal real) |
| `sint_tipo_vivienda` | Sintética | ≈40% apartment / ≈25% house / ≈35% NULL |

La generación es **determinista** (`sha256(f"{serie}:{campo}")`, sin `random`):
misma SERIE → mismo perfil sintético en cualquier recarga, reproducible y
defendible. Al armar el perfil de dominio, `sint_tiene_*` alimenta
`has_children/has_vehicle/has_credit` y `sint_tipo_vivienda` a `property_type`;
lo **declarado en conversación siempre pisa lo sintético**. El camino CSV de
fallback no inventa señales (quedan `None`).

## Arquitectura de capas

```
app/
├── main.py          # entrypoint FastAPI
├── core/            # configuración (pydantic-settings)
├── api/routes/      # routers HTTP
├── services/        # lógica de negocio
├── repositories/    # acceso a datos
├── models/          # modelos de persistencia (SQLModel)
├── schemas/         # DTOs Pydantic
└── helpers/         # utilidades transversales
```

Regla de dependencias: `api → services → repositories → models` — ninguna capa se salta la intermedia.
