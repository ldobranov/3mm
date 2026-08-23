from backend.routes.ai_extension_builder_routes import _plan_extension_intent
from backend.schemas.ai_extension_builder import PlanExtensionIntentRequest


def test_dashboard_settings_become_a_compiled_widget_without_crud():
    plan = _plan_extension_intent(PlanExtensionIntentRequest(
        description="Dashboard clock widget with timezone and editor settings",
    ))
    assert plan.project_type == "widget"
    assert plan.package_kind == "compiled"
    assert plan.template_key == "simple"
    assert plan.needs_database is False
    properties = plan.config_schema["properties"]
    assert properties["timezone"]["format"] == "timezone"


def test_named_widget_choices_are_selects_not_booleans():
    plan = _plan_extension_intent(PlanExtensionIntentRequest(
        description="Dashboard widget with digital or analog display and 12/24 hour format",
    ))
    properties = plan.config_schema["properties"]
    assert properties["displayMode"]["enum"] == ["digital", "analog"]
    assert properties["hourFormat"]["enum"] == ["24", "12"]


def test_record_management_becomes_crud_only_when_records_are_requested():
    plan = _plan_extension_intent(PlanExtensionIntentRequest(
        description="Separate page with a catalog and editable database records",
    ))
    assert plan.project_type == "extension"
    assert plan.template_key == "crud"
    assert plan.needs_database is True


def test_ambiguous_placement_asks_one_plain_language_question():
    plan = _plan_extension_intent(PlanExtensionIntentRequest(
        description="Show the current time with a configurable timezone",
    ))
    assert plan.project_type == "widget"
    assert [question.id for question in plan.questions] == ["placement"]


def test_gpio_indicator_request_produces_a_typed_capability_plan():
    plan = _plan_extension_intent(PlanExtensionIntentRequest(
        description="Dashboard widget that reads a GPIO input pin and shows a red or green lamp",
        placement="dashboard",
        data_mode="settings",
    ))
    capability_plan = plan.capability_plan
    assert capability_plan is not None
    assert capability_plan.bindings[0].capability_id == "gpio.digital.input"
    assert capability_plan.bindings[0].operation == "subscribe"
    assert {item.kind for item in capability_plan.settings} >= {"device", "capability_channel"}
    assert {item.state for item in capability_plan.presentations[0].states} >= {
        "value", "stale", "offline", "error",
    }
