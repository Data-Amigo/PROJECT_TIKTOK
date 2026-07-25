"""
Account — a seller's login. The private identity behind a public storefront.

Separation of concerns (deliberate):
    Account  — WHO logs in: name, email, phone, password hash. Never public.
    Seller   — the STOREFRONT: handle, display name, bio, avatar. Public.
The Seller gets an `account_id` link in the next step (2.2) — one account owns
one storefront. Keeping auth data out of the public Seller row means the
buyer-facing page can never accidentally leak an email or a password hash.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    # Login identity. Stored lower-cased (the service normalizes) and UNIQUE at
    # the DB level — two accounts can never share an email, no matter which code
    # path inserts. Indexed: every login looks up by email.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Canonical 2547XXXXXXXX (normalized at the border). UNIQUE so one person =
    # one account, and because this same number is what M-Pesa will pay out to.
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True)

    # Argon2id hash — NEVER the plaintext. Text, because argon2 hashes are long
    # and embed their own salt + parameters.
    password_hash: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # never include the hash in logs
        return f"<Account {self.email!r} (id={self.id})>"
