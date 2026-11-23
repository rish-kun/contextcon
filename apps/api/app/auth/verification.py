"""Email verification for self-serve sign-up.

A new account gets a link `<web>/verify?token=<token>`. The token is 256 random bits;
only its SHA-256 is stored (`email_verification_tokens`), it expires after
`AUTH_VERIFICATION_TTL_HOURS` and it works once: using it deletes the row in the same
statement that reads it, so two concurrent uses cannot both succeed. Issuing a new link
replaces the user's older ones.

Email goes out through Resend (`RESEND_API_KEY` and `EMAIL_FROM`, the same settings as the
seller request). Without them (local dev) the email, link included, is written to the
server log instead. `EMAIL_SEND_ENABLED` does not apply here: it gates email to third
parties, while these go to the person who asked for them.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.act.resend import ResendClient
from app.auth.config import get_auth_settings
from app.auth.sessions import _now, hash_token
from app.db.models import EmailVerificationToken, User
from app.settings import get_settings

log = logging.getLogger("app.auth")


# --- Tokens -----------------------------------------------------------------------


async def issue_token(db: AsyncSession, user_id: uuid.UUID, *, ttl: timedelta) -> str:
    """A new raw token for `user_id`; older links of that user (and expired links of
    anyone) are deleted. Flushes."""
    now = _now()
    await db.execute(
        delete(EmailVerificationToken).where(
            or_(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.expires_at <= now,
            )
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(user_id=user_id, token_hash=hash_token(token), expires_at=now + ttl)
    )
    await db.flush()
    return token


async def consume_token(db: AsyncSession, token: str) -> User | None:
    """The user a live token belongs to, now verified, or None if the token is unknown,
    expired or already used. The token cannot be used again. Flushes."""
    if not token:
        return None
    used = await db.execute(
        delete(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash == hash_token(token),
            EmailVerificationToken.expires_at > _now(),
        )
        .returning(EmailVerificationToken.user_id)
    )
    user_id = used.scalar_one_or_none()
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:  # pragma: no cover - the FK cascades tokens with their user
        return None
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    await db.execute(
        delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
    )
    await db.flush()
    return user


# --- Email ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    kind: str  # tag value: [A-Za-z0-9_-]
    idempotency_key: str


class Mailer(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


class LogMailer:
    """Local dev: the email is written to the server log, so the link can be copied."""

    async def send(self, email: OutgoingEmail) -> None:
        level = logging.ERROR if get_auth_settings().on_cloud_run else logging.WARNING
        log.log(
            level,
            "Email not sent (RESEND_API_KEY or EMAIL_FROM is unset). To: %s\nSubject: %s\n\n%s",
            email.to,
            email.subject,
            email.text,
        )


class ResendMailer:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(self, email: OutgoingEmail) -> None:
        client = ResendClient(self._api_key)
        try:
            result = await client.send_email(
                idempotency_key=email.idempotency_key,
                sender=self._sender,
                to=email.to,
                subject=email.subject,
                text=email.text,
                tags={"dealproof_kind": email.kind},
            )
        finally:
            await client.aclose()
        if result.outcome != "accepted":
            # The person can ask for a new link; nothing else depends on this email.
            log.warning(
                "%s email to %s: %s (%s)", email.kind, email.to, result.outcome, result.error
            )


def get_mailer() -> Mailer:
    settings = get_settings()
    key = settings.resend_api_key.get_secret_value()
    if key and settings.email_from:
        return ResendMailer(key, settings.email_from)
    if key:
        log.warning("RESEND_API_KEY is set but EMAIL_FROM is not; auth emails go to the log")
    return LogMailer()


def web_url(path: str) -> str:
    base = get_auth_settings().public_web_url.strip()
    if not base:
        origins = get_settings().cors_origins
        base = origins[0] if origins else "http://localhost:3000"
    return f"{base.rstrip('/')}{path}"


async def send_verification_email(
    to: str, display_name: str, token: str, *, ttl: timedelta
) -> None:
    link = web_url(f"/verify?token={token}")
    hours = max(1, round(ttl.total_seconds() / 3600))
    text = (
        f"Hello {display_name},\n\n"
        "Confirm your email address to finish creating your DealProof account:\n\n"
        f"{link}\n\n"
        f"The link works once and expires in {hours} hours. If you did not sign up for "
        "DealProof, ignore this email: the account stays switched off until the link is used.\n"
    )
    await get_mailer().send(
        OutgoingEmail(
            to=to,
            subject="Confirm your email for DealProof",
            text=text,
            kind="verify_email",
            idempotency_key=f"verify-email-{hash_token(token)}",
        )
    )


async def send_existing_account_email(to: str, display_name: str) -> None:
    text = (
        f"Hello {display_name},\n\n"
        "Someone tried to create a DealProof account with this email address. You already "
        "have one, so nothing was created and nothing about your account changed.\n\n"
        f"Log in here: {web_url('/login')}\n\n"
        "If you have forgotten your password, ask the person who runs DealProof for your "
        "team to reset it. If this was not you, you can ignore this email.\n"
    )
    await get_mailer().send(
        OutgoingEmail(
            to=to,
            subject="You already have a DealProof account",
            text=text,
            kind="existing_account",
            idempotency_key=f"existing-account-{uuid.uuid4().hex}",
        )
    )
