from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, TypeAdapter, field_validator


class OpenAIClusterResponse(BaseModel):
    """Validated shape of the model JSON for summarization."""

    post: str = Field(default="", max_length=4096)
    used_raw_post_ids: list[int] = Field(default_factory=list)
    headline: str = Field(default="", max_length=200)

    @field_validator("used_raw_post_ids", mode="before")
    @classmethod
    def coerce_ids(cls, v: Any) -> list[int]:
        if not isinstance(v, list):
            raise TypeError("used_raw_post_ids must be a list")
        out: list[int] = []
        for x in v:
            if isinstance(x, bool):
                raise ValueError("boolean is not a valid id")
            if isinstance(x, int):
                out.append(x)
            elif isinstance(x, float) and x.is_integer():
                out.append(int(x))
            else:
                raise TypeError("used_raw_post_ids must contain integers")
        return out

    @field_validator("post", mode="after")
    @classmethod
    def trim_post(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 1000:
            return v[:1000].rstrip()
        return v

    @field_validator("headline", mode="after")
    @classmethod
    def trim_headline(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > 200:
            return v[:200].rstrip()
        return v


class SourceItem(BaseModel):
    channel: str = Field(min_length=1, max_length=255)
    message_id: int

    @field_validator("channel", mode="before")
    @classmethod
    def strip_channel(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise TypeError("channel must be a string")
        s = v.strip()
        if not s:
            raise ValueError("channel must be non-empty")
        return s


class DraftCreatePayload(BaseModel):
    """Validated draft row payload before persistence (content + sources JSON)."""

    content: str = Field(min_length=1, max_length=200_000)
    content_hash: str = Field(min_length=16, max_length=64)
    sources: list[SourceItem] = Field(min_length=1)


_sources_list_adapter: TypeAdapter[list[SourceItem]] = TypeAdapter(list[SourceItem])


def validate_sources_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize sources for DB JSON storage."""
    parsed = _sources_list_adapter.validate_python(items)
    return [s.model_dump(mode="json") for s in parsed]
