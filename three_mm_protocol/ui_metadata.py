"""Shared localized labels and UI identifiers, without product/runtime models."""
from pydantic import BaseModel, ConfigDict, Field
IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
ROUTE_PATTERN = r"^/[a-z0-9][a-z0-9/_-]*$"
class LocalizedTextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    en: str = Field(min_length=1, max_length=160)
    translations: dict[str,str] = Field(default_factory=dict)
