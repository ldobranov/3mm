"""Runtime composition; worker imports do not load setup/provisioning code."""

__all__ = ["DeviceRuntimePlanner", "RuntimePlan", "RuntimeService"]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    from components.system_runtime import services
    return getattr(services, name)
