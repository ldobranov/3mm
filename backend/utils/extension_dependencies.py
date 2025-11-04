"""
Extension Dependencies and Version Management
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from packaging import version
import requests

class DependencyResolver:
    """Resolves extension dependencies and version conflicts"""

    def __init__(self):
        self.installed_packages: Dict[str, str] = {}
        self.extension_dependencies: Dict[str, Dict[str, str]] = {}

    def add_installed_package(self, package_name: str, version_spec: str):
        """Add an installed package to the resolver"""
        self.installed_packages[package_name] = version_spec

    def parse_version_spec(self, version_spec: str) -> Tuple[str, str]:
        """Parse version specification like '>=1.0.0', '==2.1.0'"""
        operators = ['>=', '<=', '>', '<', '==', '!=', '~=', '===']
        for op in operators:
            if version_spec.startswith(op):
                return op, version_spec[len(op):].strip()
        # No operator means exact version
        return '==', version_spec.strip()

    def check_version_compatibility(self, installed_version: str, required_spec: str) -> bool:
        """Check if installed version satisfies the requirement"""
        try:
            op, req_version = self.parse_version_spec(required_spec)
            installed = version.parse(installed_version)
            required = version.parse(req_version)

            if op == '>=':
                return installed >= required
            elif op == '<=':
                return installed <= required
            elif op == '>':
                return installed > required
            elif op == '<':
                return installed < required
            elif op == '==':
                return installed == required
            elif op == '!=':
                return installed != required
            elif op == '~=':
                # Compatible release (e.g., ~=2.2 is equivalent to >=2.2, ==2.*)
                return installed >= required and installed.major == required.major
            else:
                return False
        except Exception:
            return False

    def resolve_dependencies(self, extension_id: str, dependencies: Dict[str, str]) -> Dict[str, str]:
        """Resolve dependencies for an extension"""
        unresolved = {}
        conflicts = {}

        for dep_name, version_spec in dependencies.items():
            # Check if package is available (simplified check - in real implementation would check pip)
            # For now, assume common packages are available
            if dep_name in ['psutil', 'requests', 'fastapi', 'sqlalchemy', 'pydantic']:
                # These are common packages that should be available
                pass  # Allow installation
            elif dep_name in self.installed_packages:
                installed_version = self.installed_packages[dep_name]
                if not self.check_version_compatibility(installed_version, version_spec):
                    conflicts[dep_name] = {
                        'required': version_spec,
                        'installed': installed_version
                    }
            else:
                unresolved[dep_name] = version_spec

        return {
            'unresolved': unresolved,
            'conflicts': conflicts,
            'can_install': len(unresolved) == 0 and len(conflicts) == 0
        }

    def install_missing_dependencies(self, unresolved: Dict[str, str]) -> List[str]:
        """Attempt to install missing dependencies (would integrate with pip)"""
        installed = []
        failed = []

        for package, version_spec in unresolved.items():
            try:
                # This would normally use pip or another package manager
                # For now, we'll simulate installation
                print(f"Installing {package}{version_spec}")
                self.installed_packages[package] = version_spec.replace('>=', '').replace('==', '')
                installed.append(package)
            except Exception as e:
                print(f"Failed to install {package}: {e}")
                failed.append(package)

        return installed

class ExtensionVersionManager:
    """Manages extension versions and updates"""

    def __init__(self):
        self.installed_versions: Dict[str, str] = {}
        self.available_updates: Dict[str, str] = {}

    def register_extension(self, extension_id: str, version: str):
        """Register an installed extension version"""
        self.installed_versions[extension_id] = version

    def check_for_updates(self, extension_id: str, current_version: str) -> Optional[str]:
        """Check if updates are available for an extension"""
        # This would typically query a repository or marketplace
        # For now, return None (no updates available)
        return None

    def is_compatible_update(self, current_version: str, new_version: str) -> bool:
        """Check if an update is backward compatible"""
        try:
            current = version.parse(current_version)
            new = version.parse(new_version)

            # Major version changes are potentially breaking
            if new.major > current.major:
                return False

            # Minor version changes are usually safe
            return True
        except Exception:
            return False

    def validate_extension_version(self, version_string: str) -> bool:
        """Validate that a version string follows semantic versioning"""
        semver_pattern = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        return bool(re.match(semver_pattern, version_string))

class ExtensionRepository:
    """Manages extension repositories and marketplaces"""

    def __init__(self, repository_url: str = None):
        self.repository_url = repository_url or "https://extensions.megamonitor.dev"
        self.cache: Dict[str, dict] = {}

    def search_extensions(self, query: str) -> List[Dict]:
        """Search for extensions in the repository"""
        # This would query the actual repository
        # For now, return empty list
        return []

    def get_extension_info(self, extension_id: str) -> Optional[Dict]:
        """Get detailed information about an extension"""
        if extension_id in self.cache:
            return self.cache[extension_id]

        try:
            # This would make an HTTP request to the repository
            # response = requests.get(f"{self.repository_url}/extensions/{extension_id}")
            # return response.json()

            # For now, return None
            return None
        except Exception:
            return None

    def download_extension(self, extension_id: str, version: str) -> Optional[bytes]:
        """Download an extension package"""
        try:
            # This would download the extension ZIP file
            # response = requests.get(f"{self.repository_url}/extensions/{extension_id}/{version}/download")
            # return response.content

            # For now, return None
            return None
        except Exception:
            return None

# Global instances
dependency_resolver = DependencyResolver()
version_manager = ExtensionVersionManager()
extension_repository = ExtensionRepository()