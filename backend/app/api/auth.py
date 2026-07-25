"""
Auth routes — sign up, log in, and "who am I".

    POST /api/auth/signup   create account → returns a token (auto-logged-in)
    POST /api/auth/login    email + password → returns a token
    GET  /api/auth/me       the logged-in account (proves the token works)

Thin: validate (schemas already did), call the accounts service, sign a token.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.db import get_db
from app.models.account import Account
from app.schemas.auth import AccountOut, LoginIn, SignupIn, TokenOut
from app.security import create_access_token
from app.services import accounts as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: Session = Depends(get_db)) -> TokenOut:
    """Create a seller account and log them straight in (return a token)."""
    try:
        account = svc.create_account(db, body.name, body.email, body.phone, body.password)
    except svc.AccountError as e:
        # 409 Conflict: the request was well-formed but clashes with an existing
        # account (duplicate email/phone). Bad email/phone shapes were already
        # rejected as 422 by the schema.
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return TokenOut(access_token=create_access_token(str(account.id)))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    """Exchange email + password for a token."""
    account = svc.authenticate(db, body.email, body.password)
    if account is None:
        # ONE message for both 'no such email' and 'wrong password' — never
        # reveal which accounts exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return TokenOut(access_token=create_access_token(str(account.id)))


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)) -> Account:
    """Return the caller's own account. Also the frontend's 'am I logged in?'
    check — a 200 means the stored token is still valid."""
    return account
