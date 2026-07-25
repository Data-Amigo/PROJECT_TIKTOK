"""
Draft agent tests — the guardrail, verified WITHOUT spending money.

We don't call Gemini here (non-deterministic, costs money, needs network) —
that's what the __main__ smoke test in draft.py is for. We test the parts that
must hold regardless of what the model says: the schema IS the guardrail, and
missing-image handling fails cleanly.
"""

import pytest

from app.agent.draft import DraftError, ProductDraft, draft_from_video


def test_draft_schema_has_no_money_fields():
    """The core safety property, asserted as a test so it can never regress:
    the agent's output schema cannot carry a price or stock. If someone adds
    one later, this test fails and forces the conversation."""
    forbidden = {"price", "amount", "cost", "stock", "quantity", "qty", "phone"}
    fields = set(ProductDraft.model_fields)
    assert fields & forbidden == set(), f"draft must not expose money/stock: {fields & forbidden}"


def test_draft_only_exposes_descriptive_fields():
    assert set(ProductDraft.model_fields) == {"name", "description", "tags", "language_note"}


def test_no_cover_raises_clean_error():
    """A video with no cover is data, not a crash — the agent must refuse with
    a human message the UI can show, not an AttributeError."""
    with pytest.raises(DraftError, match="No cover image"):
        draft_from_video(cover_bytes=None)


def test_missing_key_raises_clean_error(monkeypatch):
    """With no API key, fail with instructions — same POC bar as everywhere."""
    from app import config

    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    with pytest.raises(DraftError, match="GEMINI_API_KEY"):
        draft_from_video(cover_bytes=b"fake-image-bytes")
