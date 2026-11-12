"""Optional application dependency. Core never imports this package."""
from .schema import CrudDefinition
from .engine import CrudService

__all__ = ["CrudDefinition", "CrudService"]
