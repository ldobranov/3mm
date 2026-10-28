"""Additive subject migration and identity non-reuse, preserving existing data."""
import re
import subprocess
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.db.user import User
from backend.tests.test_migration_history import _alembic


def test_populated_upgrade_preserves_account_session_and_grants(tmp_path):
    url=f"sqlite:///{tmp_path/'subjects.db'}"
    _alembic(url,'upgrade','9e74f5c60d64')
    engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id,username,email,hashed_password,role,is_blocked,token_version) VALUES (7,'existing','user@example.invalid','password-hash','admin',0,4),(8,'other','other@example.invalid','other-hash','user',0,0)"))
        db.execute(text("INSERT INTO sessions (id,user_id,token,is_active) VALUES (3,7,'unchanged-token',1)"))
    _alembic(url,'upgrade','head'); _alembic(url,'check')
    with engine.connect() as db:
        rows=db.execute(text('SELECT id,subject_id,hashed_password,role,token_version FROM users ORDER BY id')).all()
        assert rows[0][0]==7 and rows[0][2:]==('password-hash','admin',4)
        assert len({row[1] for row in rows})==2
        assert all(re.fullmatch('usr_[a-f0-9]{32}',row[1]) for row in rows)
        assert db.execute(text('SELECT user_id,token,is_active FROM sessions')).one()==(7,'unchanged-token',1)
    _alembic(url,'upgrade','head')
    with engine.connect() as db: assert db.execute(text('SELECT subject_id FROM users WHERE id=7')).scalar()==rows[0][1]
    with Session(engine) as db:
        db.add(User(id=9,username='new',email='new@example.invalid')); db.commit()
        first=db.get(User,9).subject_id
        db.delete(db.get(User,9)); db.commit()
        db.add(User(id=9,username='new',email='new@example.invalid')); db.commit()
        assert db.get(User,9).subject_id!=first
        db.add(User(id=10,username='duplicate',subject_id=rows[0][1]))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
    with pytest.raises(subprocess.CalledProcessError) as blocked:
        _alembic(url,'downgrade','9e74f5c60d64')
    assert 'Stable user subjects' in blocked.value.stderr
    with engine.connect() as db:
        assert db.execute(text("SELECT hashed_password,role,token_version FROM users WHERE id=7")).one()==('password-hash','admin',4)
        assert db.execute(text('SELECT user_id,token FROM sessions')).one()==(7,'unchanged-token')
        assert db.execute(text('SELECT subject_id FROM users WHERE id=7')).scalar()==rows[0][1]
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='b096b7e82f86'
    _alembic(url,'upgrade','head'); _alembic(url,'check')
    engine.dispose()
