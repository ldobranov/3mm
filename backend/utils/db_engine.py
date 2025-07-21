from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///backend/mega_monitor.db"  # Updated to match the application's configuration
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
