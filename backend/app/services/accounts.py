"""
Accounts service — create + authenticate sellers. The security-critical core.

Rules enforced here (with the DB's UNIQUE constraints as the final backstop):
  - emails are stored lower-cased and unique
  - phones are stored canonical (2547…) and unique
  - passwords are Argon2id-hashed, never stored in the clear
  - a failed login says the SAME thing whether the email is unknown or the
    password is wrong — never leak which accounts exist
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Account
from app.security import hash_password, verify_password


class AccountError(Exception):
    """A signup/business-rule failure with a message safe to show a human."""


def create_account(db: Session, name: str, email: str, phone: str, password: str) -> Account:
    """Create a seller account. `phone` is already normalized by the schema;
    `email` we lower-case here. Uniqueness is checked for a friendly message
    AND guarded by the DB (the IntegrityError catch handles the race where two
    signups pass the check at once)."""
    email = email.strip().lower()

    if db.scalar(select(Account).where(Account.email == email)):
        raise AccountError("An account with this email already exists.")
    if db.scalar(select(Account).where(Account.phone == phone)):
        raise AccountError("An account with this phone number already exists.")

    account = Account(
        name=name.strip(),
        email=email,
        phone=phone,
        password_hash=hash_password(password),  # plaintext dies here — never stored
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race: another signup inserted the same email/phone first.
        db.rollback()
        raise AccountError("An account with this email or phone already exists.")
    db.refresh(account)
    return account


def authenticate(db: Session, email: str, password: str) -> Account | None:
    """Return the account iff email+password match, else None.

    We verify a password even when the email is unknown-ish? No — a simple
    lookup is fine here; the important anti-enumeration guarantee is that the
    ROUTE returns one identical 401 for both 'no such email' and 'wrong
    password'. We just return None for both cases and let the route speak."""
    email = email.strip().lower()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None:
        return None
    if not verify_password(password, account.password_hash):
        return None
    return account
