"""Dev-only hosted auth routes for local multi-user sandboxing."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.dev_auth import (
    DevHostedLoginRequest,
    DevHostedLoginResponse,
    DevHostedPersonaSummary,
    DevHostedRegisterRequest,
    DevHostedRegisterResponse,
    DevHostedUserSummary,
)
from app.services import auth_service, dev_auth_service

router = APIRouter(prefix="/dev/auth", tags=["dev-auth"])


@router.get("/personas", response_model=list[DevHostedPersonaSummary])
def list_personas() -> list[DevHostedPersonaSummary]:
    return dev_auth_service.list_personas()


@router.post("/login", response_model=DevHostedLoginResponse)
def login(
    body: DevHostedLoginRequest,
    db: Session = Depends(get_db),
) -> DevHostedLoginResponse:
    persona = dev_auth_service.get_persona(body.persona_id)
    claims = {
        "sub": persona.id,
        "email": persona.email,
        "email_verified": True,
        "app_metadata": {"provider": "dev-sandbox"},
        "user_metadata": {
            "full_name": persona.full_name,
            "avatar_url": persona.avatar_url,
        },
    }
    user = auth_service.user_from_claims(claims)
    auth_service.ensure_profile_and_workspace(db, user)
    dev_auth_service.seed_persona_workspace(db, persona, reset=body.reset)
    token, expires_at = dev_auth_service.issue_access_token(persona)
    return DevHostedLoginResponse(
        access_token=token,
        expires_at=expires_at,
        persona=persona.summary(),
    )


@router.post("/register", response_model=DevHostedRegisterResponse)
def register(
    body: DevHostedRegisterRequest,
    db: Session = Depends(get_db),
) -> DevHostedRegisterResponse:
    user_id, email, full_name = dev_auth_service.provision_test_account(
        db,
        email=body.email,
        full_name=body.full_name,
        reset=body.reset,
    )
    token, expires_at = dev_auth_service.issue_access_token_for_user(
        user_id=user_id,
        email=email,
        full_name=full_name,
    )
    return DevHostedRegisterResponse(
        access_token=token,
        expires_at=expires_at,
        user=DevHostedUserSummary(
            id=user_id,
            email=email,
            full_name=full_name,
            auth_provider="dev-sandbox",
            seeded=False,
        ),
    )
