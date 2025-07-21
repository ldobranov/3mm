"""
Unit tests for handle_settings function in backend.routes.settings.
Covers happy paths and edge cases for all HTTP methods (GET, POST, PUT, DELETE).
Mocks all DB and FastAPI dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from types import SimpleNamespace

# Patch create_crud_routes globally for all tests in this module
@pytest.fixture(autouse=True)
def patch_create_crud_routes(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.settings.create_crud_routes",
        lambda *a, **kw: MagicMock(name="crud_router"),
    )

# Helper: mock request with method and .json()
def make_request(method, json_data=None, json_side_effect=None):
    req = MagicMock()
    req.method = method
    if json_side_effect:
        req.json.side_effect = json_side_effect
    else:
        req.json.return_value = json_data
    return req

@pytest.mark.usefixtures("patch_create_crud_routes")
class TestHandleSettings:
    """
    Unit tests for handle_settings in backend.routes.settings.
    """

    @pytest.fixture(autouse=True)
    def import_handle_settings(self):
        # Import fresh for each test to ensure patching works
        from backend.routes.settings import handle_settings
        self.handle_settings = handle_settings

    # -------------------- HAPPY PATHS --------------------

    @pytest.mark.happy
    def test_get_settings_success(self):
        """Test GET returns settings data when present."""
        mock_settings = SimpleNamespace(data={"foo": "bar"})
        db = MagicMock()
        db.query.return_value.first.return_value = mock_settings
        req = make_request("GET")
        result = self.handle_settings(req, db)
        assert result == {"data": {"foo": "bar"}}

    @pytest.mark.happy
    def test_post_settings_success(self):
        """Test POST creates settings successfully."""
        db = MagicMock()
        db.query.return_value.first.return_value = None
        req = make_request("POST", json_data={"baz": 123})
        result = self.handle_settings(req, db)
        assert result == {"message": "Settings created successfully"}
        db.add.assert_called()
        db.commit.assert_called()

    @pytest.mark.happy
    def test_put_settings_success(self):
        """Test PUT updates settings successfully."""
        # Existing settings with id=1
        existing = SimpleNamespace(id=1, data={"foo": "bar"})
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.commit = MagicMock()
        req = make_request("PUT", json_data={"id": 1, "baz": 456})
        result = self.handle_settings(req, db)
        assert result == {"message": "Settings updated successfully"}
        assert "baz" in existing.data
        db.commit.assert_called()

    @pytest.mark.happy
    def test_delete_settings_success(self):
        """Test DELETE removes settings successfully."""
        existing = SimpleNamespace(id=1, data={"foo": "bar"})
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        req = make_request("DELETE", json_data={"id": 1})
        result = self.handle_settings(req, db)
        assert result == {"message": "Settings deleted successfully"}
        db.delete.assert_called_with(existing)
        db.commit.assert_called()

    # -------------------- EDGE CASES --------------------

    @pytest.mark.edge
    def test_get_settings_not_found(self):
        """Test GET when no settings exist raises 404."""
        db = MagicMock()
        db.query.return_value.first.return_value = None
        req = make_request("GET")
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Settings not found"

    @pytest.mark.edge
    def test_post_settings_invalid_payload(self):
        """Test POST with invalid payload raises 422."""
        db = MagicMock()
        # Simulate request.json() raising an error (e.g., invalid JSON)
        req = make_request("POST", json_side_effect=ValueError("bad json"))
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422
        assert "bad json" in str(exc.value.detail)

    @pytest.mark.edge
    def test_post_settings_schema_validation_error(self):
        """Test POST with payload not matching schema raises 422."""
        db = MagicMock()
        # SettingsSchema expects a dict under 'data', so pass a non-dict
        req = make_request("POST", json_data="notadict")
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422

    @pytest.mark.edge
    def test_put_settings_not_found(self):
        """Test PUT when settings with given id do not exist raises 404."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        req = make_request("PUT", json_data={"id": 99, "foo": "bar"})
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Settings not found"

    @pytest.mark.edge
    def test_put_settings_invalid_payload(self):
        """Test PUT with invalid payload raises 422."""
        db = MagicMock()
        req = make_request("PUT", json_side_effect=TypeError("bad put"))
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422
        assert "bad put" in str(exc.value.detail)

    @pytest.mark.edge
    def test_put_settings_schema_validation_error(self):
        """Test PUT with payload not matching schema raises 422."""
        db = MagicMock()
        # Missing 'id' key
        req = make_request("PUT", json_data={"foo": "bar"})
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422

    @pytest.mark.edge
    def test_delete_settings_not_found(self):
        """Test DELETE when settings with given id do not exist raises 404."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        req = make_request("DELETE", json_data={"id": 42})
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Settings not found"

    @pytest.mark.edge
    def test_delete_settings_invalid_payload(self):
        """Test DELETE with invalid payload raises 422."""
        db = MagicMock()
        req = make_request("DELETE", json_side_effect=KeyError("id"))
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422
        assert "id" in str(exc.value.detail)

    @pytest.mark.edge
    def test_delete_settings_schema_validation_error(self):
        """Test DELETE with payload missing 'id' key raises 422."""
        db = MagicMock()
        req = make_request("DELETE", json_data={})
        with pytest.raises(HTTPException) as exc:
            self.handle_settings(req, db)
        assert exc.value.status_code == 422

    # -------------------- ADDITIONAL EDGE CASES --------------------

    @pytest.mark.edge
    def test_unexpected_method(self):
        """Test that an unsupported HTTP method raises AttributeError (since not handled)."""
        db = MagicMock()
        req = make_request("PATCH")
        # Should do nothing or raise, depending on FastAPI's router, but here, falls through
        with pytest.raises(AttributeError):
            self.handle_settings(req, db)