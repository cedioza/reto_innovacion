# PólizIA 🛡️

**Asesora de seguros con IA para afiliados de Colsubsidio: recomienda, cotiza,
compara y deja la solicitud lista — explicable de punta a punta.**

> Proyecto del reto de seguros — Hackathon de innovación Colsubsidio 2026.

## Sobre el proyecto

El portafolio de seguros de Colsubsidio es prácticamente invisible para sus
afiliados: hoy comprar una póliza exige saber que existe, entender coberturas y
pasar por un canal humano de horario limitado. **PólizIA** convierte ese proceso
en una conversación: perfila al cliente (con la base real de afiliados cuando la
persona se identifica, o con lo que declare en el chat), recomienda la categoría
correcta **con razones explicables**, cotiza con un motor determinista de tarifas,
permite ajustar y comparar, y cierra dejando la solicitud lista con consentimiento
explícito y handoff por correo a la aseguradora.

Para quién: afiliados de Colsubsidio (perfil desde la base anonimizada por
`SERIE`) y no afiliados (perfil 100% declarado en conversación).

## Construido con

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) · Python 3.12 · SQLModel +
  Postgres (SQLite local como fallback dev) · [Gemini](https://ai.google.dev/) con
  function calling (el LLM conversa; **nunca** decide precios ni productos).
- **Frontend**: [Vue 3](https://vuejs.org/) + Vite.
- **Datos**: catálogo de productos en JSON versionado (fuente de verdad de
  coberturas, exclusiones, ajustes y tarifas) · base real anonimizada de 500k
  afiliados (no incluida en el repo) + complemento sintético marcado.
- **Canales**: chat web · WhatsApp (YCloud/Meta) · Telegram.
- **Infra**: Dokploy sobre VPS propio (backend Nixpacks, frontend
  Dockerfile+nginx, Postgres gestionado).

## Demo y video

> 🔗 **Demo desplegado**: pendiente — se publica el sábado.
>
> 🎥 **Video**: pendiente — se publica el domingo.

## Cómo ejecutar

Requisitos: Python 3.12+, Node 20+.

```bash
git clone https://github.com/cedioza/reto_innovacion.git
cd reto_innovacion

# Backend (terminal 1) — Windows
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # Linux/macOS: cp .env.example .env
cd ..

# Frontend (terminal 1 también — solo instala)
cd frontend && npm install && cd ..

# Levantar TODO de una vez
python dev.py
```

Backend en `http://localhost:8000` (docs interactivas en `/docs`), frontend en
`http://localhost:5173`; `Ctrl+C` detiene ambos. Detalle por proyecto:
[backend/README.md](backend/README.md) · [frontend/README.md](frontend/README.md).

Tests del backend:

```bash
cd backend && pytest
```

### Nota de datos (importante)

- **La base de afiliados de Colsubsidio NO está en este repo** (regla del reto:
  la data nunca se publica; `.gitignore` la excluye).
- **El proyecto corre completo sin ella**: sin base, el perfil se construye con lo
  declarado en la conversación (el flujo REST y todos los tests funcionan sin
  `.env`, sin Postgres y sin archivo de datos).
- Si tienes el archivo oficial (xlsx de 500k o CSV `;` de 1,5M), se carga con
  `python -m app.scripts.cargar_afiliados <ruta> --replace` — columnas reales vs.
  sintéticas (`sint_*`) documentadas en [backend/README.md](backend/README.md).
- Sin `GEMINI_API_KEY` el chat LLM no responde, pero el funnel REST (perfil →
  recomendación → cotización → consentimiento) es 100% funcional — los motores
  son deterministas, no dependen del LLM.

### Base de datos local (opcional)

Postgres 17 vía Docker (misma versión que producción; sin esto, cae a SQLite):

```bash
docker compose up -d db      # detener: docker compose down (−v borra datos)
```

y en `backend/.env`: `DATABASE_URL=postgresql://reto:reto@localhost:5432/reto_innovacion`.

## Cómo funciona la recomendación

El corazón del proyecto es un **motor de propensión explicable**: 16 reglas
declarativas (pesos + condiciones sobre el perfil) puntúan las 5 categorías del
catálogo y devuelven un **ranking con razones** (`code`/`label`/`evidence`) — el
LLM solo relata lo que el motor decidió. Determinista, testeado y auditado por un
log JSON por evaluación. Dos ejemplos:

- `casa · 26-40 · urbana · estrato 3` → **Hogar Estándar** (0.70): propietario +
  capacidad económica + zona urbana.
- El mismo perfil dice **"tengo carro"** → el ranking se voltea: **Auto Todo
  Riesgo** (0.75) y la primera razón cita el vehículo declarado.

📖 **Lógica completa, las 16 reglas y 4 ejemplos calculados:
[docs/propension.md](docs/propension.md)**

## Arquitectura

```mermaid
flowchart TB
    Cliente(["👤 Cliente<br/>(afiliado o no afiliado)"])

    subgraph Canales["Canales — adaptador delgado por canal"]
        Web["💬 Chat web (Vue)"]
        WA["📱 WhatsApp (YCloud / Meta)"]
        TG["✈️ Telegram"]
    end

    Cliente --> Web & WA & TG

    subgraph Backend["Backend FastAPI (Dokploy/VPS + Postgres)"]
        Orq["🤖 Orquestador conversacional<br/>Gemini + tool-use<br/>texto y notas de voz"]

        subgraph Tools["Herramientas del agente"]
            T1["perfilar_cliente()"]
            T2["recomendar_seguro()"]
            T3["cotizar()"]
            T4["ajustar_comparar()"]
            T5["cerrar_venta()"]
        end

        Prop["⚙️ Motor de propensión<br/>16 reglas explicables<br/>ranking + razones — no caja negra"]
        Tarifas["💰 Motor de tarifas<br/>determinista"]
        Catalogo[("📚 Catálogo JSON<br/>5 categorías<br/>versionado en repo")]
        Perfiles[("👥 Tabla afiliados (Postgres)<br/>base real 500k por SERIE<br/>+ complemento sintético sint_*")]
        Registro[("📝 Conversaciones y solicitudes<br/>persistidas — evidencia trazable")]
    end

    Web & WA & TG --> Orq
    Orq --> Tools
    T1 --> Perfiles
    T2 --> Prop
    T3 & T4 --> Tarifas
    Tarifas --> Catalogo
    Prop --> Catalogo
    Orq --> Registro

    T5 --> Cierre["✅ Solicitud lista con consentimiento<br/>★ pasarela de pago fuera del alcance"]
    Cierre --> Notif["📧 Handoff por correo (Resend)<br/>link a la página de la<br/>aseguradora (simulada)"]

    Cierre -.en producción: API aseguradora + pasarela.-> Prod["🏭 Punto de integración real"]
    classDef fuera stroke-dasharray: 5 5
    class Prod fuera
```

## Deploy (Dokploy)

Ambos proyectos se despliegan en **Dokploy**:

- **Backend** — Application con build type **Nixpacks** (lee
  [backend/Procfile](backend/Procfile)); puerto del contenedor `8000`; health
  check path `/api/v1/health`; env vars según
  [backend/.env.example](backend/.env.example) (`BACKEND_PUBLIC_URL` = dominio
  HTTPS asignado; `DATABASE_URL` = servicio Postgres creado en Dokploy). Tras el
  deploy, re-apuntar los webhooks de YCloud/Meta al dominio nuevo y re-registrar
  el de Telegram (`POST /api/v1/webhooks/telegram/set`).
- **Frontend** — build type **Dockerfile** (lee
  [frontend/Dockerfile](frontend/Dockerfile), root `frontend/`); puerto del
  contenedor `80`; health check path `/`. El
  [frontend/nginx.conf](frontend/nginx.conf) hace el **fallback de SPA**
  (`try_files → index.html`), así las rutas directas (`/panel`,
  `/aseguradora/{token}` — el link del correo de handoff) funcionan al abrirse o
  refrescar. ⚠️ `VITE_API_URL` se inyecta **en build time** como *build arg* del
  Dockerfile (rebuildar si cambia).
- **Ruteo de dominios** (elige uno):
  - **Same-domain (recomendado, cero CORS)**: un solo dominio; en Dokploy, el
    backend con path `/api/v1` y el front como raíz. Build arg `VITE_API_URL`
    **vacío** (paths relativos).
  - **Subdominios**: `VITE_API_URL=https://api.<dominio>` en el build del front y
    `FRONTEND_URL=https://<front>` en el backend (CORS).

## Roadmap — 3 meses de piloto

1. **Semanas 1–8 · Piloto acotado**: un producto de cotización instantánea
   (acuerdo directo con la aseguradora, sin broker), un canal, tráfico limitado y
   un humano supervisando transcripciones (la evidencia ya queda persistida).
2. **Validación**: comparar conversión y calidad de asesoría contra el canal
   humano actual con métricas del panel.
3. **Escala**: portafolio completo — incluidos productos que hoy pasan por broker
   (PólizIA media: recibe la cotización, la comunica y avisa al broker para
   emitir), integración con la aseguradora vía API y campañas dirigidas por
   segmento sobre la base de afiliados.

## Cómo se construyó — repo compañero

Este proyecto se trabajó de la mano con
**[zubcarz/colsubsidio-brain](https://github.com/zubcarz/colsubsidio-brain)**: el
"segundo cerebro" del reto (vault de Obsidian) donde vive todo el trabajo
no-código — análisis del enunciado y de la base real de afiliados, registro de
decisiones (DEC-001…DEC-009), matriz de perfilamiento por categoría, modelo de
negocio, material del pitch y el tablero de tareas por feature (A…H).

Cada plan de implementación de
[.claude/analysis/plans/](.claude/analysis/plans/) nace de una tarea de ese
vault: la trazabilidad **idea → decisión → tarea → plan → commit** es parte del
entregable.

## Desarrollo

- Cada paquete (`backend/`, `frontend/`) tiene su propio README con instrucciones
  detalladas.
- Contribuciones vía pull request hacia `master`; commits bajo
  [Conventional Commits](.claude/rules/commit-standards.md) (hook `commit-msg`
  los valida).
- **Trabajo con IA (Claude Code, Codex, gentle-ai)**: ver
  [README-IA.md](README-IA.md) — flujo homologado de planes por fases, reglas y
  setup por herramienta.

## Licencia

Distribuido bajo licencia [MIT](LICENSE).

## Agradecimientos

- A los **mentores del reto** por las sesiones de seguros (el modelo de mediación
  con broker del roadmap salió de ahí).
- A **Colsubsidio** por la base anonimizada de afiliados que calibra el motor y
  por el contexto real del portafolio.
