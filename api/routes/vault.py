"""
Credential Vault API routes — auth-gated, display-only.

POST /vault/unlock              - unlock vault (master password in body, NOT logged)
POST /vault/lock                - lock vault
GET  /vault/credentials         - list all credentials (summaries — no secrets)
GET  /vault/credentials/search  - search credentials (summaries)
POST /vault/credentials         - add a new credential
GET  /vault/credentials/{id}    - get a credential summary (NOT the secret)
DELETE /vault/credentials/{id}  - soft-delete
POST /vault/credentials/{id}/totp - get current TOTP code (display only)
GET  /vault/health              - credential health report
POST /vault/generate-password   - generate a strong random password

SECURITY INVARIANTS:
1. No route in this file ever returns credential secrets in a response body.
2. The master password is accepted in a request body and is NEVER logged or stored.
3. TOTP codes are returned as display-only strings — the caller must not send them to TTS.
4. Every vault operation is logged to vault_audit.log via CredentialVault internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from observability.logger import get_logger
from security.vault.models import Credential, CredentialType
from security.vault.vault import CredentialVault, VaultLockedError

log = get_logger(__name__)

router = APIRouter(prefix="/vault", tags=["vault"])


# ---------------------------------------------------------------------------
# Dependency: shared CredentialVault instance (wired via app.state)
# ---------------------------------------------------------------------------


def _get_vault() -> CredentialVault:
    """Placeholder — overridden by app.state dependency injection."""
    raise RuntimeError("CredentialVault not wired into API dependencies")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


# UUID v4 pattern for credential_id path param
CREDENTIAL_ID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

# Max lengths for request body fields (input validation)
_MAX_STR = 2048
_MAX_SECRET = 4096


class UnlockRequest(BaseModel):
    """Vault unlock request. Master password is used in-memory only."""

    master_password: str = Field(..., min_length=1, max_length=_MAX_SECRET)


class AddCredentialRequest(BaseModel):
    """Request to add a new credential."""

    type: str = Field(default="PASSWORD", max_length=32)
    name: str = Field(..., min_length=1, max_length=_MAX_STR)
    service: str = Field(default="", max_length=_MAX_STR)
    username: str = Field(default="", max_length=_MAX_STR)
    secret: str = Field(..., min_length=1, max_length=_MAX_SECRET)
    totp_seed: str = Field(default="", max_length=256)
    url: str = Field(default="", max_length=_MAX_STR)
    tags: list[str] = Field(default_factory=list, max_length=64)
    notes: str = Field(default="", max_length=_MAX_SECRET)
    expiry_date: str | None = None


class GeneratePasswordRequest(BaseModel):
    """Password generation parameters."""

    length: int = Field(default=24, ge=12, le=128)
    use_symbols: bool = True
    use_digits: bool = True
    use_upper: bool = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/unlock")
async def unlock_vault(
    body: UnlockRequest,
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """
    Unlock the vault with the master password.

    The master password is consumed here and not logged or stored.
    Returns 200 on success.
    """
    try:
        success = await vault.unlock(body.master_password)
        if not success:
            raise HTTPException(status_code=401, detail="Vault unlock failed")
        return {"status": "unlocked"}
    except Exception as exc:
        log.error("vault_unlock_api_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Vault unlock error") from exc


@router.post("/lock")
async def lock_vault(
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """Lock the vault immediately."""
    await vault.lock()
    return {"status": "locked"}


@router.get("/status")
async def vault_status(
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, bool]:
    """Return whether the vault is currently unlocked."""
    return {"unlocked": vault.is_unlocked()}


@router.get("/credentials")
async def list_credentials(
    vault: CredentialVault = Depends(_get_vault),
) -> dict:
    """
    List all credentials as summaries. Secrets are NEVER included.
    """
    try:
        summaries = await vault.list_all()
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")

    return {
        "credentials": [
            {
                "id": s.id,
                "name": s.name,
                "service": s.service,
                "username": s.username,
                "type": s.type.value,
                "tags": s.tags,
                "password_strength": s.password_strength,
                "expiry_date": s.expiry_date,
                "last_accessed": s.last_accessed,
            }
            for s in summaries
        ]
    }


@router.get("/credentials/search")
async def search_credentials(
    q: str = "",
    vault: CredentialVault = Depends(_get_vault),
) -> dict:
    """Search credentials by name/service/username (no secrets in results)."""
    try:
        summaries = await vault.search(q)
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")

    return {
        "credentials": [
            {
                "id": s.id,
                "name": s.name,
                "service": s.service,
                "username": s.username,
                "type": s.type.value,
            }
            for s in summaries
        ]
    }


@router.post("/credentials", status_code=201)
async def add_credential(
    body: AddCredentialRequest,
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """Add a new credential. Secret is encrypted before storage."""
    try:
        cred_type = CredentialType(body.type.upper())
    except ValueError:
        cred_type = CredentialType.OTHER

    from security.vault.health_checker import PasswordStrengthScorer

    strength = PasswordStrengthScorer().score(body.secret)

    cred = Credential(
        type=cred_type,
        name=body.name,
        service=body.service,
        username=body.username,
        url=body.url,
        tags=body.tags,
        notes=body.notes,
        expiry_date=body.expiry_date,
        password_strength=strength,
    )

    try:
        cred_id = await vault.add(cred, plaintext_secret=body.secret)
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")

    return {"id": cred_id}


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: str = Path(..., pattern=CREDENTIAL_ID_PATTERN),
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """Soft-delete a credential."""
    try:
        await vault.delete(credential_id)
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")
    return {"status": "deleted", "id": credential_id}


@router.post("/credentials/{credential_id}/totp")
async def get_totp_code(
    credential_id: str = Path(..., pattern=CREDENTIAL_ID_PATTERN),
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """
    Return the current TOTP code for a credential.

    DISPLAY ONLY — this value must never be passed to TTS or LLM context.
    """
    try:
        code = await vault.get_totp(credential_id)
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"totp_code": code, "__display_only": True}


@router.get("/health")
async def credential_health(
    vault: CredentialVault = Depends(_get_vault),
) -> dict:
    """Run credential health checks (no secrets in results)."""
    try:
        report = await vault.health_report()
    except VaultLockedError:
        raise HTTPException(status_code=403, detail="Vault is locked")

    return {"alerts": report, "count": len(report)}


@router.post("/generate-password")
async def generate_password(
    body: GeneratePasswordRequest,
    vault: CredentialVault = Depends(_get_vault),
) -> dict[str, str]:
    """Generate a cryptographically secure random password."""
    if not vault.is_unlocked():
        raise HTTPException(status_code=403, detail="Vault is locked")

    pw = await vault.generate_password(
        length=body.length,
        use_symbols=body.use_symbols,
        use_digits=body.use_digits,
        use_upper=body.use_upper,
    )
    return {"password": pw}
