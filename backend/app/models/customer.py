"""
Customer — a buyer the sales chat captured (name + phone). (M5.2, lead capture)

The bot asks for a name and phone when a shopper wants to buy, and we store it
here. Two payoffs: the phone is what M-Pesa STK needs to charge them, and the
seller gets a real contact list (the seed of the Customers tab, M8).

One row per (seller, phone): the same person messaging twice updates their name,
never duplicates. Phone is canonical 2547XXXXXXXX (normalized at the border).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Customer(Base):
    __tablename__ = "customers"

    __table_args__ = (
        # One person (by phone) per shop — messaging again updates, never dupes.
        UniqueConstraint("seller_id", "phone", name="uq_customers_seller_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(15))  # canonical 2547XXXXXXXX

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    seller = relationship("Seller")

    def __repr__(self) -> str:
        return f"<Customer {self.name!r} {self.phone} (seller={self.seller_id})>"
