"""
Draft agent tests — the guardrail, verified WITHOUT spending money.

We don't call Gemini here (non-deterministic, costs money, needs network) —
that's what the __main__ smoke test in draft.py is for. We test the parts that
must hold regardless of what the model says: the schema IS the guardrail, and
missing-image handling fails cleanly.
"""

import pytest

from app.agent.draft import DraftError, ProductDraft, draft_from_video


def test_draft_never_exposes_stock_or_contact():
    """The guardrail, asserted so it can't silently regress. The agent may now
    SUGGEST a price it can READ off the image (suggested_price_kes) — but it
    must never carry stock or a phone. Stock isn't visible in a picture; a
    contact is the seller's alone. (That the suggested price never becomes the
    STORED price is proven at the service layer — see test_products.py.)"""
    forbidden = {"stock", "quantity", "qty", "phone", "contact"}
    fields = set(ProductDraft.model_fields)
    assert fields & forbidden == set(), f"draft must not expose stock/contact: {fields & forbidden}"


def test_draft_exposes_expected_fields():
    assert set(ProductDraft.model_fields) == {
        "is_product",
        "not_product_reason",
        "name",
        "description",
        "tags",
        "suggested_price_kes",
        "language_note",
    }


def test_no_cover_raises_clean_error():
    """A video with no cover is data, not a crash — the agent must refuse with
    a human message the UI can show, not an AttributeError."""
    with pytest.raises(DraftError, match="No cover image"):
        draft_from_video(cover_bytes=None)


def test_missing_key_raises_clean_error(monkeypatch):
    """With no API key, fail with instructions — same POC bar as everywhere."""
    from app import config

    monkeypatch.setattr(config.settings, "openai_api_key", "")
    with pytest.raises(DraftError, match="OPENAI_API_KEY"):
        draft_from_video(cover_bytes=b"fake-image-bytes")
