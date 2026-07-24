"""Conversation API router.

Thin layer: validates input via schemas, delegates to ConversationService,
returns the response. No business logic here.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.conversation import (
    ConsentRequest,
    ConsentedApplication,
    ConversationCreate,
    ConversationResponse,
    ProfileData,
)
from app.services.conversation import ConversationService

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
_service = ConversationService()


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(body: ConversationCreate):
    return _service.create(body)


@router.get("/{session_id}", response_model=ConversationResponse)
async def get_conversation(session_id: str):
    session = _service.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/profile", response_model=ConversationResponse)
async def update_profile(session_id: str, profile: ProfileData):
    try:
        return _service.update_profile(session_id, profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/accept", response_model=ConversationResponse)
async def accept_quote(session_id: str):
    try:
        return _service.accept_quote(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/consent", response_model=ConsentedApplication)
async def submit_consent(session_id: str, consent: ConsentRequest):
    try:
        return _service.submit_consent(session_id, consent.consent_given)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
