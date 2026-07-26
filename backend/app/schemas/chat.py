"""Sales-chat schemas (public, buyer-facing)."""

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)  # cap input → bounds cost/abuse


class ChatIn(BaseModel):
    # The conversation so far (must start with a user turn, alternate). Capped
    # so a public endpoint can't be pushed into huge, expensive prompts.
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    video_id: str | None = None  # which video the buyer arrived from (?v=)


class ChatOut(BaseModel):
    reply: str
