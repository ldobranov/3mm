# backend/utils/extension_security.py
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import re

class ExtensionSecurityManager:
    """Manages security for extension operations"""

    def __init__(self):
        self.allowed_file_types = {'.vue', '.js', '.ts', '.json', '.css', '.scss', '.png', '.jpg', '.jpeg', '.gif', '.svg'}
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.forbidden_patterns = [
            r'import\s+.*\.\./',  # Parent directory imports
            r'require\s*\(\s*.*\.\./',  # Parent directory requires
            r'process\.env',  # Environment access
            # r'localStorage',  # Local storage access (allowed for frontend widgets)
            r'document\.cookie',  # Cookie access
            r'window\.location',  # Location manipulation
            r'eval\s*\(',  # Eval usage
            # r'Function\s*\(',  # Function constructor (allowed in Vue components)
            r'XMLHttpRequest',  # Direct HTTP requests
            # r'fetch\s*\(',  # Fetch API (allowed for API calls)
        ]

    def validate_file_security(self, file_path: Path) -> List[str]:
        """Validate a single file for security issues"""
        issues = []

        # Check file extension
        if file_path.suffix.lower() not in self.allowed_file_types:
            issues.append(f"Disallowed file type: {file_path.suffix}")

        # Check file size
        try:
            size = file_path.stat().st_size
            if size > self.max_file_size:
                issues.append(f"File too large: {size} bytes (max: {self.max_file_size})")
        except OSError:
            issues.append("Cannot read file size")

        # Check file content for dangerous patterns
        if file_path.suffix.lower() in {'.js', '.ts', '.vue'}:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                for pattern in self.forbidden_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        issues.append(f"Potentially dangerous code pattern found: {pattern}")

                # Check for network access patterns
                if re.search(r'(http://|https://|ws://|wss://)', content):
                    issues.append("Network access detected - ensure proper CORS handling")

            except (IOError, UnicodeDecodeError):
                issues.append("Cannot read file content for security analysis")

        return issues

    def validate_extension_package(self, extension_dir: Path) -> Dict[str, List[str]]:
        """Validate entire extension package for security"""
        security_report = {
            'critical': [],
            'warnings': [],
            'passed': []
        }

        # Check all files in extension
        for file_path in extension_dir.rglob('*'):
            if file_path.is_file():
                issues = self.validate_file_security(file_path)

                if issues:
                    relative_path = file_path.relative_to(extension_dir)
                    for issue in issues:
                        if 'dangerous' in issue.lower() or 'forbidden' in issue.lower():
                            security_report['critical'].append(f"{relative_path}: {issue}")
                        else:
                            security_report['warnings'].append(f"{relative_path}: {issue}")
                else:
                    security_report['passed'].append(str(file_path.relative_to(extension_dir)))

        return security_report

    def calculate_extension_hash(self, extension_dir: Path) -> str:
        """Calculate SHA256 hash of extension files for integrity checking"""
        hash_obj = hashlib.sha256()

        # Sort files for consistent hashing
        files = []
        for file_path in extension_dir.rglob('*'):
            if file_path.is_file():
                files.append(file_path)

        files.sort()

        for file_path in files:
            try:
                with open(file_path, 'rb') as f:
                    while chunk := f.read(8192):
                        hash_obj.update(chunk)
            except IOError:
                continue  # Skip files that can't be read

        return hash_obj.hexdigest()

    def quarantine_extension(self, extension_dir: Path, reason: str) -> None:
        """Move extension to quarantine directory"""
        quarantine_dir = Path("backend/extensions/quarantine")
        quarantine_dir.mkdir(exist_ok=True)

        extension_name = extension_dir.name
        quarantine_path = quarantine_dir / extension_name

        if quarantine_path.exists():
            # Remove existing quarantine
            import shutil
            shutil.rmtree(quarantine_path)

        # Move to quarantine
        extension_dir.rename(quarantine_path)

        # Log quarantine action
        print(f"Extension {extension_name} quarantined: {reason}")

class ExtensionPermissionManager:
    """Manages permissions for extension capabilities"""

    def __init__(self):
        self.permission_levels = {
            'none': 0,
            'read': 1,
            'write': 2,
            'admin': 3
        }

    def check_extension_permissions(self, manifest: Dict, user_permissions: List[str]) -> Dict[str, bool]:
        """Check if user has required permissions for extension"""
        required_permissions = manifest.get('permissions', [])
        results = {}

        for perm in required_permissions:
            # Check if user has this permission
            has_permission = perm in user_permissions
            results[perm] = has_permission

        return results

    def validate_manifest_permissions(self, manifest: Dict) -> List[str]:
        """Validate that manifest permissions are reasonable"""
        issues = []
        permissions = manifest.get('permissions', [])

        dangerous_permissions = [
            'system_access',
            'file_system',
            'network_unrestricted',
            'database_admin',
            'process_control',
            'database_direct'
        ]

        for perm in permissions:
            if perm in dangerous_permissions:
                issues.append(f"Dangerous permission requested: {perm}")

        return issues

# Global security manager instance
security_manager = ExtensionSecurityManager()
permission_manager = ExtensionPermissionManager()