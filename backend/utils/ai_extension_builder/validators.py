from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from backend.schemas.ai_extension_builder import BuildWarning, ExtensionSpec


def _get_nested(obj: Any, dotted: str) -> Optional[Any]:
    cur = obj
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _extract_t_keys(text: str) -> List[str]:
    # Very small heuristic: t('a.b.c', ...) in Vue/TS.
    return re.findall(r"\bt\(\s*['\"]([^'\"]+)['\"]", text)


def _extract_backend_api_prefix(py_text: str) -> Optional[str]:
    """Best-effort extraction of APIRouter(prefix="...") from backend entry."""
    if not py_text:
        return None
    m = re.search(r"APIRouter\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]", py_text)
    return m.group(1) if m else None


def _extract_backend_version_literals(py_text: str) -> List[str]:
    """Best-effort extraction of explicit version string literals in the backend entry."""
    if not py_text:
        return []
    versions: List[str] = []

    # Common pattern: return {"version": "1.2.3"}
    versions.extend(re.findall(r"['\"]version['\"]\s*:\s*['\"]([^'\"]+)['\"]", py_text))

    # Common pattern: docstring "Initialize X 1.2.3"
    versions.extend(re.findall(r"Initialize\s+[^\n\r]*?\b(\d+\.\d+\.\d+)\b", py_text))

    # De-dup, preserve order
    seen = set()
    out: List[str] = []
    for v in versions:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def validate_extension_package(spec: ExtensionSpec, files_text: Dict[str, str]) -> List[BuildWarning]:
    warnings: List[BuildWarning] = []

    # --- Manifest checks ---
    manifest_raw = files_text.get('manifest.json')
    manifest: Dict[str, Any] = {}
    if not manifest_raw:
        warnings.append(
            BuildWarning(code='manifest.missing', message='manifest.json is missing.')
        )
    else:
        try:
            manifest = json.loads(manifest_raw)
        except Exception as e:
            warnings.append(
                BuildWarning(code='manifest.invalid_json', message=f'manifest.json is not valid JSON: {e}')
            )

    # --- API prefix checks ---
    api_prefix = (spec.api_prefix or '').strip()
    if api_prefix and not api_prefix.startswith('/api/'):
        warnings.append(
            BuildWarning(
                code='api_prefix.nonstandard',
                message=f"API prefix '{api_prefix}' does not start with '/api/'.",
            )
        )

    backend_entry_path = f"backend/{spec.backend_entry}"
    backend_text = files_text.get(backend_entry_path, '')
    backend_prefix = _extract_backend_api_prefix(backend_text)
    if backend_prefix and api_prefix and backend_prefix != api_prefix:
        warnings.append(
            BuildWarning(
                code='api_prefix.mismatch',
                message=(
                    f"Spec api_prefix is '{api_prefix}' but backend router prefix is '{backend_prefix}' "
                    f"in {backend_entry_path}."
                ),
            )
        )

    # --- Relationships checks (files exist) ---
    provides = (manifest.get('provides') or {}) if isinstance(manifest, dict) else {}
    content_embedders = {}
    if isinstance(provides, dict):
        ce = provides.get('content_embedders')
        if isinstance(ce, dict):
            content_embedders = ce

    for embedder_type, cfg in content_embedders.items():
        if not isinstance(cfg, dict):
            continue
        comp = cfg.get('component')
        if not isinstance(comp, str) or not comp:
            continue
        comp_file = comp if comp.endswith('.vue') else f"{comp}.vue"
        frontend_path = f"frontend/{comp_file}"
        if frontend_path not in files_text:
            warnings.append(
                BuildWarning(
                    code='relationships.missing_component',
                    message=f"provides.content_embedders['{embedder_type}'] references component '{comp_file}' but '{frontend_path}' is missing.",
                )
            )

    # --- Frontend route/component checks ---
    frontend_entry = None
    if isinstance(manifest, dict):
        fe = manifest.get('frontend_entry')
        if isinstance(fe, str) and fe:
            frontend_entry = fe
    frontend_entry = frontend_entry or spec.frontend_entry

    if frontend_entry:
        frontend_entry_path = f"frontend/{frontend_entry}"
        if frontend_entry_path not in files_text:
            warnings.append(
                BuildWarning(
                    code='frontend.entry_missing',
                    message=f"Frontend entry '{frontend_entry_path}' is missing.",
                )
            )

    # Validate frontend_components
    frontend_components = []
    if isinstance(manifest, dict) and isinstance(manifest.get('frontend_components'), list):
        frontend_components = [c for c in manifest.get('frontend_components') if isinstance(c, str)]
    else:
        frontend_components = list(spec.frontend_components or [])

    for comp in frontend_components:
        comp_file = comp if comp.endswith('.vue') else comp
        comp_path = f"frontend/{comp_file}"
        if comp_path not in files_text:
            warnings.append(
                BuildWarning(
                    code='frontend.component_missing',
                    message=f"frontend_components references '{comp_file}' but '{comp_path}' is missing.",
                )
            )

    # Validate each frontend_routes component exists
    routes: List[Dict[str, Any]] = []
    if isinstance(manifest, dict) and isinstance(manifest.get('frontend_routes'), list):
        routes = [r for r in manifest.get('frontend_routes') if isinstance(r, dict)]

    for route in routes:
        comp = route.get('component')
        if not isinstance(comp, str) or not comp:
            continue
        comp_file = comp if comp.endswith('.vue') else f"{comp}.vue" if '.' not in comp else comp
        frontend_path = f"frontend/{comp_file}"
        if frontend_path not in files_text:
            warnings.append(
                BuildWarning(
                    code='routes.missing_component',
                    message=f"frontend_routes references component '{comp_file}' but '{frontend_path}' is missing.",
                )
            )

    # --- i18n checks (t() keys exist in locale json) ---
    locales_dir = spec.locales.directory or 'locales/'
    if not locales_dir.endswith('/'):
        locales_dir += '/'

    locale_json_by_lang: Dict[str, Dict[str, Any]] = {}
    for lang in spec.locales.supported:
        raw = files_text.get(f"{locales_dir}{lang}.json")
        if not raw:
            warnings.append(
                BuildWarning(
                    code='i18n.locale_missing',
                    message=f"Locale file missing: {locales_dir}{lang}.json",
                )
            )
            continue
        try:
            locale_json_by_lang[lang] = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            warnings.append(
                BuildWarning(
                    code='i18n.locale_invalid_json',
                    message=f"Locale file {locales_dir}{lang}.json is invalid JSON: {e}",
                )
            )

    # collect t() keys from frontend text files
    used_keys: List[str] = []
    for path, text in files_text.items():
        if not path.startswith('frontend/'):
            continue
        if not (path.endswith('.vue') or path.endswith('.ts') or path.endswith('.js')):
            continue
        used_keys.extend(_extract_t_keys(text))

    used_keys = sorted(set(k for k in used_keys if k and not k.startswith('http')))
    for lang, locale_json in locale_json_by_lang.items():
        for key in used_keys:
            if _get_nested(locale_json, key) is None:
                warnings.append(
                    BuildWarning(
                        code='i18n.missing_key',
                        message=f"Missing i18n key '{key}' in {locales_dir}{lang}.json",
                    )
                )

    # --- DB naming heuristics ---
    for path, text in files_text.items():
        if not path.startswith('backend/') or not path.endswith('.py'):
            continue

        # Find ext_* identifiers and warn on version/invalid characters.
        # Note: we intentionally do NOT enforce lowercase here because some deployments
        # may accept quoted identifiers; we focus on the major breakage: versioned prefixes.
        for match in re.findall(r"\bext_[^\s\"']+", text):
            # Stop at common punctuation that ends identifiers
            match = match.rstrip(',:);')
            if re.search(r"_\d+\.\d+\.\d+", match):
                warnings.append(
                    BuildWarning(
                        code='db.table_name.contains_version',
                        message=f"Table-like identifier '{match}' appears to include a version (avoid version in table names).",
                    )
                )
            if '.' in match or ' ' in match:
                warnings.append(
                    BuildWarning(
                        code='db.table_name.invalid_chars',
                        message=f"Table-like identifier '{match}' contains invalid characters (use underscores only).",
                    )
                )

    # --- Version consistency checks ---
    manifest_version = None
    if isinstance(manifest, dict):
        mv = manifest.get('version')
        if isinstance(mv, str) and mv:
            manifest_version = mv

    if manifest_version and manifest_version != spec.version:
        warnings.append(
            BuildWarning(
                code='version.mismatch',
                message=f"Spec version is '{spec.version}' but manifest.json version is '{manifest_version}'.",
            )
        )

    backend_versions = _extract_backend_version_literals(backend_text)
    if backend_versions and spec.version not in backend_versions:
        warnings.append(
            BuildWarning(
                code='version.backend_literal_mismatch',
                message=(
                    f"Backend entry {backend_entry_path} contains version literal(s) {backend_versions} "
                    f"but spec.version is '{spec.version}'."
                ),
            )
        )

    # --- public_endpoints sanity checks ---
    public_endpoints = []
    if isinstance(manifest, dict) and isinstance(manifest.get('public_endpoints'), list):
        public_endpoints = [e for e in manifest.get('public_endpoints') if isinstance(e, str)]
    else:
        public_endpoints = list(spec.public_endpoints or [])

    for ep in public_endpoints:
        ep = (ep or '').strip()
        if not ep:
            continue
        # In this codebase, public_endpoints are API paths, not UI routes.
        if not ep.startswith('/api/'):
            warnings.append(
                BuildWarning(
                    code='public_endpoints.non_api',
                    message=f"public_endpoints contains '{ep}', which does not start with '/api/'.",
                )
            )

    return warnings
