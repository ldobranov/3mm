"""Cosmetic product defaults only; never service, device or network identities."""
from copy import deepcopy
import html
import json
from pathlib import Path
import re


PRODUCT_PATH = Path(__file__).resolve().parents[2] / "config_templates/product.json"
FALLBACK = {
    "schema_version": 1, "name": "Platform", "display_name": "Device platform",
    "welcome_message": "Welcome", "description": "Local application and device administration.",
    "default_logo_url": "", "favicon_url": "/favicon.ico",
    "setup": {"page_title": "Device setup", "header": "Device platform", "labels": {
        "en": {"title": "Set up this device", "wifi": "Manage a Wi-Fi connection",
               "networkHelp": "Keeping the connection leaves it under operating-system control.",
               "success": "Setup saved. Reopen the application at the current device address."},
        "bg": {"title": "Настройка на устройството", "wifi": "Управление на Wi-Fi връзка",
               "networkHelp": "Запазената връзка остава под управлението на операционната система.",
               "success": "Настройката е запазена. Отвори приложението на текущия адрес на устройството."},
    }},
}


def _text(value, limit=1024):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Invalid product text")
    value.encode("utf-8")  # Reject lone surrogates before an HTML response is encoded.
    return value


def _asset(value, empty=False):
    if empty and value == "":
        return ""
    if (not isinstance(value, str) or len(value) > 256
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)
            or "//" in value or ".." in value.split("/")):
        raise ValueError("Invalid product asset path")
    return value


def load_product_metadata(path=None):
    """Malformed/missing cosmetics must not disable setup or alter its rights."""
    try:
        with (PRODUCT_PATH if path is None else Path(path)).open("rb") as stream:
            body = stream.read(16385)
        if len(body) > 16384:
            raise ValueError("Product metadata too large")
        raw = json.loads(body)
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("Unsupported product metadata")
        setup = raw["setup"]
        return {"schema_version": 1, "name": _text(raw["name"], 128),
                "display_name": _text(raw["display_name"], 256),
                "welcome_message": _text(raw["welcome_message"]),
                "description": _text(raw["description"], 2048),
                "default_logo_url": _asset(raw["default_logo_url"], True),
                "favicon_url": _asset(raw["favicon_url"]),
                "setup": {"page_title": _text(setup["page_title"], 256),
                          "header": _text(setup["header"], 256), "labels": {
                              locale: {key: _text(setup["labels"][locale][key])
                                       for key in ("title", "wifi", "networkHelp", "success")}
                              for locale in ("en", "bg")}}}
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return deepcopy(FALLBACK)


def render_setup_page(page, metadata, *, read_only):
    labels = json.dumps(metadata["setup"]["labels"], ensure_ascii=True, allow_nan=False)
    # JSON is embedded in a script element, not HTML: escape its closing-tag
    # alphabet too. Text and attribute positions use normal HTML escaping.
    labels = labels.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    values = {"__PRODUCT_TITLE__": html.escape(metadata["setup"]["page_title"]),
              "__PRODUCT_HEADER__": html.escape(metadata["setup"]["header"]),
              "__PRODUCT_LABELS__": labels,
              "__READ_ONLY__": "true" if read_only else "false"}
    return re.sub(r"__PRODUCT_TITLE__|__PRODUCT_HEADER__|__PRODUCT_LABELS__|__READ_ONLY__",
                  lambda match: values[match[0]], page)
