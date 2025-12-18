from sqlalchemy import create_engine
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lazar:admin@localhost:5432/mega_monitor")
engine = create_engine(DATABASE_URL)
