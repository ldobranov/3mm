"""
Unit tests for the `init_db` function in backend.database.database.py

These tests are organized into happy path and edge case categories,
using pytest markers for each. The tests are contained in a single
test class as per instructions.
"""

import pytest
import importlib
import sys
from unittest import mock

# Import the function to test
from backend.database import init_db

@pytest.mark.usefixtures("monkeypatch")
class TestInitDb:
    """
    Unit tests for the `init_db` function in backend.database.
    """

    # -------------------- HAPPY PATHS --------------------

    @pytest.mark.happy_path
    def test_init_db_runs_without_error(self):
        """
        Test that `init_db` runs without raising any exceptions.
        """
        # Should not raise any exception
        assert init_db() is None

    @pytest.mark.happy_path
    def test_init_db_with_default_env(self, monkeypatch):
        """
        Test that `init_db` works when DATABASE_URL is not set (uses default).
        """
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Re-import the module to re-evaluate DATABASE_URL
        if "backend.database" in sys.modules:
            del sys.modules["backend.database"]
        db_module = importlib.import_module("backend.database")
        # Should not raise
        assert db_module.init_db() is None

    @pytest.mark.happy_path
    def test_init_db_with_custom_env(self, monkeypatch):
        """
        Test that `init_db` works when DATABASE_URL is set to a custom value.
        """
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test_custom.db")
        # Re-import the module to re-evaluate DATABASE_URL
        if "backend.database" in sys.modules:
            del sys.modules["backend.database"]
        db_module = importlib.import_module("backend.database")
        # Should not raise
        assert db_module.init_db() is None

    # -------------------- EDGE CASES --------------------

    @pytest.mark.edge_case
    def test_init_db_when_engine_is_none(self, monkeypatch):
        """
        Test that `init_db` does not fail if the engine is None.
        """
        # Patch engine to None in the module
        import backend.database as db_module
        monkeypatch.setattr(db_module, "engine", None)
        # Should not raise
        assert db_module.init_db() is None

    @pytest.mark.edge_case
    def test_init_db_when_base_is_none(self, monkeypatch):
        """
        Test that `init_db` does not fail if Base is None.
        """
        import backend.database as db_module
        monkeypatch.setattr(db_module, "Base", None)
        # Should not raise
        assert db_module.init_db() is None

    @pytest.mark.edge_case
    def test_init_db_when_sessionlocal_is_none(self, monkeypatch):
        """
        Test that `init_db` does not fail if SessionLocal is None.
        """
        import backend.database as db_module
        monkeypatch.setattr(db_module, "SessionLocal", None)
        # Should not raise
        assert db_module.init_db() is None

    @pytest.mark.edge_case
    def test_init_db_when_os_environ_is_empty(self, monkeypatch):
        """
        Test that `init_db` works when os.environ is empty.
        """
        monkeypatch.setattr("os.environ", {})
        # Re-import the module to re-evaluate DATABASE_URL
        if "backend.database" in sys.modules:
            del sys.modules["backend.database"]
        db_module = importlib.import_module("backend.database")
        # Should not raise
        assert db_module.init_db() is None

    @pytest.mark.edge_case
    def test_init_db_multiple_calls(self):
        """
        Test that calling `init_db` multiple times does not cause errors.
        """
        for _ in range(5):
            assert init_db() is None