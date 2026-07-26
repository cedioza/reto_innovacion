"""Script de siembra de datos de demo para el panel (H4).

Crea 7 conversaciones sintéticas con prefijo reservado `seed-demo-` — 5
"ventas" cerradas (una por categoría del catálogo: hogar, vida, accidentes,
movilidad, crédito) que terminan en solicitud finalizada (`finalizada_demo`,
con `ConsentedApplication` asociada) y 2 conversaciones "en curso" (una en
`quote_ready`, otra en `awaiting_consent`) que se quedan a medio camino, sin
solicitud. El prefijo `seed-demo-` está reservado: nunca debe usarlo una
conversación real (las reales llevan `uuid4()`, ver
`ConversationService.create`), así que sirve para identificar de forma
inequívoca qué filas son de demo y poder limpiarlas o re-sembrarlas sin
arriesgar datos reales — de ahí el chequeo `LIKE 'seed-demo-%'` antes de
escribir y el `--replace` que solo borra filas con ese prefijo.

Todas las ventas se capturan con `email=None`: son datos de demo para el
panel, no personas reales con bandeja de entrada, así que nunca deben
disparar el correo de comprobante de `ConsentService.capture` (que solo se
dispara si hay `email`).

Las conversaciones se calculan con los mismos motores deterministas que usa
el flujo real (`PropensityService.evaluate` / `QuoteService.calculate_quote`)
para que la recomendación y la cotización de cada conversación sembrada sean
coherentes con lo que el motor produciría hoy para ese mismo perfil — no son
literales inventados a mano.

Los `ConversationRecord` de las 7 conversaciones se escriben DIRECTO con una
`Session` de SQLModel (no vía `ConversationRepository.save`, que siempre fija
`created_at=now`) para poder escalonar `created_at`/`updated_at` hacia atrás,
dentro de las últimas ~24h, y que el panel muestre una línea de tiempo
creíble en vez de 7 filas con el mismo instante. Mismo precedente que
`app.scripts.cargar_afiliados` escribiendo `AffiliateRecord` directo.

Nota importante sobre el engine: `ConsentService` (usado para capturar y
finalizar las 5 ventas) resuelve su `ApplicationRepository` internamente sin
recibir un engine explícito, así que SIEMPRE cae al engine global
(`app.repositories.db.get_engine()`). Este script por lo tanto asume que el
`engine` que recibe `sembrar()` (o `None`, en cuyo caso también se resuelve
vía `db.get_engine()`) ES el engine global — en producción esto es cierto
por construcción (hay un único engine global); en tests, la fixture
parchea `db.get_engine` para que devuelva el engine de prueba antes de
llamar a `sembrar()`, así que el supuesto también se cumple ahí.

Uso (desde `backend/`, con el venv activo):

    python -m app.scripts.seed_demo [--replace]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, delete
from sqlmodel import Session, select

from app.models.application import ApplicationRecord
from app.models.conversation import ConversationRecord
from app.repositories import db
from app.services.catalog import CatalogService
from app.services.consent import ConsentService
from app.services.propensity import PropensityService
from app.services.quote import QuoteService
from app.schemas.conversation import (
    ConversationResponse,
    ConversationState,
    Message,
    ProfileData,
    QuoteDetail,
    Recommendation,
)

SEED_PREFIX = "seed-demo-"

_NEXT_ACTION_QUOTE_READY = "Revisá la cotización y coberturas, podés ajustar las opciones"
_NEXT_ACTION_AWAITING_CONSENT = "Dá tu consentimiento para generar la solicitud"
_NEXT_ACTION_FINALIZED = "Tu solicitud quedó lista para pago con la aseguradora"


def _propensity() -> PropensityService:
    return PropensityService()


def _quote_service() -> QuoteService:
    return QuoteService()


def _catalog() -> CatalogService:
    return CatalogService()


def _recomendar(profile: ProfileData) -> tuple[Recommendation, QuoteDetail]:
    """Evalúa `profile` con los motores reales y arma recomendación + cotización."""
    resultado = _propensity().evaluate(profile)
    product_id = resultado["product_id"]
    product = _catalog().get_product(product_id)
    product_name = product.name if product else product_id

    recommendation = Recommendation(
        product_id=product_id,
        product_name=product_name,
        reasons=resultado["reasons"],
    )

    quote_data = _quote_service().calculate_quote(profile, product_id=product_id)
    quote = QuoteDetail(**quote_data)

    return recommendation, quote


def _timestamped_messages(
    pares: list[tuple[str, str]], created_at: datetime
) -> list[Message]:
    """Arma `Message`s con timestamp explícito, coherente con `created_at`.

    Cada mensaje queda 2 minutos después del anterior, empezando en
    `created_at`, para que la conversación se vea como un intercambio real en
    el tiempo (no todos los mensajes en el mismo instante).
    """
    mensajes: list[Message] = []
    for i, (role, content) in enumerate(pares):
        timestamp = (created_at + timedelta(minutes=2 * i)).isoformat()
        mensajes.append(Message(role=role, content=content, timestamp=timestamp))
    return mensajes


# -- Datos de las 5 ventas (una por categoría del catálogo) -----------------

_VENTAS = [
    {
        "session_id": f"{SEED_PREFIX}hogar",
        "horas_atras": 23,
        "profile": ProfileData(
            property_type="house", stratum=3, zone="urban", age_range="26-40"
        ),
        "guion": lambda product_name, premium: [
            ("user", "Hola, quiero asegurar mi casa. Vivo en zona urbana, estrato 3."),
            ("assistant", "Con gusto te ayudo. ¿Tienes entre 26 y 40 años?"),
            ("user", "Sí, tengo 34 años."),
            (
                "assistant",
                f"Perfecto, te recomiendo **{product_name}**: es ideal para "
                f"propietarios en zona urbana. Tu prima mensual estimada es "
                f"${premium:,.0f} COP.",
            ),
            ("user", "Me interesa, quiero continuar con la solicitud."),
            (
                "assistant",
                "¡Listo! Tu solicitud quedó registrada y lista para pago con "
                "la aseguradora.",
            ),
        ],
    },
    {
        "session_id": f"{SEED_PREFIX}vida",
        "horas_atras": 20,
        "profile": ProfileData(
            has_children=True, has_family=True, age_range="26-40"
        ),
        "guion": lambda product_name, premium: [
            ("user", "Hola, tengo dos hijos y quiero protegerlos con un seguro de vida."),
            ("assistant", "Entiendo, cuéntame un poco más de tu situación familiar."),
            ("user", "Tengo familia a cargo y estoy en mis 30."),
            (
                "assistant",
                f"Te recomiendo **{product_name}**, pensado para proteger a "
                f"tu familia. La prima mensual estimada es ${premium:,.0f} COP.",
            ),
            ("user", "Quiero seguir con la solicitud."),
            (
                "assistant",
                "¡Listo! Tu solicitud quedó registrada y lista para pago con "
                "la aseguradora.",
            ),
        ],
    },
    {
        "session_id": f"{SEED_PREFIX}accidentes",
        "horas_atras": 17,
        "profile": ProfileData(
            age_range="18-25", zone="urban", has_children=False, has_family=False
        ),
        "guion": lambda product_name, premium: [
            (
                "user",
                "Hola, tengo 22 años y vivo en la ciudad. No tengo hijos ni "
                "familia a cargo.",
            ),
            ("assistant", "Perfecto, cuéntame si te movilizas mucho en zona urbana."),
            ("user", "Sí, salgo bastante, uso transporte público y bici."),
            (
                "assistant",
                f"Con ese perfil te recomiendo **{product_name}**, cubre "
                f"accidentes personales. Tu prima mensual estimada es "
                f"${premium:,.0f} COP.",
            ),
            ("user", "Me interesa, sigamos con la solicitud."),
            (
                "assistant",
                "¡Listo! Tu solicitud quedó registrada y lista para pago con "
                "la aseguradora.",
            ),
        ],
    },
    {
        "session_id": f"{SEED_PREFIX}movilidad",
        "horas_atras": 14,
        "profile": ProfileData(has_vehicle=True, age_range="26-40"),
        "guion": lambda product_name, premium: [
            ("user", "Hola, tengo carro propio y quiero asegurarlo."),
            ("assistant", "Genial, ¿qué edad tienes?"),
            ("user", "Tengo 30 años."),
            (
                "assistant",
                f"Te recomiendo **{product_name}** para proteger tu vehículo. "
                f"Tu prima mensual estimada es ${premium:,.0f} COP.",
            ),
            ("user", "Quiero continuar con la solicitud."),
            (
                "assistant",
                "¡Listo! Tu solicitud quedó registrada y lista para pago con "
                "la aseguradora.",
            ),
        ],
    },
    {
        "session_id": f"{SEED_PREFIX}credito",
        "horas_atras": 11,
        "profile": ProfileData(has_credit=True, age_range="41-55"),
        "guion": lambda product_name, premium: [
            ("user", "Hola, tengo un crédito vigente y quiero protegerlo."),
            ("assistant", "Entiendo, ¿qué edad tienes?"),
            ("user", "Tengo 45 años."),
            (
                "assistant",
                f"Te recomiendo **{product_name}** para cubrir tu obligación "
                f"crediticia. Tu prima mensual estimada es ${premium:,.0f} COP.",
            ),
            ("user", "Sigamos con la solicitud."),
            (
                "assistant",
                "¡Listo! Tu solicitud quedó registrada y lista para pago con "
                "la aseguradora.",
            ),
        ],
    },
]

# -- Datos de las 2 conversaciones "en curso" (sin solicitud) ----------------

_EN_CURSO = [
    {
        "session_id": f"{SEED_PREFIX}en-curso-1",
        "horas_atras": 6,
        "estado": ConversationState.QUOTE_READY,
        "next_action": _NEXT_ACTION_QUOTE_READY,
        "profile": ProfileData(
            property_type="apartment", stratum=4, zone="urban", age_range="41-55"
        ),
        "guion": lambda product_name, premium: [
            ("user", "Hola, quiero cotizar un seguro para mi apartamento."),
            ("assistant", "Claro, cuéntame el estrato y la zona."),
            ("user", "Estrato 4, zona urbana, tengo 45 años."),
            (
                "assistant",
                f"Te recomiendo **{product_name}**. Tu prima mensual estimada "
                f"es ${premium:,.0f} COP. ¿Quieres ver los detalles de "
                "cobertura o ajustar algo?",
            ),
        ],
    },
    {
        "session_id": f"{SEED_PREFIX}en-curso-2",
        "horas_atras": 3,
        "estado": ConversationState.AWAITING_CONSENT,
        "next_action": _NEXT_ACTION_AWAITING_CONSENT,
        "profile": ProfileData(
            has_children=True, has_family=True, age_range="41-55"
        ),
        "guion": lambda product_name, premium: [
            ("user", "Hola, quiero un seguro de vida para proteger a mi familia."),
            ("assistant", "Cuéntame más sobre tu situación familiar."),
            ("user", "Tengo hijos y familia a cargo, tengo 50 años."),
            (
                "assistant",
                f"Te recomiendo **{product_name}**. Tu prima mensual estimada "
                f"es ${premium:,.0f} COP.",
            ),
            (
                "assistant",
                "Para continuar necesitamos tu consentimiento. ¿Confirmas que "
                "entiendes las coberturas y exclusiones y quieres dejar tu "
                "solicitud lista para pago?",
            ),
        ],
    },
]


def _existing_seed_ids(engine: Engine) -> set[str]:
    """IDs con prefijo `seed-demo-` ya presentes en `conversaciones` o `solicitudes`."""
    with Session(engine) as session:
        conv_ids = session.exec(
            select(ConversationRecord.session_id).where(
                ConversationRecord.session_id.like(f"{SEED_PREFIX}%")
            )
        ).all()
        app_ids = session.exec(
            select(ApplicationRecord.session_id).where(
                ApplicationRecord.session_id.like(f"{SEED_PREFIX}%")
            )
        ).all()
    return set(conv_ids) | set(app_ids)


def _borrar_seed_previo(engine: Engine) -> None:
    """Borra SOLO filas con `session_id LIKE 'seed-demo-%'` de ambas tablas."""
    with engine.begin() as conn:
        conn.execute(
            delete(ConversationRecord).where(
                ConversationRecord.session_id.like(f"{SEED_PREFIX}%")
            )
        )
        conn.execute(
            delete(ApplicationRecord).where(
                ApplicationRecord.session_id.like(f"{SEED_PREFIX}%")
            )
        )


def sembrar(engine: Engine | None = None, replace: bool = False) -> dict:
    """Siembra las 7 conversaciones de demo (5 ventas + 2 en curso).

    Ver el docstring del módulo para el supuesto sobre `engine` (debe
    coincidir con el engine global que resuelve `ConsentService`).

    Devuelve `{"conversaciones": 7, "solicitudes": 5, "ids": [...]}`.
    """
    resolved_engine = engine or db.get_engine()
    db.init_db(resolved_engine)  # idempotente: create_all si no existen

    existentes = _existing_seed_ids(resolved_engine)
    if existentes and not replace:
        raise RuntimeError(
            "ya existen datos seed-demo-*; usa --replace para reemplazarlos"
        )

    if existentes and replace:
        _borrar_seed_previo(resolved_engine)

    ahora = datetime.now(timezone.utc)
    consent = ConsentService()

    ids: list[str] = []

    with Session(resolved_engine) as session:
        for venta in _VENTAS:
            session_id = venta["session_id"]
            profile: ProfileData = venta["profile"]
            created_at = ahora - timedelta(hours=venta["horas_atras"])

            recommendation, quote = _recomendar(profile)

            application = consent.capture(
                session_id=session_id,
                product_id=recommendation.product_id,
                profile=profile,
                recommendation=recommendation,
                quote=quote,
                email=None,
            )
            finalizada = consent.finalize_by_token(application.handoff_token)

            pares = venta["guion"](recommendation.product_name, quote.monthly_premium)
            messages = _timestamped_messages(pares, created_at)

            doc = ConversationResponse(
                session_id=session_id,
                state=ConversationState.FINALIZED_DEMO,
                messages=messages,
                profile=profile,
                recommendation=recommendation,
                quote=quote,
                application=finalizada,
                next_action=_NEXT_ACTION_FINALIZED,
            )

            record = ConversationRecord(
                session_id=session_id,
                canal=None,
                estado=doc.state.value,
                data=doc.model_dump(mode="json"),
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(record)
            ids.append(session_id)

        for en_curso in _EN_CURSO:
            session_id = en_curso["session_id"]
            profile: ProfileData = en_curso["profile"]
            created_at = ahora - timedelta(hours=en_curso["horas_atras"])

            recommendation, quote = _recomendar(profile)

            pares = en_curso["guion"](
                recommendation.product_name, quote.monthly_premium
            )
            messages = _timestamped_messages(pares, created_at)

            doc = ConversationResponse(
                session_id=session_id,
                state=en_curso["estado"],
                messages=messages,
                profile=profile,
                recommendation=recommendation,
                quote=quote,
                application=None,
                next_action=en_curso["next_action"],
            )

            record = ConversationRecord(
                session_id=session_id,
                canal=None,
                estado=doc.state.value,
                data=doc.model_dump(mode="json"),
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(record)
            ids.append(session_id)

        session.commit()

    return {
        "conversaciones": len(_VENTAS) + len(_EN_CURSO),
        "solicitudes": len(_VENTAS),
        "ids": ids,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Siembra 7 conversaciones de demo (5 ventas finalizadas + 2 en "
            "curso) con prefijo reservado `seed-demo-` para el panel."
        )
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Borra los datos `seed-demo-*` existentes antes de sembrar.",
    )
    args = parser.parse_args(argv)

    try:
        resumen = sembrar(replace=args.replace)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"conversaciones sembradas: {resumen['conversaciones']} | "
        f"solicitudes sembradas: {resumen['solicitudes']}"
    )
    print(f"ids: {', '.join(resumen['ids'])}")
    print(
        "recuerda: esto es data de demo para el panel; para re-sembrarla "
        "usa `python -m app.scripts.seed_demo --replace`."
    )


if __name__ == "__main__":
    main()
