import pytest
from pydantic import ValidationError

from three_mm_protocol import RuntimeExtensionV1


def definition(**changes):
    value = {
        "runtime_extension_version": 1,
        "module_id": "org.3mm.contacts",
        "version": "1.0.0",
        "name": {"en": "Contacts", "translations": {"bg": "Контакти"}},
        "description": {"en": "Manage contacts"},
        "entities": [
            {
                "entity_id": "contact",
                "label": {"en": "Contact"},
                "fields": [
                    {
                        "field_id": "name",
                        "label": {"en": "Name"},
                        "kind": "text",
                        "required": True,
                    }
                ],
            }
        ],
        "pages": [
            {
                "page_id": "contacts",
                "path": "/contacts",
                "title": {"en": "Contacts"},
                "entity_id": "contact",
                "view": "table",
                "actions": ["create", "read", "update", "delete"],
            }
        ],
        "navigation": [
            {
                "navigation_id": "contacts_menu",
                "page_id": "contacts",
                "label": {"en": "Contacts"},
                "icon": "bi-people",
            }
        ],
        "permissions": ["runtime.data.read", "runtime.data.write"],
    }
    value.update(changes)
    return value


def test_valid_crud_runtime_extension_contract():
    runtime = RuntimeExtensionV1.model_validate(definition())

    assert runtime.module_id == "org.3mm.contacts"
    assert runtime.pages[0].entity_id == "contact"


@pytest.mark.parametrize("executable_field", ["script", "component", "backend_entry"])
def test_executable_or_compiled_fields_are_rejected(executable_field):
    value = definition()
    value[executable_field] = "arbitrary-code"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RuntimeExtensionV1.model_validate(value)


def test_unknown_entity_reference_is_rejected():
    value = definition()
    value["pages"][0]["entity_id"] = "missing"

    with pytest.raises(ValidationError, match="unknown entity"):
        RuntimeExtensionV1.model_validate(value)


def test_write_actions_require_explicit_permission():
    value = definition(permissions=["runtime.data.read"])

    with pytest.raises(ValidationError, match="runtime.data.write"):
        RuntimeExtensionV1.model_validate(value)


def test_duplicate_routes_are_rejected():
    value = definition()
    second = dict(value["pages"][0], page_id="contacts_archive")
    value["pages"].append(second)

    with pytest.raises(ValidationError, match="page routes must be unique"):
        RuntimeExtensionV1.model_validate(value)
