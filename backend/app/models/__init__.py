"""
Models package — every table BOB owns, one file per aggregate.

    Base (app/db.py)
      ├── Seller   (seller.py)   who sells: handle, bio, contacts
      └── Product  (product.py)  what's for sale: scrape + price + stock

IMPORTANT: importing this package is what REGISTERS the tables on
Base.metadata. Alembic's env.py does `from app import models` for exactly
that reason — a model missing from the imports below is INVISIBLE to
migrations (autogenerate would try to drop its table).
"""

from app.models.product import Product, ProductStatus
from app.models.seller import Seller

# What `from app.models import *` exposes; also doubles as the checklist of
# every model that exists — keep it exhaustive.
__all__ = ["Seller", "Product", "ProductStatus"]
