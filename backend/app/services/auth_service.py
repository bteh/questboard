"""Hosted bearer-token authentication for Supabase-backed deployments."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
import uuid

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.workspace import Profile, Workspace, WorkspaceMembership
from app.services.workspace_naming import allocate_workspace_slug, ensure_workspace_identity


@dataclass
class HostedUser:
    user_id: str
    email: str
    full_name: str
    avatar_url: str
    auth_provider: str
    email_verified: bool
    claims: dict[str, Any]


def _settings_error(detail: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


def _auth_error(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _issuer() -> str:
    settings = get_settings()
    if not settings.supabase_url:
        raise _settings_error("Supabase auth is not configured")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _unverified_issuer(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "verify_aud": False,
                "verify_iss": False,
            },
            algorithms=["HS256", "RS256", "ES256"],
        )
    except jwt.PyJWTError:
        return ""
    return str(claims.get("iss") or "").strip()


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def _audiences() -> list[str]:
    settings = get_settings()
    raw = settings.supabase_jwt_audience.strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise _auth_error()
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _auth_error()
    return token.strip()


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.dev_hosted_auth_enabled:
        from app.services import dev_auth_service

        issuer_hint = _unverified_issuer(token)
        if not settings.supabase_url or issuer_hint == settings.resolved_dev_hosted_auth_issuer:
            return dev_auth_service.decode_access_token(token)

    issuer = _issuer()
    audiences = _audiences()
    decode_kwargs: dict[str, Any] = {
        "issuer": issuer,
        "algorithms": ["HS256", "RS256", "ES256"],
        "options": {"require": ["sub", "exp", "iss"]},
        "leeway": 30,
    }
    if audiences:
        decode_kwargs["audience"] = audiences if len(audiences) > 1 else audiences[0]
    else:
        decode_kwargs["options"] = {
            **decode_kwargs["options"],
            "verify_aud": False,
        }

    try:
        if settings.supabase_jwt_secret:
            return jwt.decode(token, settings.supabase_jwt_secret, **decode_kwargs)

        jwks_url = settings.resolved_supabase_jwks_url
        if not jwks_url:
            raise _settings_error("Supabase JWKS is not configured")
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, **decode_kwargs)
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise _auth_error(f"Invalid access token: {exc}") from exc


def _identity_provider(claims: dict[str, Any]) -> str:
    app_metadata = claims.get("app_metadata") or {}
    if isinstance(app_metadata, dict) and app_metadata.get("provider"):
        return str(app_metadata["provider"])
    identities = claims.get("identities") or []
    if isinstance(identities, list) and identities:
        provider = identities[0].get("provider")
        if provider:
            return str(provider)
    return "supabase"


def user_from_claims(claims: dict[str, Any]) -> HostedUser:
    metadata = claims.get("user_metadata") or {}
    email = str(claims.get("email") or metadata.get("email") or "").strip()
    full_name = (
        metadata.get("full_name")
        or metadata.get("name")
        or claims.get("full_name")
        or email.split("@")[0]
        or "Launchboard User"
    )
    avatar_url = str(metadata.get("avatar_url") or metadata.get("picture") or "").strip()
    return HostedUser(
        user_id=str(claims.get("sub") or "").strip(),
        email=email,
        full_name=str(full_name).strip(),
        avatar_url=avatar_url,
        auth_provider=_identity_provider(claims),
        email_verified=bool(claims.get("email_confirmed_at") or claims.get("email_verified")),
        claims=claims,
    )


def authenticate_request(authorization_header: str | None) -> HostedUser:
    token = extract_bearer_token(authorization_header)
    claims = decode_access_token(token)
    user = user_from_claims(claims)
    if not user.user_id:
        raise _auth_error("Access token missing subject")
    return user


def ensure_profile_and_workspace(db: Session, user: HostedUser) -> tuple[Profile, Workspace, WorkspaceMembership]:
    profile = db.query(Profile).filter(Profile.id == user.user_id).first()
    if not profile:
        profile = Profile(id=user.user_id)
        db.add(profile)

    profile.email = user.email
    profile.full_name = user.full_name
    profile.avatar_url = user.avatar_url
    profile.auth_provider = user.auth_provider
    profile.email_verified = bool(user.email_verified)

    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.user_id,
            WorkspaceMembership.is_default == True,  # noqa: E712
        )
        .first()
    )

    workspace = None
    if membership:
        workspace = db.query(Workspace).filter(Workspace.id == membership.workspace_id).first()

    if not workspace:
        workspace_name = f"{user.full_name}'s workspace".strip() or "Workspace"
        workspace = Workspace(
            id=uuid.uuid4().hex,
            owner_user_id=user.user_id,
            name=workspace_name,
            slug=allocate_workspace_slug(db, user.email or user.full_name or user.user_id),
            mode="personal",
            plan=profile.plan or "free",
            subscription_status=profile.subscription_status or "inactive",
        )
        db.add(workspace)
        db.flush()
        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.user_id,
            role="owner",
            is_default=True,
        )
        db.add(membership)
    else:
        workspace.owner_user_id = user.user_id
        workspace.plan = profile.plan or workspace.plan or "free"
        workspace.subscription_status = profile.subscription_status or workspace.subscription_status or "inactive"
        ensure_workspace_identity(
            db,
            workspace,
            label=user.email or user.full_name or user.user_id,
            fallback_name=f"{user.full_name}'s workspace".strip() or "Workspace",
        )

    db.commit()
    db.refresh(profile)
    db.refresh(workspace)
    db.refresh(membership)
    return profile, workspace, membership
