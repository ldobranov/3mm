from pydantic import BaseModel, ConfigDict
from backend.db.universal_translation import Menu


class MenuSchema(BaseModel):
    id: int
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)

class MenuCreateSchema(BaseModel):
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)
