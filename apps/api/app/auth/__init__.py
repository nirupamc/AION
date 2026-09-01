"""Persistence helpers for MusicAccount and OAuthToken."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MusicAccount, OAuthToken


def upsert_account(
    session: Session,
    *,
    provider: str,
    provider_user_id: str,
    display_name: Optional[str] = None,
) -> MusicAccount:
    account = session.execute(
        select(MusicAccount).where(
            MusicAccount.provider == provider,
            MusicAccount.provider_user_id == provider_user_id,
        )
    ).scalar_one_or_none()
    if account is None:
        account = MusicAccount(
            provider=provider,
            provider_user_id=provider_user_id,
            display_name=display_name,
        )
        session.add(account)
        session.flush()
    elif display_name and account.display_name != display_name:
        account.display_name = display_name
    return account


def upsert_token(
    session: Session,
    *,
    account: MusicAccount,
    access_token: str,
    refresh_token: Optional[str],
    token_type: str,
    scope: Optional[str],
    expires_in: Optional[int],
) -> OAuthToken:
    token = session.execute(
        select(OAuthToken).where(OAuthToken.account_id == account.id)
    ).scalar_one_or_none()
    if token is None:
        token = OAuthToken(account_id=account.id)
        session.add(token)
    token.access_token = access_token
    if refresh_token:
        token.refresh_token = refresh_token
    token.token_type = token_type
    token.scope = scope
    if expires_in is not None:
        token.expires_at = datetime.now(timezone.utc).timestamp() + expires_in
        token.expires_at = datetime.fromtimestamp(
            token.expires_at, tz=timezone.utc
        )
    session.flush()
    return token


def get_token(session: Session, account: MusicAccount) -> Optional[OAuthToken]:
    return session.execute(
        select(OAuthToken).where(OAuthToken.account_id == account.id)
    ).scalar_one_or_none()
