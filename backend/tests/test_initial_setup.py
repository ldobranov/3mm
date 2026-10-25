import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.services.initial_setup import InitialAdministratorError, establish_administrator
from backend.utils.auth import hash_password, verify_password


@pytest.fixture
def database(tmp_path):
    path=tmp_path/'core.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, '
                   'hashed_password TEXT, role TEXT, is_blocked BOOLEAN DEFAULT 0, token_version INTEGER DEFAULT 0)')
    return path


def test_concurrent_setup_is_idempotent_and_preserves_password(database):
    def create(_): establish_administrator(database,'admin','admin@example.com','admin')
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(create,range(2)))
    with sqlite3.connect(database) as db:
        users=db.execute('SELECT hashed_password,role FROM users').fetchall()
    assert len(users)==1 and users[0][1]=='admin' and verify_password('admin',users[0][0])


@pytest.mark.parametrize('role,blocked,password',[('admin',0,'wrong'),('admin',1,'original'),('user',0,'original')])
def test_setup_never_resets_blocked_admin_or_promotes_existing_user(database,role,blocked,password):
    hashed=hash_password('original')
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO users (username,email,hashed_password,role,is_blocked) VALUES (?,?,?,?,?)',
                   ('admin','admin@example.com',hashed,role,blocked))
    with pytest.raises(InitialAdministratorError):
        establish_administrator(database,'admin','admin@example.com',password)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT hashed_password,role,is_blocked FROM users').fetchone()==(hashed,role,blocked)


def test_missing_database_is_not_created(tmp_path):
    missing=tmp_path/'missing.db'
    with pytest.raises(InitialAdministratorError): establish_administrator(missing,'admin','admin@example.com','admin')
    assert not missing.exists()
