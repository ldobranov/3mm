from sqlalchemy import create_engine
from backend.config import get_settings

DATABASE_URL = get_settings().database_url
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)

# A missing optional observation facility must not prevent login or Core startup.
try:
    from backend.storage.contention import write_observer
    write_observer.install(engine)
except Exception:
    import logging
    logging.getLogger(__name__).warning("Optional SQLite write observation is unavailable")
