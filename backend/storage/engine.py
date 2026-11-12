from sqlalchemy import create_engine
from backend.config import get_settings

DATABASE_URL = get_settings().database_url
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
