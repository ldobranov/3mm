from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.db.base import Base
from backend.db.association_tables import user_roles
from pydantic import BaseModel  # Import BaseModel from pydantic
from passlib.context import CryptContext

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, nullable=False)  # Add role field to the User model
    roles = relationship("Role", secondary=user_roles, back_populates="users", lazy="dynamic")
    audit_logs = relationship("AuditLog", back_populates="user", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("username", "email", name="unique_user_email"),
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class UserSchema(BaseModel):
    id: int
    username: str
    email: str
    role: str  # Include role in the schema

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    id: int | None = None
    username: str
    email: str
    role: str
    hashed_password: str | None = None  # Make hashed_password optional for updates

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None
    hashed_password: str | None = None  # Optional for updates

    class Config:
        from_attributes = True