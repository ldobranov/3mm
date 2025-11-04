"""
Extension Sandbox - Provides restricted execution environment for extensions
"""

import sys
import types
from typing import Dict, Any, List, Set
import builtins

class RestrictedEnvironment:
    """Creates a restricted execution environment for extensions"""

    def __init__(self, allowed_modules: List[str] = None, allowed_builtins: List[str] = None):
        self.allowed_modules = allowed_modules or [
            'os', 'sys', 'json', 'datetime', 'time', 'math', 'random',
            'collections', 'itertools', 'functools'
        ]

        self.allowed_builtins = allowed_builtins or [
            'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes',
            'chr', 'dict', 'enumerate', 'filter', 'float', 'format',
            'int', 'len', 'list', 'map', 'max', 'min', 'ord', 'pow',
            'range', 'round', 'set', 'slice', 'sorted', 'str', 'sum',
            'tuple', 'type', 'zip', 'isinstance', 'hasattr', 'getattr',
            'setattr', 'delattr', 'callable', 'repr', 'print'
        ]

        # Create restricted builtins
        self.safe_builtins = {}
        for name in self.allowed_builtins:
            if hasattr(builtins, name):
                self.safe_builtins[name] = getattr(builtins, name)

        # Add safe versions of dangerous builtins
        self.safe_builtins['open'] = self._restricted_open
        self.safe_builtins['eval'] = self._restricted_eval
        self.safe_builtins['exec'] = self._restricted_exec
        self.safe_builtins['__import__'] = self._restricted_import

    def _restricted_open(self, *args, **kwargs):
        """Restrict file operations"""
        raise PermissionError("File operations not allowed in extension sandbox")

    def _restricted_eval(self, *args, **kwargs):
        """Disable eval"""
        raise PermissionError("eval() not allowed in extension sandbox")

    def _restricted_exec(self, *args, **kwargs):
        """Disable exec"""
        raise PermissionError("exec() not allowed in extension sandbox")

    def _restricted_import(self, name, *args, **kwargs):
        """Restrict module imports"""
        if name not in self.allowed_modules:
            raise ImportError(f"Import of module '{name}' not allowed in extension sandbox")
        return __builtins__['__import__'](name, *args, **kwargs)

    def create_sandbox(self, global_vars: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a sandboxed global environment"""
        sandbox_globals = {
            '__builtins__': self.safe_builtins,
            '__name__': '__extension__',
            '__doc__': None,
            '__package__': None,
        }

        if global_vars:
            # Only allow safe global variables
            for key, value in global_vars.items():
                if not key.startswith('_'):
                    sandbox_globals[key] = value

        return sandbox_globals

class ExtensionSandbox:
    """Manages sandboxed execution of extension code"""

    def __init__(self):
        self.environments: Dict[str, RestrictedEnvironment] = {}

    def create_environment(self, extension_id: str, permissions: List[str]) -> RestrictedEnvironment:
        """Create a restricted environment based on extension permissions"""

        # Base allowed modules
        allowed_modules = [
            'json', 'datetime', 'time', 'math', 'random',
            'collections', 'itertools', 'functools'
        ]

        # Add modules based on permissions
        if 'system_access' in permissions:
            allowed_modules.extend(['psutil', 'platform', 'socket'])
        if 'network_access' in permissions:
            allowed_modules.extend(['urllib', 'http', 'socket'])
        if 'file_system' in permissions:
            # File system access is heavily restricted
            pass

        env = RestrictedEnvironment(allowed_modules=allowed_modules)
        self.environments[extension_id] = env
        return env

    def execute_in_sandbox(self, extension_id: str, code: str, global_vars: Dict[str, Any] = None) -> Any:
        """Execute code in a sandboxed environment"""
        if extension_id not in self.environments:
            raise ValueError(f"No sandbox environment for extension {extension_id}")

        env = self.environments[extension_id]
        sandbox_globals = env.create_sandbox(global_vars)

        try:
            # Compile and execute the code
            compiled_code = compile(code, f'<extension_{extension_id}>', 'exec')
            exec(compiled_code, sandbox_globals)
            return sandbox_globals
        except Exception as e:
            raise RuntimeError(f"Sandbox execution failed for {extension_id}: {e}")

    def validate_extension_code(self, extension_id: str, code: str) -> List[str]:
        """Validate extension code for security issues"""
        issues = []

        # Check for dangerous patterns
        dangerous_patterns = [
            'import os', 'import sys', 'import subprocess',
            'eval(', 'exec(', '__import__(',
            'open(', 'file(', 'input('
        ]

        for pattern in dangerous_patterns:
            if pattern in code:
                issues.append(f"Dangerous pattern detected: {pattern}")

        # Check for file system access
        if 'open(' in code or 'file(' in code:
            issues.append("File system access detected")

        # Check for network access without permission
        if ('urllib' in code or 'http' in code or 'socket' in code):
            if extension_id not in self.environments or 'network_access' not in self.environments[extension_id].allowed_modules:
                issues.append("Network access without permission")

        return issues

# Global sandbox manager
extension_sandbox = ExtensionSandbox()