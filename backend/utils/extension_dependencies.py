"""
Extension Dependency Management System

This module provides functionality for managing extension dependencies and inter-extension communication.
Extensions can declare dependencies on other extensions and access their APIs.
"""

import json
import re
from typing import Dict, List, Any, Optional, Callable
from backend.database import get_db
from sqlalchemy import text


class ExtensionDependencyManager:
    """Manages extension dependencies and API access"""

    def __init__(self):
        self._api_registry: Dict[str, Dict[str, Any]] = {}
        self._extension_contexts: Dict[str, Any] = {}

    def register_extension_context(self, extension_id: str, context: Any):
        """Register an extension's context for dependency access"""
        self._extension_contexts[extension_id] = context

    def unregister_extension_context(self, extension_id: str):
        """Unregister an extension's context"""
        if extension_id in self._extension_contexts:
            del self._extension_contexts[extension_id]

    def register_api(self, extension_id: str, api_name: str, api_function: Callable):
        """Register an API function that other extensions can call"""
        if extension_id not in self._api_registry:
            self._api_registry[extension_id] = {}

        self._api_registry[extension_id][api_name] = api_function

    def get_api(self, extension_id: str, api_name: str):
        """Get an API function from another extension"""
        if extension_id in self._api_registry and api_name in self._api_registry[extension_id]:
            return self._api_registry[extension_id][api_name]
        return None

    def check_dependencies(self, extension_manifest: dict) -> Dict[str, Any]:
        """Check if all dependencies for an extension are satisfied"""
        dependencies = extension_manifest.get("dependencies", {})
        extension_deps = dependencies.get("extensions", {})

        results = {
            "satisfied": True,
            "missing": [],
            "version_conflicts": [],
            "available_apis": {}
        }

        # Check extension dependencies
        for dep_name, dep_config in extension_deps.items():
            dep_result = self._check_extension_dependency(dep_name, dep_config)
            if not dep_result["available"]:
                results["satisfied"] = False
                if dep_result["reason"] == "missing":
                    results["missing"].append({
                        "name": dep_name,
                        "required_version": dep_config.get("version", "any"),
                        "optional": dep_config.get("optional", False)
                    })
                elif dep_result["reason"] == "version_conflict":
                    results["version_conflicts"].append({
                        "name": dep_name,
                        "required_version": dep_config.get("version", "any"),
                        "installed_version": dep_result.get("installed_version")
                    })

            # Collect available APIs
            if dep_result["available"] and dep_result.get("apis"):
                results["available_apis"][dep_name] = dep_result["apis"]

        return results

    def _check_extension_dependency(self, extension_name: str, dep_config: dict) -> Dict[str, Any]:
        """Check if a specific extension dependency is satisfied"""
        try:
            # Query the database for installed extensions
            db = next(get_db())
            result = db.execute(text("""
                SELECT id, name, version, is_enabled
                FROM extensions
                WHERE name = :name
            """), {"name": extension_name}).fetchone()

            if not result:
                return {
                    "available": False,
                    "reason": "missing",
                    "apis": []
                }

            # Safely extract values from result
            try:
                # Try dictionary access first
                installed_version = result["version"]
                is_enabled = result["is_enabled"]
            except (TypeError, KeyError):
                # Fallback to index access
                installed_version = result[2]  # version is the 3rd column (0-indexed)
                is_enabled = result[3]  # is_enabled is the 4th column (0-indexed)

            if not is_enabled:
                return {
                    "available": False,
                    "reason": "disabled",
                    "installed_version": installed_version,
                    "apis": []
                }

            # Check version constraint
            required_version = dep_config.get("version", "*")
            if not self._check_version_constraint(installed_version, required_version):
                return {
                    "available": False,
                    "reason": "version_conflict",
                    "installed_version": installed_version,
                    "apis": []
                }

            # Get available APIs for this extension
            apis = list(self._api_registry.get(extension_name, {}).keys())

            return {
                "available": True,
                "installed_version": installed_version,
                "apis": apis
            }

        except Exception as e:
            print(f"Error checking extension dependency {extension_name}: {e}")
            return {
                "available": False,
                "reason": "error",
                "error": str(e),
                "apis": []
            }

    def _check_version_constraint(self, installed_version: str, required_version: str) -> bool:
        """Check if installed version satisfies the version constraint"""
        if required_version == "*" or required_version == "any":
            return True

        try:
            # Simple version comparison (can be enhanced with semver library)
            if required_version.startswith(">="):
                min_version = required_version[2:]
                return self._compare_versions(installed_version, min_version) >= 0
            elif required_version.startswith(">"):
                min_version = required_version[1:]
                return self._compare_versions(installed_version, min_version) > 0
            elif required_version.startswith("<="):
                max_version = required_version[2:]
                return self._compare_versions(installed_version, max_version) <= 0
            elif required_version.startswith("<"):
                max_version = required_version[1:]
                return self._compare_versions(installed_version, max_version) < 0
            elif required_version.startswith("~"):
                # Compatible version range (patch-level)
                base_version = required_version[1:]
                return installed_version.startswith(base_version.rsplit(".", 1)[0])
            elif required_version.startswith("^"):
                # Compatible version range (minor-level)
                base_version = required_version[1:]
                return installed_version.startswith(base_version.split(".", 1)[0])
            else:
                # Exact version match
                return installed_version == required_version

        except Exception as e:
            print(f"Error parsing version constraint {required_version}: {e}")
            return False

    def _compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings"""
        v1_parts = [int(x) for x in version1.split(".")]
        v2_parts = [int(x) for x in version2.split(".")]

        # Pad shorter version with zeros
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_len - len(v1_parts)))
        v2_parts.extend([0] * (max_len - len(v2_parts)))

        for i in range(max_len):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1

        return 0

    def get_extension_context(self, extension_id: str):
        """Get the context of another extension"""
        return self._extension_contexts.get(extension_id)

    def call_extension_api(self, extension_id: str, api_name: str, *args, **kwargs):
        """Call an API function from another extension"""
        api_func = self.get_api(extension_id, api_name)
        if api_func:
            return api_func(*args, **kwargs)
        else:
            raise ValueError(f"API '{api_name}' not found in extension '{extension_id}'")


class VersionManager:
    """Manages extension version checking and compatibility"""

    def is_compatible_update(self, current_version: str, new_version: str) -> bool:
        """Check if an update is compatible (no breaking changes)"""
        try:
            current_parts = [int(x) for x in current_version.split('.')]
            new_parts = [int(x) for x in new_version.split('.')]

            # Pad shorter versions
            max_len = max(len(current_parts), len(new_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            new_parts.extend([0] * (max_len - len(new_parts)))

            # Major version change is potentially breaking
            if new_parts[0] > current_parts[0]:
                return False

            # Minor version changes are usually compatible
            return True
        except:
            return False

    def check_for_updates(self, extension_id: str, current_version: str) -> Optional[str]:
        """Check if there's a newer version available (mock implementation)"""
        # This would integrate with marketplace API
        # For now, return None (no update available)
        return None

    def compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2"""
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]

            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))

            for i in range(max_len):
                if v1_parts[i] > v2_parts[i]:
                    return 1
                elif v1_parts[i] < v2_parts[i]:
                    return -1
            return 0
        except:
            return 0


# Global instances
extension_dependency_manager = ExtensionDependencyManager()
version_manager = VersionManager()

# Backward compatibility alias
extension_repository = extension_dependency_manager


def get_extension_dependency_manager():
    """Get the global extension dependency manager instance"""
    return extension_dependency_manager