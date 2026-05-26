"""Item Object Type. See docs/ontology.md §2.6."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import ItemType


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: ItemType
    description: str = ""

    base_price: int = Field(default=0, ge=0)

    owner_id: str | None = None
    location_id: str | None = None

    is_unique: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
