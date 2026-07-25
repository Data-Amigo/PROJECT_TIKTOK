"""
Shared route dependencies. The important one: `get_current_account` — the
gate that turns a Bearer token into a real, logged-in Account, or a 401.

Any protected endpoint just adds `account: Account = Depends(get_current_account)`
and is guaranteed a valid account or an automatic 401 — the auth check lives in
ONE place, not copy-pasted per route.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account
from app.security import decode_access_token

# auto_error=False → we raise our OWN 401 (consistent shape) instead of the
# default, and can tell "no token" apart from "bad token" if we ever need to.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_account(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Account:
    """Resolve the caller's account from their Bearer token, or 401.

    Every failure mode — missing token, bad signature, expired, or an account
    that was deleted after the token was issued — collapses to the same 401.
    We never say *why* in detail (that would help an attacker).
    """
    if creds is None:
        raise _UNAUTHORIZED
    try:
        payload = decode_access_token(creds.credentials)
        account_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED

    account = db.get(Account, account_id)
    if account is None:
        raise _UNAUTHORIZED
    return account
