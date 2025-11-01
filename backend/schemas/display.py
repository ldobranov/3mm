from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any


class DisplayCreate(BaseModel):
    title: str
    slug: str
    is_public: bool = False


class DisplayUpdate(BaseModel):
    title: Optional[str] = None
    is_public: Optional[bool] = None


class WidgetCreate(BaseModel):
    type: Literal["CLOCK", "TEXT", "RSS"]
    config: Dict[str, Any] = Field(default_factory=dict)
    x: int = 0
    y: int = 0
    width: int = 2
    height: int = 2
    z_index: int = 1


class WidgetUpdate(BaseModel):
    config: Optional[Dict[str, Any]] = None
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    z_index: Optional[int] = None


class BulkLayoutItem(BaseModel):
    id: int
    x: int
    y: int
    width: int
    height: int
    z_index: int


class BulkLayoutUpdate(BaseModel):
    widgets: List[BulkLayoutItem]
