"""Loaded immutable component identity; contains no permission or credentials."""
import os

_identity=None


def set_component_identity(component,build_id):
    global _identity
    if _identity is not None:raise RuntimeError("Component identity was already bound")
    _identity={"component":component,"build_id":build_id}


def component_health():
    return None if _identity is None else {**_identity,"pid":os.getpid()}
