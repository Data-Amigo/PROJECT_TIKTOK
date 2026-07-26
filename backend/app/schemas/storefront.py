"""Storefront (seller's own shop) schemas."""

from pydantic import BaseModel, ConfigDict, Field


class ConnectTikTokIn(BaseModel):
    username: str = Field(min_length=1, description="TikTok @handle, username, or profile URL")


class StorefrontOut(BaseModel):
    """The seller's view of their OWN storefront (the dashboard header)."""

    model_config = ConfigDict(from_attributes=True)

    handle: str
    display_name: str
    tiktok_username: str | None
    bio: str
    avatar_url: str | None
    follower_count: int
    phone: str | None
