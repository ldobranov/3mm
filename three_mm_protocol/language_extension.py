"""Data-only language extension delivered inside a manifest-v2 package."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN

class LanguageExtensionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    language_extension_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    code: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    name: str = Field(min_length=1, max_length=120)
    native_name: str = Field(min_length=1, max_length=120)
    locale: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    direction: Literal["ltr", "rtl"] = "ltr"
    frontend: dict = Field(default_factory=dict)
    backend: dict = Field(default_factory=dict)

    @field_validator("frontend", "backend")
    @classmethod
    def bounded_text_tree(cls, value):
        count = 0
        def visit(node, depth):
            nonlocal count
            if depth > 12 or not isinstance(node, dict):
                raise ValueError("translations must be a bounded tree of text")
            for key, item in node.items():
                count += 1
                if count > 10000 or not isinstance(key, str) or not key or len(key) > 160 or key in {"__proto__", "prototype", "constructor"}:
                    raise ValueError("translation key limit exceeded or unsafe key")
                if isinstance(item, dict):
                    visit(item, depth + 1)
                elif not isinstance(item, str) or len(item) > 16000:
                    raise ValueError("translation values must be bounded text")
        visit(value, 0)
        return value
