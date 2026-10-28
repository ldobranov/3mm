import backend.database  # noqa: F401 - registers the complete model metadata
from backend.db.base import Base
from backend.db.role import Role
from backend.db.menu import Menu
from backend.db.user import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)(), engine


def test_user_and_role_round_trip():
    session, engine = make_session()
    try:
        user = User(
            username="test-user",
            email="test@example.com",
            hashed_password="not-a-real-password-hash",
        )
        role = Role(name="operator", description="Device operator")
        user.roles.append(role)
        session.add(user)
        session.commit()

        stored = session.query(User).filter_by(username="test-user").one()
        assert stored.email == "test@example.com"
        assert [role.name for role in stored.roles] == ["operator"]
    finally:
        session.close()
        engine.dispose()


def test_menu_has_one_canonical_model():

    session, engine = make_session()
    try:
        menu = Menu(
            name="Main",
            items=[{"label": {"en": "Home"}, "path": "/"}],
            default_language="en",
            has_translations=False,
            is_active=True,
        )
        session.add(menu)
        session.commit()

        stored = session.query(Menu).one()
        assert stored.name == "Main"
        assert stored.items[0]["path"] == "/"
        assert stored.is_active is True
    finally:
        session.close()
        engine.dispose()
